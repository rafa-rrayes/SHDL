import json

from helpers import FIXTURES, flatten_fixture

from shdlc.baseshdl import parse_base

ALL_TOPS = sorted(p.stem for p in FIXTURES.glob("*.shdl") if p.stem != "stdgates")


def test_add2_exact_layout():
    out = flatten_fixture("add2")
    lines = out.text.splitlines()
    assert lines[0] == (
        "component Add2(A_1_, A_2_, B_1_, B_2_, Cin) -> (Sum_1_, Sum_2_, Cout) {"
    )
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
        assert comp.gates == {
            g.name: g.type_name for g in netlist.gates.values()
        }, name
        assert len(comp.connections) == len(netlist.connections), name
        assert comp.meta == json.loads(json.dumps(out.meta)), name
