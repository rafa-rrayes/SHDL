"""Per-gate truth tables, cycle-by-cycle, including the cycle-0 zeros.

The handwritten constants are first self-checked against BaseEval (those
tests pass today, with no compiled library involved); the compiled library is
then held to the same pinned, BaseEval-derived values.
"""

from __future__ import annotations

import pytest

from .harness import (
    GND_TEXT,
    HANDWRITTEN,
    NOT_TEXT,
    VCC_NOT_TEXT,
    VCC_TEXT,
    make_oracle,
)

# Truth tables after step(1) from a fresh reset, keyed (a, b) -> y.
# Derived from BaseEval (scratch run 2026-06-10); also re-derived live below.
TWO_INPUT_TRUTH = {
    "hand_and": {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 1},
    "hand_or": {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 1},
    "hand_xor": {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 0},
}
NOT_TRUTH = {0: 1, 1: 0}

# Derived from BaseEval: VCC is *not* pre-loaded — it reads 0 at cycle 0 and
# 1 from cycle 1 on (shdlc_goals.md §2.4).
VCC_TRACE = [0, 1, 1, 1, 1]
# Derived from BaseEval: the NOT sees VCC's previous-cycle value, so the
# chain output is 0, then 1 (NOT of cycle-0 zero), then 0 forever.
VCC_NOT_TRACE = [0, 1, 0, 0, 0, 0, 0]
GND_TRACE = [0, 0, 0, 0, 0]

# gatesDemo fixture (NAND/NOR/XNOR from stdgates, depth 2), after step(2)
# from a fresh reset. Derived from BaseEval: (A, B) -> (Na, No, Xn).
GATESDEMO_TRUTH = {
    (0, 0): (1, 1, 1),
    (0, 1): (1, 0, 0),
    (1, 0): (1, 0, 0),
    (1, 1): (0, 0, 1),
}


# --------------------------------------------------------------------------
# Oracle self-checks: pure BaseEval, no compiled library. These pass today
# and pin the harness constants against the reference semantics.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(HANDWRITTEN))
def test_handwritten_constant_selfchecks_against_baseeval(name):
    oracle = make_oracle(HANDWRITTEN[name])
    ports = oracle.comp.meta["ports"]
    # Cycle 0: everything reads 0 (no handwritten constant has init seeds).
    for port in (*ports["inputs"], *ports["outputs"]):
        assert oracle.peek(port) == 0, (name, port)
    # Poke all-ones (masked to width) and run a few cycles without exception.
    for port, wires in ports["inputs"].items():
        oracle.poke(port, (1 << len(wires)) - 1)
    oracle.step(5)
    for port in (*ports["inputs"], *ports["outputs"]):
        oracle.peek(port)
    oracle.reset()
    for port in (*ports["inputs"], *ports["outputs"]):
        assert oracle.peek(port) == 0, (name, port)


@pytest.mark.parametrize("name", sorted(TWO_INPUT_TRUTH))
def test_oracle_two_input_truth_tables(name):
    oracle = make_oracle(HANDWRITTEN[name])
    for (a, b), want in TWO_INPUT_TRUTH[name].items():
        oracle.reset()
        oracle.poke("a", a)
        oracle.poke("b", b)
        assert oracle.peek("y") == 0  # cycle 0: stored zero
        oracle.step(1)
        assert oracle.peek("y") == want, (name, a, b)


def test_oracle_traces():
    for text, trace in [
        (VCC_TEXT, VCC_TRACE),
        (VCC_NOT_TEXT, VCC_NOT_TRACE),
        (GND_TEXT, GND_TRACE),
    ]:
        oracle = make_oracle(text)
        got = [oracle.peek("y")]
        for _ in range(len(trace) - 1):
            oracle.step(1)
            got.append(oracle.peek("y"))
        assert got == trace
    oracle = make_oracle(NOT_TEXT)
    for a, want in NOT_TRUTH.items():
        oracle.reset()
        oracle.poke("a", a)
        assert oracle.peek("y") == 0
        oracle.step(1)
        assert oracle.peek("y") == want


# --------------------------------------------------------------------------
# Compiled library vs the same pinned values (and a live BaseEval).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TWO_INPUT_TRUTH))
def test_lib_two_input_gate_truth_table(builds, name):
    sim = builds.sim_from_text(name, HANDWRITTEN[name])
    oracle = make_oracle(HANDWRITTEN[name])
    for (a, b), want in TWO_INPUT_TRUTH[name].items():
        sim.reset()
        oracle.reset()
        # True cycle 0: dirty is clear (no poke since reset), so this peek
        # must NOT tick and must return the stored zero.
        assert sim.peek("y") == 0, (name, a, b)
        sim.poke("a", a)
        sim.poke("b", b)
        oracle.poke("a", a)
        oracle.poke("b", b)
        sim.step(1)
        oracle.step(1)
        got = sim.peek("y")
        assert got == oracle.peek("y") == want, (name, a, b)
        sim.step(1)
        oracle.step(1)
        assert sim.peek("y") == oracle.peek("y") == want, (name, a, b)


def test_lib_not_truth_table_and_cycle_zero(builds):
    sim = builds.sim_from_text("hand_not", NOT_TEXT)
    # Fresh load: the constructor ran reset; the stored state is zero and
    # dirty is clear. A pre-settled implementation would show NOT(0)=1 here.
    assert sim.peek("y") == 0
    oracle = make_oracle(NOT_TEXT)
    for a, want in NOT_TRUTH.items():
        sim.reset()
        oracle.reset()
        assert sim.peek("y") == 0  # kills settling implementations
        sim.poke("a", a)
        oracle.poke("a", a)
        sim.step(1)
        oracle.step(1)
        assert sim.peek("y") == oracle.peek("y") == want


@pytest.mark.parametrize(
    "key,text,trace",
    [
        ("hand_vcc", VCC_TEXT, VCC_TRACE),
        ("hand_vcc_not", VCC_NOT_TEXT, VCC_NOT_TRACE),
        ("hand_gnd", GND_TEXT, GND_TRACE),
    ],
    ids=["hand_vcc", "hand_vcc_not", "hand_gnd"],
)
def test_lib_constant_traces(builds, key, text, trace):
    sim = builds.sim_from_text(key, text)
    oracle = make_oracle(text)
    got = [sim.peek("y")]  # cycle 0: dirty clear, no hidden tick
    for _ in range(len(trace) - 1):
        sim.step(1)
        oracle.step(1)
        got.append(sim.peek("y"))
        assert got[-1] == oracle.peek("y")
    assert got == trace


def test_lib_gatesdemo_composed_gates(builds):
    dual = builds.dual_fixture("gatesDemo")
    for (a, b), (na, no, xn) in GATESDEMO_TRUTH.items():
        dual.reset()
        dual.compare_all()
        dual.poke("A", a)
        dual.poke("B", b)
        dual.step_compare(2)  # depth 2 (timing.max_depth)
        assert dual.sim.peek("Na") == na, (a, b)
        assert dual.sim.peek("No") == no, (a, b)
        assert dual.sim.peek("Xn") == xn, (a, b)
