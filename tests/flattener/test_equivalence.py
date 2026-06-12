"""Functional equivalence of the two reference evaluators (and oracles).

``BaseEval`` interprets the emitted Base SHDL text; ``HighEval`` independently
interprets the phase-3 model with a different mechanism. Per-cycle trace
agreement over random stimulus is evidence the lowering preserved behavior.
"""

import random

import pytest
from helpers import flatten_fixture

from shdlc.baseshdl import parse_base
from shdlc.sim.base_eval import BaseEval
from flattener.sim.high_eval import HighEval


def make_evals(name, **kw):
    out = flatten_fixture(name, **kw)
    return out, BaseEval(parse_base(out.text)), HighEval(out.mono, out.expanded)


def poke_both(out, base, high, rng):
    values = {}
    for port, wires in out.meta["ports"]["inputs"].items():
        values[port] = rng.randrange(1 << len(wires))
        base.poke(port, values[port])
        high.poke(port, values[port])
    return values


def assert_outputs_agree(out, base, high, context):
    for port in out.meta["ports"]["outputs"]:
        assert base.peek(port) == high.peek(port), (context, port)


# fixture -> oracle(inputs) -> expected outputs, all values LSB-first ints
ORACLES = {
    "fullAdder": lambda v: {
        "Sum": (v["A"] + v["B"] + v["Cin"]) & 1,
        "Cout": (v["A"] + v["B"] + v["Cin"]) >> 1,
    },
    "add2": lambda v: {
        "Sum": (v["A"] + v["B"] + v["Cin"]) & 3,
        "Cout": (v["A"] + v["B"] + v["Cin"]) >> 2,
    },
    "adder8": lambda v: {
        "Sum": (v["A"] + v["B"] + v["Cin"]) & 0xFF,
        "Cout": (v["A"] + v["B"] + v["Cin"]) >> 8,
    },
    "adderN": lambda v: {
        "Sum": (v["A"] + v["B"] + v["Cin"]) & 0xF,
        "Cout": (v["A"] + v["B"] + v["Cin"]) >> 4,
    },
    "alu": lambda v: {
        "Sum": (v["A"] + v["B"]) & 0xF,
        "Cout": (v["A"] + v["B"]) >> 4,
    },
    "add100": lambda v: {
        "Sum": (v["A"] + 100) & 0xFF,
        "Cout": (v["A"] + 100) >> 8,
    },
    "splitByte": lambda v: {"Low": v["In"] & 0xF, "High": v["In"] >> 4},
    "concatDemo": lambda v: {
        "Word": v["In"],
        "Ext": (v["In"] & 3) | (0b1111 << 2 if v["Sign"] else 0),
        "Low": v["In"] & 3,
        "High": v["In"] >> 2,
        "X": (v["In"] & 1) ^ v["Sign"],
    },
    "repeater": lambda v: {
        "Out": (0b111 if v["In"] & 1 else 0) | ((0b111 << 3) if v["In"] & 2 else 0),
    },
    "pipe": lambda v: {"Out": v["In"]},
    "passthru": lambda v: {
        "B": v["A"],
        "C": (v["A"] & 1) ^ (v["A"] >> 1),
    },
    "gatesDemo": lambda v: {
        "Na": 1 - (v["A"] & v["B"]),
        "No": 1 - (v["A"] | v["B"]),
        "Xn": 1 - (v["A"] ^ v["B"]),
    },
    "constDemo": lambda v: {"O1": v["A"], "O2": 0, "O3": 0},
}


@pytest.mark.parametrize("name", sorted(ORACLES))
def test_combinational_equivalence(name):
    out, base, high = make_evals(name)
    depth = out.timing["max_depth"]
    oracle = ORACLES[name]
    rng = random.Random(0)
    for vector in range(8):
        base.reset()
        high.reset()
        values = poke_both(out, base, high, rng)
        # Trace equality on every intermediate cycle, not just at settle.
        for cycle in range(depth + 2):
            assert_outputs_agree(out, base, high, (name, vector, cycle))
            base.step()
            high.step()
        # Functional correctness at (and past) settle depth.
        expected = oracle(values)
        for port, want in expected.items():
            assert base.peek(port) == want, (name, vector, port, values)


def test_add2_exhaustive():
    out, base, high = make_evals("add2")
    for a in range(4):
        for b in range(4):
            for cin in range(2):
                base.reset()
                high.reset()
                for ev in (base, high):
                    ev.poke("A", a)
                    ev.poke("B", b)
                    ev.poke("Cin", cin)
                base.settle()
                high.step(out.timing["max_depth"])
                total = a + b + cin
                assert base.peek("Sum") == high.peek("Sum") == total & 3
                assert base.peek("Cout") == high.peek("Cout") == total >> 2


def test_settle_reaches_fixpoint():
    # One extra step after settle() must not change any output: max_depth is
    # a sufficient propagation bound.
    rng = random.Random(1)
    for name in sorted(ORACLES):
        out, base, high = make_evals(name)
        poke_both(out, base, high, rng)
        base.settle()
        before = {p: base.peek(p) for p in out.meta["ports"]["outputs"]}
        base.step()
        after = {p: base.peek(p) for p in out.meta["ports"]["outputs"]}
        assert before == after, name


def test_settle_refused_under_feedback():
    _, base, _ = make_evals("srlatch")
    with pytest.raises(ValueError):
        base.settle()


def test_srlatch_traces_and_function():
    out, base, high = make_evals("srlatch")
    # Init seeds visible at cycle 0 in both evaluators.
    assert base.peek("Q") == high.peek("Q") == 0
    assert base.peek("Qn") == high.peek("Qn") == 1

    script = [(0, 0)] * 5 + [(1, 0)] * 5 + [(0, 0)] * 5 + [(0, 1)] * 5 + [(0, 0)] * 5
    for cycle, (s, r) in enumerate(script):
        for ev in (base, high):
            ev.poke("S", s)
            ev.poke("R", r)
            ev.step()
        assert_outputs_agree(out, base, high, cycle)
        if cycle == 9:  # S held high for 5 cycles: latch set
            assert (base.peek("Q"), base.peek("Qn")) == (1, 0)
        if cycle == 14:  # back to hold: state retained
            assert (base.peek("Q"), base.peek("Qn")) == (1, 0)
        if cycle == 19:  # R held high: latch reset
            assert (base.peek("Q"), base.peek("Qn")) == (0, 1)
        if cycle == 24:
            assert (base.peek("Q"), base.peek("Qn")) == (0, 1)


def _flatten(tmp_path, source):
    """Flatten an inline program and return (out, BaseEval, HighEval)."""
    from helpers import flatten_source

    out = flatten_source(tmp_path, source)
    return out, BaseEval(parse_base(out.text)), HighEval(out.mono, out.expanded)


def test_flt7_combinational_init_visible_then_overwritten(tmp_path):
    # FLT-7: an init seed on a *combinational* (non-state-holding) wire is
    # visible at cycle 0, then overwritten by the first step (spec §11.4).
    # Here n.O is seeded to 1; once A propagates, Y becomes NOT(A).
    out, base, high = _flatten(
        tmp_path,
        "top component M(A) -> (Y) { n: NOT; init { n.O = 1; } "
        "connect { A -> n.A; n.O -> Y; } }",
    )
    assert out.timing["has_feedback"] is False  # purely combinational
    assert out.meta["init"] == {"Y": 1}
    base.poke("A", 1)
    high.poke("A", 1)
    # Cycle 0: the seed is visible in both evaluators.
    assert base.peek("Y") == high.peek("Y") == 1
    base.step()
    high.step()
    # After the first step the seed is gone, overwritten by NOT(A=1) = 0.
    assert base.peek("Y") == high.peek("Y") == 0


def test_flt8_non_fixed_point_seed_oscillates(tmp_path):
    # FLT-8: a seed that is not a fixed point of the feedback loop oscillates
    # deterministically (tasks/lessons: init must seed a fixed point). A NOT
    # gate fed by its own output, seeded to 0, toggles 0,1,0,1,... — and both
    # independent evaluators agree on the (pinned) oscillation.
    out, base, high = _flatten(
        tmp_path,
        "top component M(A) -> (Y) { n: NOT; init { n.O = 0; } "
        "connect { n.O -> n.A; n.O -> Y; } }",
    )
    assert out.timing["has_feedback"] is True
    base_trace = [base.peek("Y")]
    high_trace = [high.peek("Y")]
    for _ in range(5):
        base.step()
        high.step()
        base_trace.append(base.peek("Y"))
        high_trace.append(high.peek("Y"))
    assert base_trace == [0, 1, 0, 1, 0, 1], base_trace
    assert high_trace == base_trace


def test_rob2_high_eval_poke_overflow_raises(tmp_path):
    # ROB-2: the oracle is *intentionally* stricter than the C ABI — a poke
    # value exceeding the port width raises ValueError rather than masking
    # (the C poke masks modulo 2^width per AMB-2). This asymmetry must never be
    # "fixed" into agreement; pinning it here protects that intent.
    _, base, high = _flatten(
        tmp_path,
        "top component M(A[2]) -> (Y[2]) { connect { A -> Y; } }",
    )
    with pytest.raises(ValueError):
        high.poke("A", 4)  # 4 does not fit a 2-bit port
    with pytest.raises(ValueError):
        base.poke("A", 4)  # BaseEval is equally strict
    # In-range pokes are accepted by both.
    high.poke("A", 3)
    base.poke("A", 3)


def test_clock_ring_traces():
    out, base, high = make_evals("clock")
    assert out.timing["has_feedback"] is True
    # Inject a one-cycle pulse, then let it circulate the 20-stage ring.
    base.poke("clk", 1)
    high.poke("clk", 1)
    for cycle in range(5):
        base.step()
        high.step()
        assert_outputs_agree(out, base, high, ("pulse", cycle))
    base.poke("clk", 0)
    high.poke("clk", 0)
    for cycle in range(50):
        base.step()
        high.step()
        assert_outputs_agree(out, base, high, ("circulate", cycle))
    # The ring is ORs only, so the injected 1s persist and keep cycling.
    assert base.peek("out") != 0
