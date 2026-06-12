import pytest
from helpers import TS, expect_error, flatten_source

from flattener.diagnostics import ErrorCode, SHDLError
from flattener.loader import load_program
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


# --------------------------------------------------------------------------- #
# Local helpers (owned by this file) for the multi-directory import tests.
# --------------------------------------------------------------------------- #


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _load_err(main_path, **kw):
    with pytest.raises(SHDLError) as ei:
        load_program(str(main_path), **kw)
    d = ei.value.diagnostic
    assert d.pos.line >= 1 and d.pos.col >= 1, d
    return d


# --- IMP-4: diamond import (D loaded once, not circular) ---------------------


def test_imp4_diamond_loads_shared_module_once(tmp_path):
    # IMP-4: A→B→D and A→C→D is legal; D is loaded exactly once.
    _write(tmp_path / "D.shdl", "component D(A) -> (O) { connect { A -> O; } }")
    _write(
        tmp_path / "B.shdl",
        "use D::{D};\ncomponent B(A) -> (O) { d: D; connect { A -> d.A; d.O -> O; } }",
    )
    _write(
        tmp_path / "C.shdl",
        "use D::{D};\ncomponent C(A) -> (O) { d: D; connect { A -> d.A; d.O -> O; } }",
    )
    main = _write(
        tmp_path / "main.shdl",
        "use B::{B};\nuse C::{C};\n"
        "top component M(A) -> (O) { b: B; c: C; "
        "connect { A -> b.A; b.O -> c.A; c.O -> O; } }",
    )
    prog = load_program(str(main))
    assert sorted(prog.modules) == ["B", "C", "D", "main"]
    # D appears once in the module table — the diamond did not re-load or flag
    # it circular (an E0702 would have raised).
    assert list(prog.modules).count("D") == 1


# --- IMP-5: self-import, primitive import, use-after-definition --------------


def test_imp5_self_import_is_circular(tmp_path):
    # IMP-5: a module importing itself is a cycle (E0702).
    main = _write(
        tmp_path / "self.shdl",
        "use self::{X};\ncomponent X(A) -> (O) { connect { A -> O; } }",
    )
    assert _load_err(main).code is ErrorCode.E0702


def test_imp5_importing_a_primitive_name_is_e0703(tmp_path):
    # IMP-5 + AMB-25: primitive names are built in; a module cannot define or
    # export them, so `use lib::{AND}` is E0703 ('does not define').
    _write(tmp_path / "lib.shdl", "component W(A) -> (O) { connect { A -> O; } }")
    main = _write(
        tmp_path / "main.shdl",
        "use lib::{AND};\ntop component M(A, B) -> (O) { g: AND; "
        "connect { A -> g.A; B -> g.B; g.O -> O; } }",
    )
    assert _load_err(main).code is ErrorCode.E0703


def test_imp5_use_after_component_definition_is_e0201(tmp_path):
    # IMP-5: imports must precede definitions; a trailing `use` → E0201.
    _write(tmp_path / "lib.shdl", "component W(A) -> (O) { connect { A -> O; } }")
    main = _write(
        tmp_path / "main.shdl",
        "top component M(A) -> (O) { connect { A -> O; } }\nuse lib::{W};",
    )
    assert _load_err(main).code is ErrorCode.E0201


# --- IMP-7: no transitive re-export -----------------------------------------


def test_imp7_no_transitive_reexport(tmp_path):
    # IMP-7 + AMB-26: a imports X from b, but b only *imports* X from c (X is
    # defined in c). The origin check rejects this — no re-exports (E0703).
    _write(tmp_path / "c.shdl", "component X(A) -> (O) { connect { A -> O; } }")
    _write(
        tmp_path / "b.shdl",
        "use c::{X};\ncomponent B(A) -> (O) { connect { A -> O; } }",
    )
    main = _write(
        tmp_path / "a.shdl",
        "use b::{X};\ntop component A(A) -> (O) { connect { A -> O; } }",
    )
    d = _load_err(main)
    assert d.code is ErrorCode.E0703
    assert "X" in d.message


# --- IMP-8: import-import collisions -----------------------------------------


def test_imp8_cross_module_import_collision(tmp_path):
    # IMP-8: `use a::{X}; use b::{X};` → E0301.
    _write(tmp_path / "a.shdl", "component X(A) -> (O) { connect { A -> O; } }")
    _write(tmp_path / "b.shdl", "component X(A) -> (O) { connect { A -> O; } }")
    main = _write(
        tmp_path / "main.shdl",
        "use a::{X};\nuse b::{X};\n"
        "top component M(A) -> (O) { connect { A -> O; } }",
    )
    assert _load_err(main).code is ErrorCode.E0301


def test_imp8_duplicate_name_within_one_import_list(tmp_path):
    # IMP-8: `use a::{X, X};` → E0301 (the same collision site).
    _write(tmp_path / "a.shdl", "component X(A) -> (O) { connect { A -> O; } }")
    main = _write(
        tmp_path / "main.shdl",
        "use a::{X, X};\ntop component M(A) -> (O) { connect { A -> O; } }",
    )
    assert _load_err(main).code is ErrorCode.E0301


# --- IMP-9: -I precedence (earlier dir wins) --------------------------------


def test_imp9_earlier_include_dir_wins(tmp_path):
    # IMP-9: with two -I dirs both holding lib.shdl, the earlier one is used.
    _write(
        tmp_path / "first" / "lib.shdl",
        "component W(A) -> (O) { n1: NOT; connect { A -> n1.A; n1.O -> O; } }",
    )
    _write(
        tmp_path / "second" / "lib.shdl",
        "component W(A) -> (O) { n1: NOT; n2: NOT; "
        "connect { A -> n1.A; n1.O -> n2.A; n2.O -> O; } }",
    )
    main = _write(
        tmp_path / "main.shdl",
        "use lib::{W};\ntop component M(A) -> (O) { w: W; "
        "connect { A -> w.A; w.O -> O; } }",
    )
    prog = load_program(
        str(main),
        include_dirs=[str(tmp_path / "first"), str(tmp_path / "second")],
    )
    # The first dir's W has a single NOT; the second's has two.
    assert len(prog.modules["lib"].components[0].decls) == 1


# --- IMP-10: --top overrides a top-marker (a contract) ----------------------


def test_imp10_explicit_top_overrides_marker(tmp_path):
    # IMP-10: `--top A1` wins over a `top`-marked B1; the marker is the default
    # only when --top is absent.
    src = (
        "component A1(X) -> (Y) { connect { X -> Y; } }\n"
        "top component B1(X) -> (Y) { connect { X -> Y; } }"
    )
    out_default = flatten_source(tmp_path, src, name="m")
    assert out_default.flat.netlist.name == "B1"  # marker is the default
    out_override = flatten_source(tmp_path, src, name="m", top="A1")
    assert out_override.flat.netlist.name == "A1"  # --top overrides it


# --- IMP-11 / AMB-28: module-name case on case-insensitive filesystems -------


def test_imp11_module_name_case_mismatch_is_e0701(tmp_path):
    # IMP-11 + AMB-28: `use Add2Lib` against add2lib.shdl is rejected on every
    # platform — via a case-mismatch E0701 on APFS/NTFS, via not-found E0701 on
    # case-sensitive filesystems. Either way: E0701, platform-independent.
    _write(
        tmp_path / "add2lib.shdl",
        "component Inv(A) -> (O) { n: NOT; connect { A -> n.A; n.O -> O; } }",
    )
    main = _write(
        tmp_path / "main.shdl",
        "use Add2Lib::{Inv};\ntop component M(X) -> (Y) { i: Inv; "
        "connect { X -> i.A; i.O -> Y; } }",
    )
    assert _load_err(main).code is ErrorCode.E0701


def test_imp11_exact_case_still_loads(tmp_path):
    # IMP-11: the correct case continues to resolve (no regression).
    _write(
        tmp_path / "add2lib.shdl",
        "component Inv(A) -> (O) { n: NOT; connect { A -> n.A; n.O -> O; } }",
    )
    main = _write(
        tmp_path / "main.shdl",
        "use add2lib::{Inv};\ntop component M(X) -> (Y) { i: Inv; "
        "connect { X -> i.A; i.O -> Y; } }",
    )
    prog = load_program(str(main))
    assert "add2lib" in prog.modules


# --- AMB-27: module identity by resolved path -------------------------------


def test_amb27_same_name_two_files_is_e0701(tmp_path):
    # AMB-27: a bare module name is program-global. If `use shared` resolves to
    # two *different* files from two importers, that ambiguity is an error, not
    # a silent first-one-wins bind.
    _write(
        tmp_path / "b" / "shared.shdl",
        "component W(A) -> (O) { connect { A -> O; } }",
    )
    _write(
        tmp_path / "b" / "b.shdl",
        "use shared::{W};\ncomponent B(A) -> (O) { connect { A -> O; } }",
    )
    _write(
        tmp_path / "c" / "shared.shdl",
        "component W(A) -> (O) { connect { A -> O; } }",
    )
    _write(
        tmp_path / "c" / "c.shdl",
        "use shared::{W};\ncomponent C(A) -> (O) { connect { A -> O; } }",
    )
    main = _write(
        tmp_path / "main.shdl",
        "use b::{B};\nuse c::{C};\n"
        "top component M(A) -> (O) { connect { A -> O; } }",
    )
    d = _load_err(
        main,
        include_dirs=[str(tmp_path / "b"), str(tmp_path / "c")],
    )
    assert d.code is ErrorCode.E0701
    assert "two different files" in d.message
