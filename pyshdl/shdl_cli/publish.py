"""``shdl verify-package`` / ``shdl publish``: cc.py-equivalent admission.

``verify_package`` checks a package directory the way CCircus's verifier
does: manifest schema, every export builds at its declared defaults, every
test vector green (via :mod:`shdl_cli.runner`, the shared semantics).
``publish`` adds a not-already-published check against the index and prints
the PR playbook — actual publishing is a PR against the CCircus repo.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import CliError
from .index_client import IndexClient
from .runner import run_cases
from .semver import Range, Version

MANIFEST_REQUIRED = (
    "manifest_format", "name", "version", "summary", "license",
    "authors", "shdl", "module", "dependencies", "exports",
)
EXPORT_REQUIRED = ("name", "summary", "params", "inputs", "outputs")


def load_package_manifest(pkg_dir: Path) -> dict:
    mfile = pkg_dir / "package.json"
    if not mfile.is_file():
        raise CliError(f"no package.json in {pkg_dir}")
    try:
        manifest = json.loads(mfile.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CliError(f"{mfile}: invalid JSON: {e}") from e

    errors = [f"missing required field: {f}" for f in MANIFEST_REQUIRED if f not in manifest]
    if not errors:
        if type(manifest["manifest_format"]) is not int or manifest["manifest_format"] != 1:
            errors.append(f"unsupported manifest_format {manifest['manifest_format']!r}")
        if not manifest["authors"]:
            errors.append("authors must list at least one author")
        name = manifest["name"]
        if name != pkg_dir.resolve().name:
            errors.append(f"name {name!r} != directory name {pkg_dir.resolve().name!r}")
        if manifest["module"] != f"{name}.shdl":
            errors.append(f"module {manifest['module']!r} != {name}.shdl")
        if not (pkg_dir / manifest["module"]).is_file():
            errors.append(f"module file {manifest['module']} does not exist")
        try:
            Version.parse(manifest["version"])
        except CliError as e:
            errors.append(str(e))
        for dep, spec in manifest["dependencies"].items():
            try:
                Range.parse(spec)
            except CliError as e:
                errors.append(f"dependency {dep}: {e}")
        if not isinstance(manifest["exports"], list) or not manifest["exports"]:
            errors.append("exports must be a non-empty array")
        else:
            for i, exp in enumerate(manifest["exports"]):
                missing = [f for f in EXPORT_REQUIRED if f not in exp]
                if missing:
                    errors.append(f"exports[{i}] missing fields: {', '.join(missing)}")
    if errors:
        raise CliError(f"{mfile}: invalid manifest:\n  " + "\n  ".join(errors))
    return manifest


def _include_dirs(pkg_dir: Path, manifest: dict, packages_root: Path) -> list[str]:
    """Transitive dependency dirs under ``packages_root`` (cc.py semantics)."""
    dirs: list[str] = []
    seen: set[str] = set()

    def walk(m: dict) -> None:
        for dep in m.get("dependencies", {}):
            if dep in seen:
                continue
            seen.add(dep)
            ddir = packages_root / dep
            dmanifest = ddir / "package.json"
            if not dmanifest.is_file():
                raise CliError(
                    f"dependency {dep!r} not found under {packages_root} "
                    "(pass --packages-root at the directory holding it)"
                )
            dirs.append(str(ddir))
            walk(json.loads(dmanifest.read_text(encoding="utf-8")))

    walk(manifest)
    return dirs


def verify_package(
    pkg_dir: Path, packages_root: Path | None = None
) -> tuple[list[str], bool]:
    """(report lines, ok). Builds every export at defaults + runs vectors."""
    pkg_dir = pkg_dir.resolve()
    manifest = load_package_manifest(pkg_dir)
    name = manifest["name"]
    root = (packages_root or pkg_dir.parent).resolve()
    include = _include_dirs(pkg_dir, manifest, root)

    from SHDL import Circuit

    def open_component(comp: str):
        return Circuit(
            str(pkg_dir / manifest["module"]), top=comp, include_dirs=include
        )

    lines: list[str] = []
    ok = True

    built = 0
    exports = manifest["exports"]
    for exp in exports:
        comp = exp["name"]
        try:
            open_component(comp).close()
            built += 1
        except Exception as e:  # noqa: BLE001 - report any failure
            lines.append(f"  FAIL build  {name}::{comp}: {type(e).__name__}: {e}")
            ok = False
    lines.append(f"[build] {name}: {built}/{len(exports)} components compiled")

    tfile = pkg_dir / manifest.get("tests", f"tests/{name}.tests.json")
    if not tfile.is_file():
        lines.append(f"[test]  {name}: no test file ({tfile.name}) — a package needs vectors")
        return lines, False
    spec = json.loads(tfile.read_text(encoding="utf-8"))
    case_lines, passed, total = run_cases(open_component, spec.get("cases", []))
    lines.extend(case_lines)
    lines.append(f"[test]  {name}: {passed}/{total} cases green")
    return lines, ok and passed == total and total > 0


def publish_playbook(pkg_dir: Path, manifest: dict, index_url: str) -> list[str]:
    name, version = manifest["name"], manifest["version"]
    return [
        f"{name} {version} verified. To publish it to Circuit Circus:",
        "",
        "  1. Fork and clone https://github.com/rafa-rrayes/CCircus",
        f"  2. Copy this package in:   cp -R {pkg_dir} <CCircus>/packages/{name}",
        "  3. Regenerate the index:   python tools/cc.py gen-index",
        f"  4. Commit packages/{name}, registry.json, index/{name}.json and",
        f"     archives/{name}-{version}.tar.gz, then open a PR.",
        "",
        "CI re-verifies everything (INDEX_FORMAT.md §7); once merged, the",
        f"package is installable with:  shdl add {name}",
    ]


def check_not_published(manifest: dict, client: IndexClient) -> None:
    name, version = manifest["name"], manifest["version"]
    # scan the registry list directly: a transport/format failure must abort
    # the publish check, not silently read as "not published"
    listed = {p.get("name") for p in client.registry().get("packages", [])}
    if name not in listed:
        return  # not in the index at all — publishable
    versions = client.package_index(name)["versions"]
    if version in versions:
        raise CliError(
            f"{name} {version} is already published (index {client.index_url}) — "
            "published versions are immutable; bump the version"
        )
