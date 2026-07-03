"""Scaffolding: the generated project is complete, refuses clobbering, and
actually builds and tests green through the real pipeline."""

from __future__ import annotations

import tomllib

import pytest

from shdl_cli.cli import main
from shdl_cli.errors import CliError
from shdl_cli.scaffold import create_project


def test_create_project_files(tmp_path):
    files = create_project(tmp_path / "demo", "demo")
    assert set(files) == {
        "shdl.toml",
        "src/demo.shdl",
        "tests/demo.tests.json",
        ".gitignore",
        "README.md",
        "shdl.lock",
    }
    doc = tomllib.loads((tmp_path / "demo" / "shdl.toml").read_text())
    assert doc["project"] == {
        "name": "demo",
        "version": "0.1.0",
        "main": "src/demo.shdl",
        "top": "Main",
        "shdl": ">=1.0.0",
    }
    assert doc["dependencies"] == {}
    gitignore = (tmp_path / "demo" / ".gitignore").read_text()
    assert "shdl_modules/" in gitignore and "build/" in gitignore


@pytest.mark.parametrize("bad", ["Demo", "1demo", "demo-x", "demo x", ""])
def test_bad_project_names(tmp_path, bad):
    with pytest.raises(CliError, match="must match"):
        create_project(tmp_path / "p", bad)


def test_refuses_existing_project(tmp_path):
    create_project(tmp_path / "demo", "demo")
    with pytest.raises(CliError, match="already exists"):
        create_project(tmp_path / "demo", "demo", into_existing=True)


def test_refuses_nonempty_dir_without_init(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "junk.txt").write_text("x")
    with pytest.raises(CliError, match="not empty"):
        create_project(tmp_path / "demo", "demo")


def test_init_into_nonempty_dir(tmp_path):
    (tmp_path / "junk.txt").write_text("x")
    create_project(tmp_path, "demo", into_existing=True)
    assert (tmp_path / "shdl.toml").is_file()
    assert (tmp_path / "junk.txt").read_text() == "x"


def test_init_refuses_overwrite(tmp_path):
    (tmp_path / "README.md").write_text("mine")
    with pytest.raises(CliError, match="refusing to overwrite: README.md"):
        create_project(tmp_path, "demo", into_existing=True)
    assert (tmp_path / "README.md").read_text() == "mine"


def test_scaffold_builds_and_tests_green(tmp_path, monkeypatch, capsys):
    create_project(tmp_path / "demo", "demo")
    monkeypatch.chdir(tmp_path / "demo")
    assert main(["build", "--dev"]) == 0
    assert main(["test", "--dev"]) == 0
    out = capsys.readouterr().out
    assert "built" in out
    assert "1/1 cases green" in out
