"""IndexClient over file:// + the vendor tree: fetch, verify, extract, prune."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile

import pytest

from shdl_cli import vendor
from shdl_cli.errors import CliError
from shdl_cli.index_client import (
    DEFAULT_INDEX,
    IndexClient,
    resolve_index_url,
)
from shdl_cli.lockfile import Lock, LockedPackage
from shdl_cli.project import Project
from shdl_cli.semver import Version


# --- URL precedence -----------------------------------------------------------
def test_index_url_precedence(monkeypatch):
    monkeypatch.delenv("SHDL_INDEX_URL", raising=False)
    assert resolve_index_url(None, None) == DEFAULT_INDEX
    assert resolve_index_url(None, "https://proj/") == "https://proj"
    monkeypatch.setenv("SHDL_INDEX_URL", "https://env")
    assert resolve_index_url(None, "https://proj") == "https://env"
    assert resolve_index_url("https://flag", "https://proj") == "https://flag"


# --- fetching the two index levels ---------------------------------------------
def test_registry_and_package_index(registry_url):
    client = IndexClient(registry_url)
    reg = client.registry()
    assert [p["name"] for p in reg["packages"]] == ["adders", "nands"]
    assert client.registry_entry("nands")["version"] == "0.2.0"  # latest inlined

    idx = client.package_index("nands")
    assert idx["latest"] == "0.2.0"
    assert set(idx["versions"]) == {"0.1.0", "0.2.0"}
    versions = client.versions("nands")
    assert Version.parse("0.1.0") in versions
    assert versions[Version.parse("0.2.0")]["module"] == "nands.shdl"


def test_unknown_package_errors(registry_url):
    with pytest.raises(CliError, match="'ghost' not found in the index"):
        IndexClient(registry_url).registry_entry("ghost")


def test_unreachable_index_errors(tmp_path):
    with pytest.raises(CliError, match="index fetch failed"):
        IndexClient((tmp_path / "nowhere").as_uri()).registry()


def test_bad_registry_format(tmp_path):
    (tmp_path / "registry.json").write_text('{"registry_format": 1, "packages": []}')
    with pytest.raises(CliError, match="unsupported registry_format"):
        IndexClient(tmp_path.as_uri()).registry()


# --- archives -------------------------------------------------------------------
def _locked(client: IndexClient, name: str) -> LockedPackage:
    entry = client.registry_entry(name)
    idx = client.package_index(name)
    v = idx["versions"][entry["version"]]
    return LockedPackage(
        version=entry["version"],
        source={"type": "registry", "url": client.index_url},
        dependencies=v["dependencies"],
        module=v["module"],
        exports=[e["name"] for e in v["exports"]],
        sha256=v["sha256"],
    )


def test_download_archive_verifies_sha(registry_url):
    client = IndexClient(registry_url)
    locked = _locked(client, "nands")
    blob = client.download_archive("nands", locked.version, locked.sha256)
    assert hashlib.sha256(blob).hexdigest() == locked.sha256
    with pytest.raises(CliError, match="sha256 mismatch.*refusing to unpack"):
        client.download_archive("nands", locked.version, "0" * 64)


def test_archive_url_layout(registry_url):
    client = IndexClient(registry_url)
    assert client.archive_url("nands", "0.1.0") == f"{registry_url}/archives/nands-0.1.0.tar.gz"


# --- the vendor tree -------------------------------------------------------------
def _project(tmp_path) -> Project:
    return Project(
        root=tmp_path,
        name="app",
        version="0.1.0",
        main="src/app.shdl",
        top=None,
        shdl=None,
        dependencies={},
        registry_url=None,
    )


def _lock_for(client: IndexClient, names: list[str]) -> Lock:
    return Lock(
        manifest_fingerprint="sha256:test",
        registry=client.index_url,
        packages={n: _locked(client, n) for n in names},
    )


def test_sync_fetches_prunes_and_is_idempotent(tmp_path, registry_url):
    project = _project(tmp_path)
    client = IndexClient(registry_url)
    lock = _lock_for(client, ["nands", "adders"])

    stray = project.modules_dir / "stray"
    stray.mkdir(parents=True)
    (stray / "junk.txt").write_text("x")

    lines = vendor.sync(project, lock, client)
    assert any("fetched nands 0.2.0" in line for line in lines)
    assert any("fetched adders 0.1.0" in line for line in lines)
    assert any("removed stray" in line for line in lines)
    assert (project.modules_dir / "nands" / "nands.shdl").is_file()
    assert (project.modules_dir / "nands" / "package.json").is_file()
    assert not stray.exists()

    assert vendor.sync(project, lock, client) == []  # idempotent
    vendor.verify_vendored(project, lock)  # and satisfies the preflight

    dirs = vendor.include_dirs(project, lock)
    assert dirs == sorted(
        [str(project.modules_dir / "adders"), str(project.modules_dir / "nands")]
    )


def test_sync_replaces_stale_vendored_dir(tmp_path, registry_url):
    project = _project(tmp_path)
    client = IndexClient(registry_url)
    lock = _lock_for(client, ["nands"])

    fake = project.modules_dir / "nands"
    fake.mkdir(parents=True)
    (fake / "package.json").write_text('{"name": "nands", "version": "0.0.1"}')
    (fake / "leftover.txt").write_text("junk that must not survive the swap")

    lines = vendor.sync(project, lock, client)
    assert any("fetched nands" in line for line in lines)
    assert not (fake / "leftover.txt").exists()
    assert json.loads((fake / "package.json").read_text())["version"] == "0.2.0"


def test_verify_vendored_demands_install(tmp_path, registry_url):
    project = _project(tmp_path)
    client = IndexClient(registry_url)
    lock = _lock_for(client, ["nands"])
    with pytest.raises(CliError, match="run 'shdl install'"):
        vendor.verify_vendored(project, lock)


class _EvilClient:
    """Serves a syntactically valid archive whose members escape the prefix."""

    index_url = "https://evil.invalid"

    def __init__(self, member_name: str):
        tar_buf = io.BytesIO()
        with tarfile.open(mode="w", fileobj=tar_buf) as tar:
            data = b"pwned"
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(tar_buf.getvalue())
        self.blob = buf.getvalue()
        self.sha256 = hashlib.sha256(self.blob).hexdigest()

    def download_archive(self, name, version, sha256):
        return self.blob


@pytest.mark.parametrize("member", ["../evil.txt", "other-0.1.0/file", "nands-0.1.0/../../up"])
def test_malicious_archive_rejected(tmp_path, member):
    project = _project(tmp_path)
    client = _EvilClient(member)
    lock = Lock(
        manifest_fingerprint="sha256:test",
        registry=client.index_url,
        packages={
            "nands": LockedPackage(
                version="0.1.0",
                source={"type": "registry", "url": client.index_url},
                dependencies={},
                module="nands.shdl",
                exports=["Nand2"],
                sha256=client.sha256,
            )
        },
    )
    with pytest.raises(CliError, match="unexpected member|refusing"):
        vendor.sync(project, lock, client)
    assert not (project.modules_dir / "nands").exists()


def test_stray_file_in_modules_dir_recovers(tmp_path, registry_url):
    # a regular file squatting on a package's directory name (or a .tmp- leftover)
    # must be cleared by sync, not crash it
    project = _project(tmp_path)
    client = IndexClient(registry_url)
    lock = _lock_for(client, ["nands"])
    project.modules_dir.mkdir(parents=True)
    (project.modules_dir / "nands").write_text("not a directory")
    (project.modules_dir / ".tmp-nands").write_text("leftover")
    lines = vendor.sync(project, lock, client)
    assert any("fetched nands" in line for line in lines)
    assert (project.modules_dir / "nands" / "package.json").is_file()
    assert not (project.modules_dir / ".tmp-nands").exists()
    vendor.verify_vendored(project, lock)


def test_schemeless_index_url_rejected():
    with pytest.raises(CliError, match="must start with"):
        IndexClient("rafa-rrayes.github.io/CCircus")
