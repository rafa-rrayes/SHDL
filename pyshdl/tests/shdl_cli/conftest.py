"""Shared fixtures for the shdl CLI suite.

The centerpiece is ``file_registry``: a real INDEX_FORMAT.md-shaped registry
(root index, per-package version files, deterministic archives) built once
per session from ``fixtures/<name>-<version>/`` package directories and
served over ``file://`` — the same transport ``shdl`` uses against a local
CCircus checkout, with zero network.

NOTE: this directory is deliberately NOT a package (no ``__init__.py``) and
test basenames are prefixed ``test_shdl_`` to stay unique repo-wide, matching
tests/pyshdl/.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --- a miniature gen-index (the INDEX_FORMAT.md §4 recipe) -------------------
def build_archive(pkg_dir: Path, name: str, version: str) -> bytes:
    manifest = json.loads((pkg_dir / "package.json").read_text(encoding="utf-8"))
    rels = ["package.json", manifest["module"]]
    if (pkg_dir / "README.md").is_file():
        rels.append("README.md")
    tests_dir = pkg_dir / "tests"
    if tests_dir.is_dir():
        rels.extend(
            f.relative_to(pkg_dir).as_posix() for f in sorted(tests_dir.rglob("*")) if f.is_file()
        )
    members = sorted((f"{name}-{version}/{rel}", pkg_dir / rel) for rel in rels)
    tar_buf = io.BytesIO()
    with tarfile.open(mode="w", fileobj=tar_buf, format=tarfile.USTAR_FORMAT) as tar:
        for member_name, path in members:
            data = path.read_bytes()
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", filename="", mtime=0) as gz:
        gz.write(tar_buf.getvalue())
    return buf.getvalue()


def build_registry(root: Path, package_dirs: list[Path]) -> None:
    """Write registry.json / index/ / archives/ under ``root`` from fixture
    package dirs named ``<name>-<version>``."""
    per_pkg: dict[str, dict[str, dict]] = {}
    (root / "archives").mkdir(parents=True, exist_ok=True)
    (root / "index").mkdir(parents=True, exist_ok=True)
    for pkg_dir in package_dirs:
        name, _, version = pkg_dir.name.rpartition("-")
        manifest = json.loads((pkg_dir / "package.json").read_text(encoding="utf-8"))
        blob = build_archive(pkg_dir, name, version)
        (root / "archives" / f"{name}-{version}.tar.gz").write_bytes(blob)
        per_pkg.setdefault(name, {})[version] = {
            "summary": manifest["summary"],
            "description": manifest.get("description", ""),
            "license": manifest["license"],
            "authors": manifest["authors"],
            "homepage": manifest.get("homepage", ""),
            "keywords": manifest.get("keywords", []),
            "shdl": manifest["shdl"],
            "module": manifest["module"],
            "dependencies": manifest["dependencies"],
            "archive": f"archives/{name}-{version}.tar.gz",
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "exports": manifest["exports"],
        }

    def vkey(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split("."))

    registry_pkgs = []
    for name in sorted(per_pkg):
        versions = dict(sorted(per_pkg[name].items(), key=lambda kv: vkey(kv[0])))
        latest = max(versions, key=vkey)
        (root / "index" / f"{name}.json").write_text(
            json.dumps(
                {"index_format": 2, "name": name, "latest": latest, "versions": versions},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        lv = versions[latest]
        registry_pkgs.append(
            {
                "name": name,
                "version": latest,
                "summary": lv["summary"],
                "keywords": lv["keywords"],
                "circuits": len(lv["exports"]),
                "dependencies": lv["dependencies"],
                "index": f"index/{name}.json",
                "archive": lv["archive"],
                "sha256": lv["sha256"],
            }
        )
    (root / "registry.json").write_text(
        json.dumps(
            {
                "registry_format": 2,
                "name": "Fixture Registry",
                "homepage": "https://example.invalid",
                "packages": registry_pkgs,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture(scope="session")
def file_registry(tmp_path_factory) -> Path:
    """A registry with nands 0.1.0+0.2.0 and adders 0.1.0, on disk."""
    root = tmp_path_factory.mktemp("registry")
    build_registry(root, sorted(FIXTURES.iterdir()))
    return root


@pytest.fixture(scope="session")
def registry_url(file_registry: Path) -> str:
    return file_registry.as_uri()


@pytest.fixture(autouse=True)
def _no_ambient_index(monkeypatch):
    """Tests never resolve against a real index by accident."""
    monkeypatch.delenv("SHDL_INDEX_URL", raising=False)
