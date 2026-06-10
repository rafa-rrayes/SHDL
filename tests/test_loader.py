from helpers import TS, expect_error, flatten_source

from flattener.diagnostics import ErrorCode, SHDLError
from flattener.pipeline import flatten_program

INV = "component Inv(A) -> (O) { n: NOT; connect { A -> n.A; n.O -> O; } }"
MAIN = (
    "use lib::{Inv};\n"
    "top component M(X) -> (Y) { i1: Inv; connect { X -> i1.A; i1.O -> Y; } }"
)


def test_import_resolution(tmp_path):
    out = flatten_source(tmp_path, MAIN, aux={"lib": INV})
    assert "i1_n" in out.flat.netlist.gates


def test_include_dirs(tmp_path):
    libdir = tmp_path / "libs"
    libdir.mkdir()
    (libdir / "lib.shdl").write_text(INV)
    srcdir = tmp_path / "src"
    srcdir.mkdir()
    main = srcdir / "main.shdl"
    main.write_text(MAIN)
    out = flatten_program(str(main), include_dirs=[str(libdir)], timestamp=TS)
    assert "i1_n" in out.flat.netlist.gates


def test_importing_file_directory_searched_first(tmp_path):
    # A lib.shdl next to the importing file shadows one in an -I directory.
    other = tmp_path / "other"
    other.mkdir()
    (other / "lib.shdl").write_text(
        "component Inv(A) -> (O) { n1: NOT; n2: NOT; connect "
        "{ A -> n1.A; n1.O -> n2.A; n2.O -> O; } }"
    )
    out = flatten_source(
        tmp_path, MAIN, aux={"lib": INV}, include_dirs=[str(other)]
    )
    assert list(out.flat.netlist.gates) == ["i1_n"]


def test_missing_module(tmp_path):
    expect_error("E0701", tmp_path, "use nope::{X};\n" + MAIN.split("\n")[1])


def test_missing_name_in_module(tmp_path):
    d = expect_error("E0703", tmp_path, "use lib::{Nope};\n", aux={"lib": INV})
    assert "Nope" in d.message


def test_circular_import(tmp_path):
    a = "use b::{B};\ncomponent A(X) -> (Y) { connect { X -> Y; } }"
    b = "use a::{A};\ncomponent B(X) -> (Y) { connect { X -> Y; } }"
    d = expect_error("E0702", tmp_path, "use a::{A};\n" + MAIN.split("\n")[1], aux={"a": a, "b": b})
    assert "->" in d.message  # cycle chain is spelled out


def test_imported_name_collides_with_local(tmp_path):
    src = "use lib::{Inv};\n" + INV + "\n"
    expect_error("E0301", tmp_path, src, aux={"lib": INV})


def test_main_file_missing(tmp_path):
    import pytest

    with pytest.raises(SHDLError) as ei:
        flatten_program(str(tmp_path / "ghost.shdl"), timestamp=TS)
    assert ei.value.diagnostic.code is ErrorCode.E0701
