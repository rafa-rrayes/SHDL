"""shdl.lock: the pinned resolution (JSON, committed alongside shdl.toml).

The lock is what build/test/run trust — they never touch the network. Its
``manifest_fingerprint`` ties it to the inputs that produced it (the direct
dependencies and the effective registry URL); every consuming command
recomputes the fingerprint and treats a mismatch as stale.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import CliError
from .project import PathDep, Project

LOCK_FORMAT = 1


@dataclass
class LockedPackage:
    version: str
    source: dict  # {"type": "registry", "url": …} | {"type": "path", "path": …}
    dependencies: dict[str, str]
    module: str
    exports: list[str]
    sha256: str | None = None  # registry packages only

    @property
    def is_registry(self) -> bool:
        return self.source.get("type") == "registry"


@dataclass
class Lock:
    manifest_fingerprint: str
    registry: str
    packages: dict[str, LockedPackage] = field(default_factory=dict)


def manifest_fingerprint(
    dependencies: dict[str, str | PathDep], registry_url: str
) -> str:
    canon = {
        "dependencies": {
            name: ({"path": spec.path} if isinstance(spec, PathDep) else spec)
            for name, spec in dependencies.items()
        },
        "registry": registry_url,
    }
    digest = hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def read_lock(path: Path) -> Lock | None:
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CliError(f"{path}: invalid JSON: {e}") from e
    if doc.get("lock_format") != LOCK_FORMAT:
        raise CliError(
            f"{path}: unsupported lock_format {doc.get('lock_format')!r} "
            f"(this toolchain writes {LOCK_FORMAT})"
        )
    try:
        packages = {
            name: LockedPackage(
                version=p["version"],
                source=p["source"],
                dependencies=p["dependencies"],
                module=p["module"],
                exports=p["exports"],
                sha256=p.get("sha256"),
            )
            for name, p in doc["packages"].items()
        }
        return Lock(
            manifest_fingerprint=doc["manifest_fingerprint"],
            registry=doc["registry"],
            packages=packages,
        )
    except (KeyError, TypeError) as e:
        raise CliError(f"{path}: malformed lock file ({e}); delete it and re-run 'shdl install'") from e


def write_lock(path: Path, lock: Lock) -> None:
    doc = {
        "lock_format": LOCK_FORMAT,
        "manifest_fingerprint": lock.manifest_fingerprint,
        "registry": lock.registry,
        "packages": {
            name: {k: v for k, v in asdict(p).items() if not (k == "sha256" and v is None)}
            for name, p in lock.packages.items()
        },
    }
    path.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def check_fresh(project: Project, registry_url: str) -> Lock:
    """The lock, verified fresh against shdl.toml — the build/test preflight."""
    lock = read_lock(project.lock_path)
    if lock is None:
        raise CliError("no shdl.lock — run 'shdl install'")
    expected = manifest_fingerprint(project.dependencies, registry_url)
    if lock.manifest_fingerprint != expected:
        raise CliError(
            "shdl.lock is stale (shdl.toml dependencies or registry changed) — "
            "run 'shdl install'"
        )
    return lock
