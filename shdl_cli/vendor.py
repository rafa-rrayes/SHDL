"""shdl_modules/: the vendored tree, synced to shdl.lock.

Registry packages are extracted here (one directory per package, named after
the package, containing exactly the archive's files). Path dependencies are
never vendored — their directories go straight on the include path. The tree
is disposable: visible for reading, gitignored, and rebuilt from the lock by
``shdl install`` at any time.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
from pathlib import Path

from .errors import CliError
from .index_client import IndexClient
from .lockfile import Lock
from .project import Project


def _vendored_manifest(pkg_dir: Path) -> dict | None:
    mfile = pkg_dir / "package.json"
    if not mfile.is_file():
        return None
    try:
        return json.loads(mfile.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _is_current(pkg_dir: Path, name: str, version: str) -> bool:
    m = _vendored_manifest(pkg_dir)
    return m is not None and m.get("name") == name and m.get("version") == version


def _remove_entry(path: Path) -> None:
    """Remove whatever sits at ``path`` — dir, file, or dangling symlink.
    shdl_modules/ is machine-managed; a stray file (.DS_Store, a hand-made
    placeholder) must never wedge a sync."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink(missing_ok=True)


def _extract(blob: bytes, name: str, version: str, modules_dir: Path) -> None:
    prefix = f"{name}-{version}/"
    tmp = modules_dir / f".tmp-{name}"
    _remove_entry(tmp)
    tmp.mkdir(parents=True)
    try:
        try:
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if (
                        not member.isreg()
                        or not member.name.startswith(prefix)
                        or ".." in member.name.split("/")
                    ):
                        raise CliError(
                            f"archive for {name} {version} contains an unexpected "
                            f"member {member.name!r} — refusing to unpack"
                        )
                tar.extractall(tmp, filter="data")
        except tarfile.TarError as e:
            raise CliError(f"archive for {name} {version} is not a valid tar.gz: {e}") from e
        extracted = tmp / f"{name}-{version}"
        if not extracted.is_dir():
            raise CliError(f"archive for {name} {version} did not contain {prefix}")
        dest = modules_dir / name
        _remove_entry(dest)
        os.replace(extracted, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sync(project: Project, lock: Lock, client: IndexClient, *, force: bool = False) -> list[str]:
    """Make shdl_modules/ exactly mirror the lock. Returns progress lines."""
    lines: list[str] = []
    registry_pkgs = {n: p for n, p in lock.packages.items() if p.is_registry}
    modules_dir = project.modules_dir

    if modules_dir.is_dir():
        for child in sorted(modules_dir.iterdir()):
            keep = child.is_dir() and not child.name.startswith(".tmp-")
            if keep and child.name in registry_pkgs:
                continue
            _remove_entry(child)
            if keep:
                lines.append(f"  removed {child.name}")

    for name, locked in sorted(registry_pkgs.items()):
        pkg_dir = modules_dir / name
        if not force and _is_current(pkg_dir, name, locked.version):
            continue
        assert locked.sha256, f"registry package {name} has no sha256 in the lock"
        blob = client.download_archive(name, locked.version, locked.sha256)
        modules_dir.mkdir(parents=True, exist_ok=True)
        _extract(blob, name, locked.version, modules_dir)
        lines.append(f"  fetched {name} {locked.version} ({len(blob) / 1000:.1f} kB)")

    return lines


def verify_vendored(project: Project, lock: Lock) -> None:
    """The build/test preflight: every locked registry package is vendored
    at the locked version. Never touches the network."""
    for name, locked in sorted(lock.packages.items()):
        if not locked.is_registry:
            pdir = (project.root / locked.source["path"]).resolve()
            if not (pdir / locked.module).is_file():
                raise CliError(
                    f"path dependency {name}: module {locked.module} not found "
                    f"in {pdir}"
                )
            continue
        if not _is_current(project.modules_dir / name, name, locked.version):
            raise CliError(
                f"vendored package {name} is missing or does not match the lock "
                f"({name} {locked.version}) — run 'shdl install'"
            )


def include_dirs(project: Project, lock: Lock) -> list[str]:
    """Flattener -I dirs: sorted vendored package dirs, then path-dep dirs."""
    vendored = sorted(
        str(project.modules_dir / name)
        for name, p in lock.packages.items()
        if p.is_registry
    )
    paths = sorted(
        str((project.root / p.source["path"]).resolve())
        for p in lock.packages.values()
        if not p.is_registry
    )
    return vendored + paths
