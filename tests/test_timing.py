from helpers import FIXTURES, flatten_fixture

from shdlc.phases.flatten import node_str

ALL_FIXTURE_TOPS = sorted(p.stem for p in FIXTURES.glob("*.shdl") if p.stem != "stdgates")


def assert_real_edge_path(out):
    """Every adjacent pair in critical_path must be an actual connection."""
    path = out.timing["critical_path"]
    if not path:
        return
    edges = set()
    for s, d, _ in out.flat.netlist.connections:
        src = s[1] if s[0] == "in" else s[1]  # wire or gate name
        dst = d[1] if d[0] == "out" else d[1]
        edges.add((src, dst))
    for a, b in zip(path, path[1:]):
        assert (a, b) in edges, f"{a} -> {b} is not a real edge ({node_str}, {path})"
    assert path[-1] in out.flat.netlist.outputs


def test_add2_timing_exact():
    out = flatten_fixture("add2")
    t = out.timing
    assert t["max_depth"] == 5
    assert t["output_depths"] == {"Sum_1_": 2, "Sum_2_": 4, "Cout": 5}
    assert t["is_combinational"] is True
    assert t["has_feedback"] is False
    assert t["critical_path"] == [
        "A_1_", "fa1_x1", "fa1_a2", "fa1_o1", "fa2_a2", "fa2_o1", "Cout"
    ]


def test_adder8_ripple_depth():
    out = flatten_fixture("adder8")
    t = out.timing
    assert t["max_depth"] == 17  # carry chain: 3 + 2 per extra stage
    assert t["output_depths"]["Sum_1_"] == 2
    assert t["output_depths"]["Sum_8_"] == 16
    assert t["output_depths"]["Cout"] == 17


def test_power_pins_have_depth_one():
    out = flatten_fixture("constDemo")
    # a1 is fed by FIVE_bit1 (a power pin, depth 1) and input A (depth 0).
    assert out.timing["output_depths"] == {"O1": 2, "O2": 2, "O3": 2}
    assert out.timing["max_depth"] == 2


def test_feedback_detected_and_shell_depth():
    for name in ("clock", "srlatch"):
        out = flatten_fixture(name)
        t = out.timing
        assert t["has_feedback"] is True
        assert t["is_combinational"] is False
        assert t["max_depth"] == 1  # feedback-free shell only


def test_pass_through_outputs_have_depth_zero():
    out = flatten_fixture("splitByte")
    t = out.timing
    assert t["max_depth"] == 0
    assert set(t["output_depths"].values()) == {0}
    assert t["critical_path"] == ["In_1_", "Low_1_"]


def test_critical_path_is_real_everywhere():
    for name in ALL_FIXTURE_TOPS:
        out = flatten_fixture(name)
        assert_real_edge_path(out)
        # And its length matches the claimed depth: depth gates + endpoints,
        # except when the path starts at a depth-carrying gate (power pin or
        # feedback gate) rather than at an input wire.
        path = out.timing["critical_path"]
        if path and path[0] in out.flat.netlist.inputs:
            assert len(path) == out.timing["max_depth"] + 2


def test_settle_counts_match_functional_need():
    # max_depth steps after a poke must fully propagate any input change.
    from shdlc.baseshdl import parse_base
    from shdlc.sim.base_eval import BaseEval

    out = flatten_fixture("add100")
    ev = BaseEval(parse_base(out.text))
    ev.poke("A", 55)
    ev.settle()
    assert ev.peek("Sum") == (55 + 100) & 0xFF
    assert ev.peek("Cout") == 0
    ev.poke("A", 200)
    ev.settle()
    assert ev.peek("Sum") == (200 + 100) & 0xFF
    assert ev.peek("Cout") == 1
