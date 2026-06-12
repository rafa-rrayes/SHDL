"""step_settle / run_batch: the additive batch-and-settle ABI entries.

The contract for both is *observable equivalence* to the scalar ABI:
``step_settle(n)`` may skip only ticks that provably change nothing (gate
state at a fixed point with inputs held), and ``run_batch`` must behave
exactly like the equivalent poke/step/peek sequence — including lazy-peek
(dirty) semantics. Twin fresh instances of the same library are driven in
lockstep, one through each path, and compared at every observation point.
"""

from __future__ import annotations

import random

import pytest

#: Single NOT gate feeding itself: a period-2 oscillator. Never reaches a
#: fixed point, so step_settle must always run its full budget on it.
OSC_TEXT = """\
component HandOsc() -> (q) {
    g: NOT;
    connect { g.O -> g.A; g.O -> q; }
}
meta { "ports": { "inputs": {}, "outputs": { "q": ["q"] } } }
"""

ADD2_PORTS = ("A", "B", "Cin", "Sum", "Cout")


# --- step_settle ------------------------------------------------------------


def test_step_settle_matches_step_under_random_drive(builds):
    plain = builds.sim_fixture("add2")
    settled = builds.sim_fixture("add2")
    rng = random.Random(0xBA7C4)
    for sim in (plain, settled):
        sim.reset()
    for _ in range(200):
        for port, width in (("A", 2), ("B", 2), ("Cin", 1)):
            if rng.random() < 0.7:
                v = rng.getrandbits(width)
                plain.poke(port, v)
                settled.poke(port, v)
        n = rng.randint(0, 6)
        plain.step(n)
        ran = settled.step_settle(n)
        assert 0 <= ran <= n
        for port in ADD2_PORTS:
            assert plain.peek(port) == settled.peek(port)


def test_step_settle_early_exit_and_return_values(builds):
    sim = builds.sim_fixture("add2")
    sim.reset()
    sim.poke("A", 3)
    sim.poke("B", 1)
    sim.poke("Cin", 0)
    ran = sim.step_settle(100)
    assert 0 < ran < 100  # settled well inside the budget
    assert (sim.peek("Sum"), sim.peek("Cout")) == (0, 1)  # 3 + 1 = 0b100
    # Already at a fixed point: exactly one (identity) tick proves it.
    assert sim.step_settle(100) == 1
    # <= 0 cycles is a no-op, exactly like step(<= 0).
    assert sim.step_settle(0) == 0
    assert sim.step_settle(-3) == 0


def test_step_settle_zero_preserves_lazy_peek(builds):
    plain = builds.sim_fixture("add2")
    settled = builds.sim_fixture("add2")
    for sim in (plain, settled):
        sim.reset()
        sim.poke("A", 1)
        sim.poke("B", 2)
        sim.poke("Cin", 0)
    plain.step(0)
    assert settled.step_settle(0) == 0
    # Both still dirty: the first output peek hidden-ticks exactly once.
    assert plain.peek("Sum") == settled.peek("Sum")
    assert plain.peek("Cout") == settled.peek("Cout")
    plain.step(1)
    assert settled.step_settle(1) == 1
    assert plain.peek("Sum") == settled.peek("Sum")


def test_step_settle_oscillator_runs_full_budget(builds):
    plain = builds.sim_from_text("hand_osc", OSC_TEXT)
    settled = builds.sim_from_text("hand_osc", OSC_TEXT)
    for sim in (plain, settled):
        sim.reset()
    for budget in (1, 2, 5, 36, 37):
        plain.step(budget)
        assert settled.step_settle(budget) == budget  # never a fixed point
        assert plain.peek("q") == settled.peek("q")


# --- run_batch ---------------------------------------------------------------


@pytest.mark.parametrize("settle", [False, True])
def test_run_batch_matches_scalar_sequence(builds, settle):
    batch = builds.sim_fixture("add2")
    scalar = builds.sim_fixture("add2")
    rng = random.Random(0xF00D if settle else 0xFEED)
    frames = [(rng.getrandbits(2), rng.getrandbits(2), rng.getrandbits(1)) for _ in range(50)]
    # Mid-settle budget on purpose: results must match the scalar sequence
    # even when `cycles` is too small for the circuit to have settled.
    for cycles in (3, 20):
        for sim in (batch, scalar):
            sim.reset()
        got = batch.run_batch(frames, 2, cycles, settle=settle)
        for frame, outs in zip(frames, got):
            for port, v in zip(("A", "B", "Cin"), frame):
                scalar.poke(port, v)
            scalar.step(cycles)
            assert outs == (scalar.peek("Sum"), scalar.peek("Cout"))
        # dirty state matches afterwards: the next peek hidden-ticks (or
        # not) identically on both paths.
        assert batch.peek("Sum") == scalar.peek("Sum")


def test_run_batch_cycles_zero_uses_lazy_peek(builds):
    batch = builds.sim_fixture("add2")
    scalar = builds.sim_fixture("add2")
    for sim in (batch, scalar):
        sim.reset()
    frames = [(1, 2, 0), (3, 3, 1), (0, 0, 0)]
    got = batch.run_batch(frames, 2, 0)
    for frame, outs in zip(frames, got):
        for port, v in zip(("A", "B", "Cin"), frame):
            scalar.poke(port, v)
        # No step: the first peek of an output hidden-ticks exactly once.
        assert outs == (scalar.peek("Sum"), scalar.peek("Cout"))


def test_run_batch_count_zero_is_a_noop(builds):
    sim = builds.sim_fixture("add2")
    sim.reset()
    sim.poke("A", 1)
    before = sim.peek("A")
    assert sim.run_batch([], 2, 10) == []
    assert sim.peek("A") == before


def test_run_batch_no_input_ports_oscillator(builds):
    """Zero-width frames drive a no-input circuit; settle mode must still
    run the exact budget on an oscillator (5 ticks/frame: q flips)."""
    sim = builds.sim_from_text("hand_osc", OSC_TEXT)
    sim.reset()
    got = sim.run_batch([(), (), ()], 1, 5, settle=True)
    # q after 5, 10, 15 ticks: parity 1, 0, 1.
    assert got == [(1,), (0,), (1,)]
