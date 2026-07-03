"""shdl.lock round-trips, the manifest fingerprint, and freshness checks."""

from __future__ import annotations

import json

import pytest

from shdl_cli.errors import CliError
from shdl_cli.lockfile import (
    Lock,
    LockedPackage,
    check_fresh,
    manifest_fingerprint,
    read_lock,
    write_lock,
)
from shdl_cli.project import PathDep, Project


def _lock() -> Lock:
    return Lock(
        manifest_fingerprint=manifest_fingerprint({"gates": "^0.1.0"}, "https://x"),
        registry="https://x",
        packages={
            "gates": LockedPackage(
                version="0.1.0",
                source={"type": "registry", "url": "https://x"},
                dependencies={},
                module="gates.shdl",
                exports=["Nand2"],
                sha256="ab" * 32,
            ),
            "local": LockedPackage(
                version="0.2.0",
                source={"type": "path", "path": "../local"},
                dependencies={"gates": "^0.1.0"},
                module="local.shdl",
                exports=["Thing"],
                sha256=None,
            ),
        },
    )


def test_round_trip(tmp_path):
    path = tmp_path / "shdl.lock"
    write_lock(path, _lock())
    back = read_lock(path)
    assert back == _lock()
    doc = json.loads(path.read_text())
    assert doc["lock_format"] == 1
    assert "sha256" not in doc["packages"]["local"]  # path deps carry no sha
    assert doc["packages"]["gates"]["sha256"] == "ab" * 32


def test_missing_lock_reads_none(tmp_path):
    assert read_lock(tmp_path / "shdl.lock") is None


def test_malformed_lock_errors(tmp_path):
    path = tmp_path / "shdl.lock"
    path.write_text("{not json")
    with pytest.raises(CliError, match="invalid JSON"):
        read_lock(path)
    path.write_text('{"lock_format": 99}')
    with pytest.raises(CliError, match="unsupported lock_format"):
        read_lock(path)
    path.write_text('{"lock_format": 1, "packages": {}}')
    with pytest.raises(CliError, match="malformed lock"):
        read_lock(path)


def test_fingerprint_sensitivity():
    base = manifest_fingerprint({"a": "^1.0.0"}, "https://x")
    assert base.startswith("sha256:")
    assert base == manifest_fingerprint({"a": "^1.0.0"}, "https://x")  # stable
    assert base != manifest_fingerprint({"a": "^1.0.1"}, "https://x")  # range change
    assert base != manifest_fingerprint({"b": "^1.0.0"}, "https://x")  # name change
    assert base != manifest_fingerprint({"a": "^1.0.0"}, "https://y")  # registry change
    assert base != manifest_fingerprint({"a": PathDep("^1.0.0")}, "https://x")  # kind change


def test_fingerprint_order_independent():
    a = manifest_fingerprint({"a": "^1.0.0", "b": "^2.0.0"}, "https://x")
    b = manifest_fingerprint({"b": "^2.0.0", "a": "^1.0.0"}, "https://x")
    assert a == b


def _project(tmp_path, deps) -> Project:
    return Project(
        root=tmp_path,
        name="demo",
        version="0.1.0",
        main="src/demo.shdl",
        top=None,
        shdl=None,
        dependencies=deps,
        registry_url=None,
    )


def test_check_fresh(tmp_path):
    project = _project(tmp_path, {"gates": "^0.1.0"})
    with pytest.raises(CliError, match="no shdl.lock"):
        check_fresh(project, "https://x")
    write_lock(project.lock_path, _lock())
    assert check_fresh(project, "https://x").registry == "https://x"
    with pytest.raises(CliError, match="stale"):
        check_fresh(project, "https://other")  # registry changed
    with pytest.raises(CliError, match="stale"):
        check_fresh(_project(tmp_path, {"gates": "^0.2.0"}), "https://x")
