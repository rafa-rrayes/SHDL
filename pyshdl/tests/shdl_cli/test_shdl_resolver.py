"""Resolution: fixpoint (with downgrades), conflicts, collisions, path deps."""

from __future__ import annotations

import json

import pytest

from shdl_cli.errors import CliError
from shdl_cli.project import PathDep, Project
from shdl_cli.resolver import resolve
from shdl_cli.semver import Version


def entry(module: str, deps: dict | None = None, exports: tuple[str, ...] = (),
          shdl: str = ">=1.0.0") -> dict:
    return {
        "dependencies": deps or {},
        "module": module,
        "exports": [{"name": n} for n in exports],
        "sha256": "00" * 32,
        "shdl": shdl,
    }


class FakeIndex:
    index_url = "https://fake.invalid"

    def __init__(self, packages: dict[str, dict[str, dict]]):
        self._packages = packages

    def versions(self, name: str) -> dict[Version, dict]:
        if name not in self._packages:
            raise CliError(f"package {name!r} not found in the index (fake)")
        return {Version.parse(v): e for v, e in self._packages[name].items()}


@pytest.fixture(autouse=True)
def _stable_toolchain(monkeypatch):
    monkeypatch.setattr("importlib.metadata.version", lambda dist: "1.1.0")


def project(tmp_path, deps) -> Project:
    (tmp_path / "src").mkdir(exist_ok=True)
    return Project(
        root=tmp_path,
        name="app",
        version="0.1.0",
        main="src/app.shdl",
        top=None,
        shdl=None,
        dependencies=deps,
        registry_url=None,
    )


NANDS_TWO_VERSIONS = {
    "nands": {
        "0.1.0": entry("nands.shdl", exports=("Nand2",)),
        "0.2.0": entry("nands.shdl", exports=("Nand2", "Inv")),
    },
    "adders": {
        "0.1.0": entry("adders.shdl", deps={"nands": "^0.1.0"}, exports=("HalfAdd",)),
    },
}


def test_highest_satisfying_version(tmp_path):
    lock = resolve(project(tmp_path, {"nands": ">=0.1.0"}), FakeIndex(NANDS_TWO_VERSIONS))
    assert lock.packages["nands"].version == "0.2.0"
    assert lock.packages["nands"].exports == ["Nand2", "Inv"]
    assert lock.packages["nands"].source == {"type": "registry", "url": "https://fake.invalid"}


def test_fixpoint_downgrade(tmp_path):
    # nands alone would pick 0.2.0; adders' ^0.1.0 (discovered after nands is
    # chosen) must pull it back down — the one-pass-is-unsound case.
    lock = resolve(
        project(tmp_path, {"nands": ">=0.1.0", "adders": "^0.1.0"}),
        FakeIndex(NANDS_TWO_VERSIONS),
    )
    assert lock.packages["nands"].version == "0.1.0"
    assert lock.packages["adders"].version == "0.1.0"


def test_transitive_deps_pulled_in(tmp_path):
    lock = resolve(project(tmp_path, {"adders": "^0.1.0"}), FakeIndex(NANDS_TWO_VERSIONS))
    assert set(lock.packages) == {"adders", "nands"}
    assert lock.packages["nands"].version == "0.1.0"
    assert lock.manifest_fingerprint.startswith("sha256:")


def test_conflict_names_every_requirer(tmp_path):
    with pytest.raises(CliError) as exc:
        resolve(
            project(tmp_path, {"nands": "^0.2.0", "adders": "^0.1.0"}),
            FakeIndex(NANDS_TWO_VERSIONS),
        )
    msg = str(exc.value)
    assert "no version of nands satisfies" in msg
    assert "^0.2.0 (required by shdl.toml)" in msg
    assert "^0.1.0 (required by adders 0.1.0)" in msg
    assert "available: 0.2.0, 0.1.0" in msg


def test_unknown_package(tmp_path):
    with pytest.raises(CliError, match="not found"):
        resolve(project(tmp_path, {"ghost": "^1.0.0"}), FakeIndex(NANDS_TWO_VERSIONS))


def test_module_collision_between_packages(tmp_path):
    packages = {
        "aaa": {"0.1.0": entry("shared.shdl", exports=("A",))},
        "bbb": {"0.1.0": entry("shared.shdl", exports=("B",))},
    }
    with pytest.raises(CliError, match="module name collision.*aaa and bbb"):
        resolve(project(tmp_path, {"aaa": "^0.1.0", "bbb": "^0.1.0"}), FakeIndex(packages))


def test_export_collision_between_packages(tmp_path):
    packages = {
        "aaa": {"0.1.0": entry("aaa.shdl", exports=("Same",))},
        "bbb": {"0.1.0": entry("bbb.shdl", exports=("Same",))},
    }
    with pytest.raises(CliError, match="component name collision.*'Same'"):
        resolve(project(tmp_path, {"aaa": "^0.1.0", "bbb": "^0.1.0"}), FakeIndex(packages))


def test_project_module_shadows_package(tmp_path):
    p = project(tmp_path, {"nands": "^0.1.0"})
    (tmp_path / "src" / "nands.shdl").write_text("# shadow\n")
    with pytest.raises(CliError, match="the project's nands.shdl shadows"):
        resolve(p, FakeIndex(NANDS_TWO_VERSIONS))


def _write_path_dep(tmp_path, name="local", version="0.1.0", deps=None):
    pdir = tmp_path / name
    pdir.mkdir()
    (pdir / f"{name}.shdl").write_text("# module\n")
    (pdir / "package.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "module": f"{name}.shdl",
                "dependencies": deps or {},
                "exports": [{"name": "LocalThing"}],
                "shdl": ">=1.0.0",
            }
        )
    )
    return pdir


def test_path_dep_feeds_the_resolver(tmp_path):
    _write_path_dep(tmp_path, deps={"nands": "^0.1.0"})
    lock = resolve(
        project(tmp_path, {"local": PathDep("local")}),
        FakeIndex(NANDS_TWO_VERSIONS),
    )
    assert lock.packages["local"].source == {"type": "path", "path": "local"}
    assert lock.packages["local"].sha256 is None
    assert lock.packages["nands"].version == "0.1.0"  # constrained by the path dep


def test_path_dep_must_satisfy_constraints(tmp_path):
    _write_path_dep(tmp_path, version="0.1.0")
    packages = {
        "wants": {"0.1.0": entry("wants.shdl", deps={"local": "^0.5.0"}, exports=("W",))},
    }
    with pytest.raises(CliError, match=r"path dependency local 0.1.0 does not satisfy"):
        resolve(
            project(tmp_path, {"local": PathDep("local"), "wants": "^0.1.0"}),
            FakeIndex(packages),
        )


def test_path_dep_name_mismatch(tmp_path):
    _write_path_dep(tmp_path, name="local")
    with pytest.raises(CliError, match="must match"):
        resolve(
            project(tmp_path, {"other": PathDep("local")}),
            FakeIndex(NANDS_TWO_VERSIONS),
        )


def test_toolchain_skew_is_fatal(tmp_path):
    packages = {"old": {"0.1.0": entry("old.shdl", exports=("O",), shdl="<1.0.0")}}
    with pytest.raises(CliError, match=r"pyshdl 1.1.0 does not satisfy.*old 0.1.0"):
        resolve(project(tmp_path, {"old": "^0.1.0"}), FakeIndex(packages))


def test_missing_toolchain_metadata_warns_and_skips(tmp_path, monkeypatch, capsys):
    import importlib.metadata as md

    def boom(dist):
        raise md.PackageNotFoundError(dist)

    monkeypatch.setattr("importlib.metadata.version", boom)
    lock = resolve(project(tmp_path, {"nands": "^0.1.0"}), FakeIndex(NANDS_TWO_VERSIONS))
    assert lock.packages["nands"].version == "0.1.0"
    assert "skipping toolchain-compatibility" in capsys.readouterr().err


def test_vendored_tree_is_not_a_project_module(tmp_path):
    # main at the project ROOT (legal): the module scan must not sweep
    # shdl_modules/, or every re-resolution after the first vendoring would
    # report the vendored package as a project-module collision.
    p = Project(
        root=tmp_path,
        name="app",
        version="0.1.0",
        main="app.shdl",
        top=None,
        shdl=None,
        dependencies={"nands": "^0.1.0"},
        registry_url=None,
    )
    (tmp_path / "app.shdl").write_text("# main\n")
    vendored = tmp_path / "shdl_modules" / "nands"
    vendored.mkdir(parents=True)
    (vendored / "nands.shdl").write_text("# vendored\n")
    lock = resolve(p, FakeIndex(NANDS_TWO_VERSIONS))
    assert lock.packages["nands"].version == "0.1.0"
    # and a second resolution (the re-resolve path) still works
    assert resolve(p, FakeIndex(NANDS_TWO_VERSIONS)).packages["nands"].version == "0.1.0"


def test_undeclared_path_dep_module_collides(tmp_path):
    # an undeclared .shdl file in a path-dep dir is on the include path and
    # shadows same-named registry modules — the guard must see it
    pdir = _write_path_dep(tmp_path)
    (pdir / "nands.shdl").write_text("# undeclared shadow\n")
    with pytest.raises(CliError, match="module name collision.*nands.shdl"):
        resolve(
            project(tmp_path, {"local": PathDep("local"), "nands": "^0.1.0"}),
            FakeIndex(NANDS_TWO_VERSIONS),
        )
