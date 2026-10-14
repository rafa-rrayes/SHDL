import json

from helpers import FIXTURES, flatten_fixture, flatten_source

from shdlc.baseshdl import parse_base

ALL_TOPS = sorted(p.stem for p in FIXTURES.glob("*.shdl") if p.stem != "stdgates")


def test_add2_exact_layout():
    out = flatten_fixture("add2")
    lines = out.text.splitlines()
    assert lines[0] == ("component Add2(A_1_, A_2_, B_1_, B_2_, Cin) -> (Sum_1_, Sum_2_, Cout) {")
    assert lines[1] == "    fa1_x1: XOR;"
    assert lines[11] == ""  # blank line between declarations and connect
    assert lines[12] == "    connect {"
    assert lines[13] == "        A_1_ -> fa1_x1.A;"
    assert out.text.endswith("\n")
    assert not out.text.endswith("\n\n")


def test_gateless_component_has_no_declaration_section():
    out = flatten_fixture("splitByte")
    lines = out.text.splitlines()
    assert lines[0].startswith("component SplitByte(")
    assert lines[1] == "    connect {"


def test_meta_round_trips_as_json():
    out = flatten_fixture("add2")
    comp = parse_base(out.text)
    assert comp.meta == json.loads(json.dumps(out.meta))


def test_every_fixture_reparses_faithfully():
    for name in ALL_TOPS:
        out = flatten_fixture(name)
        comp = parse_base(out.text)
        netlist = out.flat.netlist
        assert comp.name == netlist.name, name
        assert comp.inputs == netlist.inputs, name
        assert comp.outputs == netlist.outputs, name
        assert comp.gates == {g.name: g.type_name for g in netlist.gates.values()}, name
        assert len(comp.connections) == len(netlist.connections), name
        assert comp.meta == json.loads(json.dumps(out.meta)), name


# ── DET-6 (round-trip half): non-ASCII doc text is raw UTF-8 and survives ───
# emit uses json.dumps(..., ensure_ascii=False), so a non-ASCII docstring is
# emitted as literal UTF-8 (not \uXXXX escapes) and must round-trip through
# shdlc.parse_base byte-for-byte. The bare-stdout locale half lives in
# test_determinism.py (it needs a subprocess). DET-6's `²` is also the LEX-9
# crash character, exercised here purely as doc text.

_NON_ASCII_DOC = "Café — ½ adder ² λ 中文 ✓"


def test_non_ascii_doc_emitted_as_raw_utf8(tmp_path):
    # DET-6
    out = flatten_source(
        tmp_path,
        f'"""{_NON_ASCII_DOC}"""\ncomponent Main(A) -> (Y) {{\n    connect {{ A -> Y; }}\n}}\n',
    )
    assert out.meta["doc"]["description"] == _NON_ASCII_DOC
    # Raw UTF-8 in the emitted text, never \u escapes.
    assert _NON_ASCII_DOC in out.text
    assert "\\u" not in out.text


def test_non_ascii_doc_round_trips_through_parse_base(tmp_path):
    # DET-6
    out = flatten_source(
        tmp_path,
        f'"""{_NON_ASCII_DOC}"""\ncomponent Main(A) -> (Y) {{\n    connect {{ A -> Y; }}\n}}\n',
    )
    comp = parse_base(out.text)
    assert comp.meta["doc"]["description"] == _NON_ASCII_DOC
    assert comp.meta == json.loads(json.dumps(out.meta))
