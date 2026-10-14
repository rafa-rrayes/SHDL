"""shdl.toml textual edits: byte preservation and the reparse-assert abort."""

from __future__ import annotations

import tomllib

import pytest

from shdl_cli.errors import CliError
from shdl_cli.project import PathDep, edit_dependencies, load_project

BASE = """\
# my project — this comment must survive every edit
[project]
name = "demo"            # trailing comment
version = "0.1.0"
main = "src/demo.shdl"

[dependencies]
gates = "^0.1.0"   # keep my gates
seq = { path = "../seq" }

[registry]
url = "https://example.invalid"
"""


@pytest.fixture
def toml_file(tmp_path):
    f = tmp_path / "shdl.toml"
    f.write_text(BASE, encoding="utf-8")
    return f


def test_add_inserts_and_preserves_bytes(toml_file):
    edit_dependencies(toml_file, add={"arith": "^0.2.0"})
    text = toml_file.read_text(encoding="utf-8")
    assert "# my project — this comment must survive every edit" in text
    assert 'gates = "^0.1.0"   # keep my gates' in text  # untouched, byte for byte
    assert 'arith = "^0.2.0"' in text
    doc = tomllib.loads(text)
    assert doc["dependencies"] == {
        "gates": "^0.1.0",
        "seq": {"path": "../seq"},
        "arith": "^0.2.0",
    }
    # inserted inside [dependencies], not after [registry]
    assert text.index("arith =") < text.index("[registry]")


def test_add_replaces_existing_line(toml_file):
    edit_dependencies(toml_file, add={"gates": "^0.3.0"})
    text = toml_file.read_text(encoding="utf-8")
    assert 'gates = "^0.3.0"' in text
    assert "keep my gates" not in text  # the line was replaced wholesale
    assert tomllib.loads(text)["dependencies"]["gates"] == "^0.3.0"


def test_add_path_dep(toml_file):
    edit_dependencies(toml_file, add={"local": PathDep("../local")})
    doc = tomllib.loads(toml_file.read_text(encoding="utf-8"))
    assert doc["dependencies"]["local"] == {"path": "../local"}


def test_remove_deletes_only_that_line(toml_file):
    edit_dependencies(toml_file, remove={"gates"})
    text = toml_file.read_text(encoding="utf-8")
    assert "gates" not in tomllib.loads(text)["dependencies"]
    assert "seq = { path" in text
    assert "[registry]" in text


def test_remove_missing_errors(toml_file):
    with pytest.raises(CliError, match="not a dependency"):
        edit_dependencies(toml_file, remove={"nope"})


def test_creates_table_when_absent(tmp_path):
    f = tmp_path / "shdl.toml"
    f.write_text('[project]\nname = "x"\nversion = "0.1.0"\nmain = "src/x.shdl"\n')
    edit_dependencies(f, add={"gates": "^0.1.0"})
    doc = tomllib.loads(f.read_text(encoding="utf-8"))
    assert doc["dependencies"] == {"gates": "^0.1.0"}


def test_unhandled_shape_aborts_untouched(tmp_path):
    # top-level dotted-key dependencies (before any table header) — the only
    # textual patch available (append a [dependencies] table) would redefine
    # the table; the editor must refuse and leave the file byte-identical.
    f = tmp_path / "shdl.toml"
    original = (
        'dependencies.gates = "^0.1.0"\n'
        '[project]\nname = "x"\nversion = "0.1.0"\nmain = "src/x.shdl"\n'
    )
    f.write_text(original, encoding="utf-8")
    with pytest.raises(CliError, match="edit shdl.toml by hand"):
        edit_dependencies(f, add={"arith": "^0.1.0"})
    assert f.read_text(encoding="utf-8") == original


def test_edit_keeps_project_loadable(toml_file, tmp_path):
    (tmp_path / "src").mkdir(exist_ok=True)
    edit_dependencies(toml_file, add={"arith": "^0.2.0"}, remove={"seq"})
    project = load_project(tmp_path)
    assert project.dependencies == {"gates": "^0.1.0", "arith": "^0.2.0"}


def test_crlf_file_keeps_its_line_endings(tmp_path):
    f = tmp_path / "shdl.toml"
    f.write_bytes(BASE.replace("\n", "\r\n").encode())
    edit_dependencies(f, add={"arith": "^0.2.0"})
    raw = f.read_bytes()
    assert b"gates = \"^0.1.0\"   # keep my gates\r\n" in raw  # untouched line intact
    assert b'arith = "^0.2.0"\r\n' in raw  # new line matches the file's style
    assert tomllib.loads(raw.decode())["dependencies"]["arith"] == "^0.2.0"


def test_insert_after_posix_incomplete_final_line(tmp_path):
    f = tmp_path / "shdl.toml"
    f.write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\nmain = "src/x.shdl"\n'
        '[dependencies]\ngates = "^0.1.0"',  # no trailing newline
        encoding="utf-8",
    )
    edit_dependencies(f, add={"arith": "^0.1.0"})
    doc = tomllib.loads(f.read_text(encoding="utf-8"))
    assert doc["dependencies"] == {"gates": "^0.1.0", "arith": "^0.1.0"}
