"""In-process end-to-end: the full new → add → install → build → test →
remove lifecycle against the file:// fixture registry, plus REPL/search/info."""

from __future__ import annotations

import io
import json
import tomllib

import pytest

from shdl_cli.cli import main

USE_HALFADD = '''\
"""demo — drives the vendored half adder."""

use adders::{HalfAdd};

top component Main(A, B) -> (S, C) {
    ha: HalfAdd;
    connect {
        A -> ha.A;
        B -> ha.B;
        ha.S -> S;
        ha.C -> C;
    }
}
'''

HALFADD_TESTS = """\
{
  "test_format": 1,
  "package": "demo",
  "cases": [
    {
      "component": "Main",
      "steps": 16,
      "vectors": [
        {"in": {"A": 0, "B": 0}, "out": {"S": 0, "C": 0}},
        {"in": {"A": 1, "B": 1}, "out": {"S": 0, "C": 1}}
      ]
    }
  ]
}
"""


@pytest.fixture
def demo(tmp_path, monkeypatch, registry_url):
    # the session-wide way to point at a registry: the env var. A bare
    # --index on 'add' is a one-shot override, and a later plain 'shdl build'
    # would rightly call the lock stale (fingerprints include the registry).
    monkeypatch.setenv("SHDL_INDEX_URL", registry_url)
    monkeypatch.chdir(tmp_path)
    assert main(["new", "demo"]) == 0
    monkeypatch.chdir(tmp_path / "demo")
    return tmp_path / "demo"


def test_full_lifecycle(demo, registry_url, capsys):
    # add: default range = caret of latest; nands vendored transitively at
    # 0.1.0 (adders' ^0.1.0 excludes the newer 0.2.0)
    assert main(["add", "adders"]) == 0
    out = capsys.readouterr().out
    assert "fetched adders 0.1.0" in out
    assert "fetched nands 0.1.0" in out
    assert "added adders ^0.1.0" in out

    doc = tomllib.loads((demo / "shdl.toml").read_text())
    assert doc["dependencies"] == {"adders": "^0.1.0"}
    lock = json.loads((demo / "shdl.lock").read_text())
    assert lock["packages"]["nands"]["version"] == "0.1.0"
    assert (demo / "shdl_modules" / "nands" / "nands.shdl").is_file()

    # frozen install: fresh lock, already vendored -> up to date, no changes
    assert main(["install", "--frozen"]) == 0
    assert "up to date (2 packages)" in capsys.readouterr().out

    # the project actually uses the vendored component
    (demo / "src" / "demo.shdl").write_text(USE_HALFADD)
    (demo / "tests" / "demo.tests.json").write_text(HALFADD_TESTS)
    assert main(["build", "--dev"]) == 0
    assert main(["test", "--dev"]) == 0
    out = capsys.readouterr().out
    assert "ok    Main" in out
    assert "1/1 cases green" in out

    # remove: transitive removal refused, direct removal prunes the tree
    assert main(["remove", "nands"]) == 1
    assert "required by adders" in capsys.readouterr().err
    assert main(["remove", "adders"]) == 0
    doc = tomllib.loads((demo / "shdl.toml").read_text())
    assert doc.get("dependencies", {}) == {}
    assert not (demo / "shdl_modules" / "adders").exists()
    assert not (demo / "shdl_modules" / "nands").exists()


def test_failed_add_leaves_project_untouched(demo, registry_url, capsys):
    toml_before = (demo / "shdl.toml").read_text()
    lock_before = (demo / "shdl.lock").read_text()
    # adders pins nands to ^0.1.0; demanding ^0.2.0 alongside cannot resolve
    assert main(["add", "adders", "nands@^0.2.0"]) == 1
    err = capsys.readouterr().err
    assert "no version of nands satisfies" in err
    assert (demo / "shdl.toml").read_text() == toml_before
    assert (demo / "shdl.lock").read_text() == lock_before
    assert not (demo / "shdl_modules" / "adders").exists()


def test_stale_lock_blocks_build(demo, registry_url, capsys):
    assert main(["add", "adders"]) == 0
    capsys.readouterr()
    # hand-edit shdl.toml behind the lock's back
    toml = demo / "shdl.toml"
    toml.write_text(
        toml.read_text().replace('adders = "^0.1.0"', 'adders = ">=0.1.0"')
    )
    assert main(["build"]) == 1
    assert "stale" in capsys.readouterr().err
    assert main(["install", "--frozen"]) == 1
    assert main(["install"]) == 0


def test_repl_over_stdin(demo, monkeypatch, capsys):
    # the scaffolded Main is an inverter: A=1 -> Y=0
    monkeypatch.setattr(
        "sys.stdin", io.StringIO("poke A 1\nstep 8\npeek Y\ninfo\nbogus\nquit\n")
    )
    assert main(["run", "--dev"]) == 0
    out = capsys.readouterr().out
    assert "0" in out.splitlines()
    assert "inputs:  A" in out
    assert "outputs: Y" in out
    assert "unknown command" in out


def test_search_and_info(registry_url, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # outside any project — both must still work
    assert main(["search", "adder", "--index", registry_url]) == 0
    assert "adders 0.1.0" in capsys.readouterr().out

    assert main(["search", "zzz-no-match", "--index", registry_url]) == 0
    assert "no packages match" in capsys.readouterr().out

    assert main(["info", "nands", "--versions", "--index", registry_url]) == 0
    out = capsys.readouterr().out
    assert "nands 0.2.0" in out
    assert "Inv" in out
    assert "0.2.0 (latest)" in out
    assert "0.1.0" in out


def test_add_at_range_pins_older_version(demo, registry_url, capsys):
    assert main(["add", "nands@^0.1.0"]) == 0
    lock = json.loads((demo / "shdl.lock").read_text())
    assert lock["packages"]["nands"]["version"] == "0.1.0"
    doc = tomllib.loads((demo / "shdl.toml").read_text())
    assert doc["dependencies"]["nands"] == "^0.1.0"


def test_add_path_dependency(demo, registry_url, capsys, tmp_path):
    pkg = tmp_path / "localpkg"
    (pkg / "tests").mkdir(parents=True)
    (pkg / "localpkg.shdl").write_text(
        'component Pass(A) -> (O) {\n    b1: NOT;\n    b2: NOT;\n'
        "    connect {\n        A -> b1.A;\n        b1.O -> b2.A;\n        b2.O -> O;\n    }\n}\n"
    )
    (pkg / "package.json").write_text(
        json.dumps(
            {
                "name": "localpkg",
                "version": "0.1.0",
                "module": "localpkg.shdl",
                "dependencies": {},
                "exports": [{"name": "Pass"}],
                "shdl": ">=1.0.0",
            }
        )
    )
    assert main(["add", "--path", str(pkg)]) == 0
    out = capsys.readouterr().out
    assert "added localpkg path" in out
    lock = json.loads((demo / "shdl.lock").read_text())
    assert lock["packages"]["localpkg"]["source"]["type"] == "path"
    # never vendored — the path dir itself goes on the include path
    assert not (demo / "shdl_modules" / "localpkg").exists()

    (demo / "src" / "demo.shdl").write_text(
        '"""demo."""\n\nuse localpkg::{Pass};\n\n'
        "top component Main(A) -> (Y) {\n    p: Pass;\n"
        "    connect {\n        A -> p.A;\n        p.O -> Y;\n    }\n}\n"
    )
    assert main(["build", "--dev"]) == 0


def test_add_path_with_illegal_name_rejected(demo, capsys, tmp_path):
    pkg = tmp_path / "badname"
    pkg.mkdir()
    (pkg / "badname.shdl").write_text("# x\n")
    (pkg / "package.json").write_text(json.dumps({
        "name": "MyLib", "version": "0.1.0", "module": "badname.shdl",
        "dependencies": {}, "exports": [{"name": "X"}], "shdl": ">=1.0.0",
    }))
    toml_before = (demo / "shdl.toml").read_text()
    assert main(["add", "--path", str(pkg)]) == 1
    assert "must match" in capsys.readouterr().err
    assert (demo / "shdl.toml").read_text() == toml_before  # untouched


def test_unmatched_component_filter_errors(demo, capsys):
    assert main(["test", "--dev", "Main", "NoSuchComp"]) == 1
    assert "NoSuchComp" in capsys.readouterr().err


def test_empty_cases_error(demo, capsys):
    (demo / "tests" / "demo.tests.json").write_text('{"cases": []}')
    assert main(["test"]) == 1
    assert "contain no cases" in capsys.readouterr().err


def test_malformed_case_is_a_fail_not_a_crash(demo, capsys):
    (demo / "tests" / "demo.tests.json").write_text(json.dumps({
        "cases": [
            {"component": "Main", "steps": 8,
             "vectors": [{"in": {"NoSuchSignal": 1}, "out": {"Y": 0}}]},
            {"steps": 8, "vectors": []},
        ]
    }))
    assert main(["test", "--dev"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  Main" in out
    assert "missing 'component'" in out
    assert "0/2 cases green" in out
