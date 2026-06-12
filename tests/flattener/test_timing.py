from helpers import FIXTURES, flatten_fixture

from flattener.phases.flatten import node_str

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


# ── TIM-5 (tightness half): step(max_depth−1) may differ from the fixpoint ──
# Sufficiency (step(max_depth) == fixpoint) is already covered. Tightness
# proves the bound is not loose: for add2 the deepest output (Cout, depth 5 =
# max_depth) needs the full carry ripple, so on at least one input transition
# step(max_depth−1) still differs from the settled value. Without this, a
# max_depth reported one too large would pass the sufficiency test silently.

def test_settle_bound_is_tight_on_add2_cout():
    # TIM-5
    from shdlc.baseshdl import parse_base
    from shdlc.sim.base_eval import BaseEval

    out = flatten_fixture("add2")
    md = out.timing["max_depth"]
    assert out.timing["output_depths"]["Cout"] == md  # Cout is the deepest
    comp = parse_base(out.text)

    # Settle A=0,B=0,Cin=0, then transition to A=0,B=3,Cin=1 — a carry that
    # must ripple the whole chain. (Seed-stable: a fixed, hand-found vector.)
    def cout_after(steps: int) -> int:
        ev = BaseEval(comp)
        ev.poke("A", 0); ev.poke("B", 0); ev.poke("Cin", 0)
        ev.settle()
        ev.poke("A", 0); ev.poke("B", 3); ev.poke("Cin", 1)
        ev.step(steps)
        return ev.peek("Cout")

    def fixpoint() -> int:
        ev = BaseEval(comp)
        ev.poke("A", 0); ev.poke("B", 0); ev.poke("Cin", 0)
        ev.settle()
        ev.poke("A", 0); ev.poke("B", 3); ev.poke("Cin", 1)
        ev.settle()
        return ev.peek("Cout")

    fp = fixpoint()
    # sufficiency: max_depth steps reach the fixpoint
    assert cout_after(md) == fp, (md, cout_after(md), fp)
    # tightness: one fewer step does NOT — the bound is exact on this input
    assert cout_after(md - 1) != fp, (
        f"step(max_depth-1={md - 1}) already matched the fixpoint {fp}: "
        "max_depth is not tight on the add2 Cout carry path"
    )


# ── TIM-6: feedback-circuit timing content (srlatch, ring) ──────────────────
# Under feedback, max_depth is the feedback-free shell only and the critical
# path may start at a feedback gate or a power pin rather than an input wire.
# Pin the exact per-output depths and the critical path on the two minimal
# feedback fixtures.

def test_srlatch_timing_content_pinned():
    # TIM-6: critical_path starts at a feedback gate (the NOR's NOT), not input.
    out = flatten_fixture("srlatch")
    t = out.timing
    assert t["has_feedback"] is True
    assert t["is_combinational"] is False
    assert t["max_depth"] == 1  # feedback-free shell
    assert t["output_depths"] == {"Q": 1, "Qn": 1}
    # Q is driven directly by n1_n1.O (the gate inside the SCC); the path is
    # exactly that gate then the output wire — it does NOT start at S or R.
    assert t["critical_path"] == ["n1_n1", "Q"]
    assert t["critical_path"][0] not in out.flat.netlist.inputs
    assert_real_edge_path(out)


def test_ring_oscillator_timing_content_pinned():
    # TIM-6: ring (clock) — every output at shell depth 1, path from the input.
    out = flatten_fixture("clock")
    t = out.timing
    assert t["has_feedback"] is True
    assert t["is_combinational"] is False
    assert t["max_depth"] == 1  # feedback-free shell
    # all 20 stage outputs sit at shell depth 1
    assert set(t["output_depths"].values()) == {1}
    assert len(t["output_depths"]) == 20
    # out_1_ is driven one gate after the clk input feeds o1.
    assert t["critical_path"] == ["clk", "o1", "out_1_"]
    assert_real_edge_path(out)


# ── TIM-7: degenerate timing blocks ─────────────────────────────────────────
# A zero-output top and a power-pin-driven output: both flatten to specific,
# live-verified timing values that nothing currently pins.

def test_zero_output_top_has_empty_timing(tmp_path):
    # TIM-7
    from helpers import flatten_source

    out = flatten_source(
        tmp_path,
        "component Sink(A) -> () {\n"
        "    g: AND;\n"
        "    connect { A -> g.A;  A -> g.B; }\n"
        "}\n",
    )
    t = out.timing
    assert t["max_depth"] == 0
    assert t["output_depths"] == {}
    assert t["critical_path"] == []
    assert t["is_combinational"] is True
    assert t["has_feedback"] is False


def test_power_pin_output_has_depth_one(tmp_path):
    # TIM-7: ONE[1] -> Y, a constant 1 wired straight to an output.
    from helpers import flatten_source

    out = flatten_source(
        tmp_path,
        "component PinOut() -> (Y) {\n"
        "    ONE = 1;\n"
        "    connect { ONE[1] -> Y; }\n"
        "}\n",
    )
    t = out.timing
    # The single gate is the __VCC__ power pin feeding Y; pins have depth 1.
    assert t["max_depth"] == 1
    assert t["output_depths"] == {"Y": 1}
    assert t["critical_path"] == ["ONE_bit1", "Y"]
    # The path starts at the power-pin gate, not at any input wire.
    assert t["critical_path"][0] not in out.flat.netlist.inputs
    assert_real_edge_path(out)
