"""Anti-settling tests: one gate level per cycle, observable carry ripple.

A settling implementation (topological evaluation within one tick) fails by
cycle 1: the intermediate Sum values below would never appear, and Cout would
be 1 immediately.
"""

from __future__ import annotations

import pytest

from .harness import make_oracle

# adder8 with A=0xFF, B=0x01, Cin=0 poked at cycle 0. Per-cycle values of Sum
# and Cout for cycles 0..19, derived from BaseEval (scratch run 2026-06-10).
# timing.max_depth is 17; the carry visibly ripples one stage at a time and
# Cout flips 0 -> 1 between cycle 15 and cycle 16.
ADDER8_SUM_TRACE = [
    0x00, 0x00, 0xFE, 0xFC, 0xFC, 0xF8, 0xF8, 0xF0, 0xF0, 0xE0,
    0xE0, 0xC0, 0xC0, 0x80, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00,
]
ADDER8_COUT_TRACE = [0] * 16 + [1] * 4
ADDER8_COUT_FLIP_CYCLE = 16  # Cout is 0 at cycle 15 and 1 at cycle 16


def test_oracle_adder8_trace_is_pinned(builds):
    """Pure-oracle pinning (passes today): catches BaseEval/fixture drift."""
    oracle = make_oracle(builds.fixture_text("adder8"))
    oracle.poke("A", 0xFF)
    oracle.poke("B", 0x01)
    oracle.poke("Cin", 0)
    sums, couts = [oracle.peek("Sum")], [oracle.peek("Cout")]
    for _ in range(19):
        oracle.step(1)
        sums.append(oracle.peek("Sum"))
        couts.append(oracle.peek("Cout"))
    assert sums == ADDER8_SUM_TRACE
    assert couts == ADDER8_COUT_TRACE


def test_adder8_carry_ripples_one_level_per_cycle(builds):
    dual = builds.dual_fixture("adder8")
    # Cycle 0 before any poke: dirty clear, stored zeros.
    sums = [dual.sim.peek("Sum")]
    couts = [dual.sim.peek("Cout")]
    dual.poke("A", 0xFF)
    dual.poke("B", 0x01)
    dual.poke("Cin", 0)
    for _ in range(19):
        dual.step_compare(1)  # lib vs BaseEval on ALL ports, every cycle
        sums.append(dual.sim.peek("Sum"))
        couts.append(dual.sim.peek("Cout"))
    # The ripple must be visible: at least 8 distinct Sum values.
    assert len(set(sums)) >= 8, f"no visible ripple: {sums}"
    assert couts[ADDER8_COUT_FLIP_CYCLE - 1] == 0
    assert couts[ADDER8_COUT_FLIP_CYCLE] == 1
    # Doubly pinned: full traces as BaseEval-derived literals.
    assert sums == ADDER8_SUM_TRACE
    assert couts == ADDER8_COUT_TRACE


def test_add2_exhaustive_per_cycle(builds):
    """All input combinations of the 2-bit adder, compared per cycle."""
    dual = builds.dual_fixture("add2")
    for a in range(4):
        for b in range(4):
            for cin in (0, 1):
                dual.reset()
                dual.compare_all()
                dual.poke("A", a)
                dual.poke("B", b)
                dual.poke("Cin", cin)
                dual.step_compare(6)  # max_depth is 5; one extra for slack
                # Semantic ground truth, independent of the oracle:
                total = a + b + cin
                assert dual.sim.peek("Sum") == (total & 3), (a, b, cin)
                assert dual.sim.peek("Cout") == (total >> 2), (a, b, cin)


@pytest.mark.parametrize(
    "name,pokes,settled",
    [
        # ALU is AdderN<4> with Cin grounded: 0xB + 0x6 = 0x11.
        ("alu", {"A": 0xB, "B": 0x6}, {"Sum": 0x1, "Cout": 1}),
        # add100 adds the constant 100: 200 + 100 = 300 = 0x12C.
        ("add100", {"A": 200}, {"Sum": 0x2C, "Cout": 1}),
    ],
)
def test_fixpoint_stable_after_max_depth(builds, name, pokes, settled):
    """After timing.max_depth cycles, extra steps must not change outputs."""
    dual = builds.dual_fixture(name)
    depth = dual.comp.meta["timing"]["max_depth"]
    for port, value in pokes.items():
        dual.poke(port, value)
    dual.step_compare(depth)
    snap = {p: dual.sim.peek(p) for p in dual.out_ports}
    assert snap == settled, name  # semantic ground truth at the fixpoint
    for _ in range(3):
        dual.step_compare(1)  # still equal to BaseEval...
        again = {p: dual.sim.peek(p) for p in dual.out_ports}
        assert again == snap, name  # ...and equal to the previous cycle
