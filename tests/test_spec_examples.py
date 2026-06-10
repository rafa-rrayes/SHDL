"""Conformance against the worked examples in base_shdl.md.

§3.7 fixes only the *set* of gates and connections, not their order
(declaration order is explicitly an implementation choice), so the
comparison is order-insensitive.
"""

from helpers import flatten_fixture

from shdlc.baseshdl import parse_base

# base_shdl.md §3.7, verbatim.
SPEC_3_7 = """
component Add2(A_1_, A_2_, B_1_, B_2_, Cin) -> (Sum_1_, Sum_2_, Cout) {
    fa1_x1: XOR;
    fa1_x2: XOR;
    fa1_a1: AND;
    fa1_a2: AND;
    fa1_o1: OR;

    fa2_x1: XOR;
    fa2_x2: XOR;
    fa2_a1: AND;
    fa2_a2: AND;
    fa2_o1: OR;

    connect {
        A_1_ -> fa1_x1.A;
        B_1_ -> fa1_x1.B;
        A_1_ -> fa1_a1.A;
        B_1_ -> fa1_a1.B;
        fa1_x1.O -> fa1_x2.A;
        Cin -> fa1_x2.B;
        fa1_x1.O -> fa1_a2.A;
        Cin -> fa1_a2.B;
        fa1_a1.O -> fa1_o1.A;
        fa1_a2.O -> fa1_o1.B;
        fa1_x2.O -> Sum_1_;

        A_2_ -> fa2_x1.A;
        B_2_ -> fa2_x1.B;
        A_2_ -> fa2_a1.A;
        B_2_ -> fa2_a1.B;
        fa2_x1.O -> fa2_x2.A;
        fa1_o1.O -> fa2_x2.B;
        fa2_x1.O -> fa2_a2.A;
        fa1_o1.O -> fa2_a2.B;
        fa2_a1.O -> fa2_o1.A;
        fa2_a2.O -> fa2_o1.B;
        fa2_x2.O -> Sum_2_;
        fa2_o1.O -> Cout;
    }
}
"""


def test_add2_matches_spec_3_7():
    spec = parse_base(SPEC_3_7)
    ours = parse_base(flatten_fixture("add2").text)
    assert ours.name == spec.name
    assert ours.inputs == spec.inputs
    assert ours.outputs == spec.outputs
    assert ours.gates == spec.gates
    assert set(ours.connections) == set(spec.connections)
    assert len(ours.connections) == len(spec.connections)


def test_fa1_hierarchy_ports_match_spec_4_4():
    out = flatten_fixture("add2")
    fa1 = out.meta["hierarchy"]["Add2"]["instances"]["fa1"]
    assert fa1["type"] == "FullAdder"
    assert fa1["prefix"] == "fa1_"
    assert fa1["ports"] == {
        "A": "A_1_", "B": "B_1_", "Cin": "Cin",
        "Sum": "Sum_1_", "Cout": "fa1_o1.O",
    }
    assert {k: v["type"] for k, v in fa1["instances"].items()} == {
        "x1": "XOR", "x2": "XOR", "a1": "AND", "a2": "AND", "o1": "OR",
    }


def test_add2_stats():
    # §4.9 quotes "total_connections": 22 for Add2, but the spec's own §3.7
    # listing contains 23 connections; 23 is correct.
    out = flatten_fixture("add2")
    spec = parse_base(SPEC_3_7)
    assert len(spec.connections) == 23
    assert out.meta["stats"] == {
        "total_gates": 10,
        "total_connections": 23,
        "total_ports": 8,
        "by_type": {"XOR": 4, "AND": 4, "OR": 2},
    }


def test_add2_timing_matches_resolved_4_7():
    # §4.7's example numbers are internally inconsistent; the prose model
    # (input depth 0, gate depth = 1 + max over inputs) gives these values.
    t = flatten_fixture("add2").timing
    assert t["max_depth"] == 5
    assert t["output_depths"] == {"Sum_1_": 2, "Sum_2_": 4, "Cout": 5}
