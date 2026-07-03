"""Flat dependency resolution: highest satisfying version, to a fixpoint.

The constraint set only ever grows (shdl.toml + path-dep manifests seed it;
every chosen package version adds its own dependency ranges), so chosen
versions can only move downward and the loop terminates. One pass is not
enough — a package chosen late can constrain one chosen early.

Post-resolution, the flat SHDL namespace is guarded here (the flattener
silently shadows on module-name collisions, so the CLI must refuse first):
module basenames must be unique across chosen packages, path deps, and the
project's own modules; exported component names must be unique across
packages. Finally the installed toolchain is checked against every chosen
version's ``shdl`` range.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .errors import CliError
from .index_client import IndexClient
from .lockfile import Lock, LockedPackage, manifest_fingerprint
from .project import PathDep, Project
from .semver import Range, Version

_MAX_ITERATIONS = 100

_PATH_MANIFEST_REQUIRED = ("name", "version", "module", "dependencies", "exports")


@dataclass(frozen=True)
class _Constraint:
    range: Range
    requirer: str


def load_path_manifest(project: Project, name: str, dep: PathDep) -> dict:
    pdir = (project.root / dep.path).resolve()
    mfile = pdir / "package.json"
    if not mfile.is_file():
        raise CliError(f"path dependency {name}: no package.json at {mfile}")
    try:
        manifest = json.loads(mfile.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CliError(f"{mfile}: invalid JSON: {e}") from e
    missing = [f for f in _PATH_MANIFEST_REQUIRED if f not in manifest]
    if missing:
        raise CliError(f"{mfile}: manifest missing fields: {', '.join(missing)}")
    if manifest["name"] != name:
        raise CliError(
            f"path dependency {name}: manifest at {mfile} names the package "
            f"{manifest['name']!r} — the shdl.toml key must match"
        )
    if not (pdir / manifest["module"]).is_file():
        raise CliError(f"path dependency {name}: module file {manifest['module']} not found in {pdir}")
    Version.parse(manifest["version"])
    return manifest


def resolve(project: Project, client: IndexClient) -> Lock:
    """Resolve shdl.toml's dependencies into a fresh Lock (not yet written)."""
    path_manifests: dict[str, dict] = {
        name: load_path_manifest(project, name, spec)
        for name, spec in project.dependencies.items()
        if isinstance(spec, PathDep)
    }

    constraints: dict[str, list[_Constraint]] = {}

    def add_constraint(target: str, spec: str, requirer: str) -> bool:
        rng = Range.parse(spec)
        bucket = constraints.setdefault(target, [])
        if any(c.range.spec == rng.spec and c.requirer == requirer for c in bucket):
            return False
        bucket.append(_Constraint(rng, requirer))
        return True

    for name, spec in project.dependencies.items():
        if isinstance(spec, str):
            add_constraint(name, spec, "shdl.toml")
    for pname, manifest in path_manifests.items():
        for dep, spec in manifest["dependencies"].items():
            add_constraint(dep, spec, f"{pname} (path dependency)")

    chosen: dict[str, Version] = {}
    for _ in range(_MAX_ITERATIONS):
        changed = False
        for name in sorted(constraints):
            if name in path_manifests:
                continue
            available = client.versions(name)
            ranges = constraints[name]
            pick = next(
                (v for v in sorted(available, reverse=True)
                 if all(c.range.contains(v) for c in ranges)),
                None,
            )
            if pick is None:
                lines = [f"no version of {name} satisfies every requirement:"]
                for c in ranges:
                    lines.append(f"  {c.range} (required by {c.requirer})")
                lines.append(
                    "  available: "
                    + ", ".join(str(v) for v in sorted(available, reverse=True))
                )
                raise CliError("\n".join(lines))
            if chosen.get(name) != pick:
                chosen[name] = pick
                changed = True
        for name, ver in list(chosen.items()):
            entry = client.versions(name)[ver]
            for dep, spec in entry.get("dependencies", {}).items():
                if add_constraint(dep, spec, f"{name} {ver}"):
                    changed = True
        if not changed:
            break
    else:
        raise CliError(f"dependency resolution did not converge after {_MAX_ITERATIONS} iterations")

    for name, manifest in path_manifests.items():
        v = Version.parse(manifest["version"])
        for c in constraints.get(name, []):
            if not c.range.contains(v):
                raise CliError(
                    f"path dependency {name} {v} does not satisfy "
                    f"{c.range} (required by {c.requirer})"
                )

    packages: dict[str, LockedPackage] = {}
    for name, ver in chosen.items():
        entry = client.versions(name)[ver]
        packages[name] = LockedPackage(
            version=str(ver),
            source={"type": "registry", "url": client.index_url},
            dependencies=dict(entry.get("dependencies", {})),
            module=entry["module"],
            exports=[e["name"] for e in entry.get("exports", [])],
            sha256=entry["sha256"],
        )
    for name, manifest in path_manifests.items():
        dep = project.dependencies[name]
        assert isinstance(dep, PathDep)
        packages[name] = LockedPackage(
            version=manifest["version"],
            source={"type": "path", "path": dep.path},
            dependencies=dict(manifest["dependencies"]),
            module=manifest["module"],
            exports=[e["name"] for e in manifest["exports"]],
            sha256=None,
        )

    _check_collisions(project, packages)
    _check_toolchain(project, packages, client, path_manifests, chosen)

    return Lock(
        manifest_fingerprint=manifest_fingerprint(project.dependencies, client.index_url),
        registry=client.index_url,
        packages=packages,
    )


def _project_modules(project: Project, exclude: set[Path]) -> set[str]:
    """Basenames of the project's own .shdl modules (main's tree + src/),
    never counting the machine-managed or dependency-owned trees in
    ``exclude`` (shdl_modules/, build/, path-dep dirs)."""
    roots = {project.main_path.parent.resolve()}
    src = project.root / "src"
    if src.is_dir():
        roots.add(src.resolve())
    names: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*.shdl"):
            if any(p.resolve().is_relative_to(ex) for ex in exclude):
                continue
            names.add(p.name)
    if project.main_path.is_file():
        names.add(project.main_path.name)
    return names


def _provided_modules(project: Project, name: str, p: LockedPackage) -> set[str]:
    """Every module basename a package puts on the include path. For a path
    dep that is the whole directory, declared or not — an undeclared .shdl
    file there shadows same-named modules just as effectively."""
    if p.is_registry:
        return {p.module}
    pdir = (project.root / p.source["path"]).resolve()
    return {p.module} | {f.name for f in pdir.glob("*.shdl")}


def _check_collisions(project: Project, packages: dict[str, LockedPackage]) -> None:
    errors: list[str] = []

    module_owner: dict[str, str] = {}
    for name, p in sorted(packages.items()):
        for mod in sorted(_provided_modules(project, name, p)):
            if mod in module_owner and module_owner[mod] != name:
                errors.append(
                    f"module name collision: packages {module_owner[mod]} and "
                    f"{name} both provide {mod}"
                )
            else:
                module_owner[mod] = name

    exclude = {project.modules_dir.resolve(), project.build_dir.resolve()} | {
        (project.root / p.source["path"]).resolve()
        for p in packages.values()
        if not p.is_registry
    }
    for mod in sorted(_project_modules(project, exclude)):
        if mod in module_owner:
            errors.append(
                f"module name collision: the project's {mod} shadows the one in "
                f"package {module_owner[mod]} (the SHDL module namespace is flat "
                f"— rename the project module)"
            )

    export_owner: dict[str, str] = {}
    for name, p in sorted(packages.items()):
        for comp in p.exports:
            if comp in export_owner:
                errors.append(
                    f"component name collision: {comp!r} is exported by both "
                    f"{export_owner[comp]} and {name}"
                )
            else:
                export_owner[comp] = name

    if errors:
        raise CliError("\n".join(errors))


def _check_toolchain(
    project: Project,
    packages: dict[str, LockedPackage],
    client: IndexClient,
    path_manifests: dict[str, dict],
    chosen: dict[str, Version],
) -> None:
    try:
        installed = importlib.metadata.version("pyshdl")
    except importlib.metadata.PackageNotFoundError:
        print(
            "shdl: warning: pyshdl is not installed as a package (checkout dev "
            "mode?) — skipping toolchain-compatibility checks",
            file=sys.stderr,
        )
        return
    try:
        v = Version.parse(installed)
    except CliError:
        print(
            f"shdl: warning: installed pyshdl version {installed!r} is not "
            "X.Y.Z — skipping toolchain-compatibility checks",
            file=sys.stderr,
        )
        return

    ranges: dict[str, str] = {}
    if project.shdl:
        ranges["the project (shdl.toml)"] = project.shdl
    for name, ver in chosen.items():
        spec = client.versions(name)[ver].get("shdl")
        if spec:
            ranges[f"{name} {ver}"] = spec
    for name, manifest in path_manifests.items():
        spec = manifest.get("shdl")
        if spec:
            ranges[f"{name} (path dependency)"] = spec

    for who, spec in ranges.items():
        if not Range.parse(spec).contains(v):
            raise CliError(
                f"installed pyshdl {v} does not satisfy the shdl range "
                f"{spec!r} required by {who}"
            )
