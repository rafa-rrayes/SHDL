"""Lazy-peek (dirty flag) semantics.

Tick counting uses the clock fixture with clk held at 1: the ring fills like
a thermometer, so out == 2**n - 1 after exactly n evaluation cycles
(BaseEval-derived: 0x0, 0x1, 0x3, 0x7, ... from cycle 0). Any extra or
missing hidden tick is therefore directly visible in the peeked value.

add2 with A=1, B=2, Cin=0 (BaseEval-derived): Sum reads 0 at cycle 1 and 3
from cycle 2 on — distinguishing "exactly one hidden tick" from zero or two.
"""

from __future__ import annotations

from .harness import AND_TEXT, make_oracle


def test_first_peek_after_poke_ticks_exactly_once_add2(builds):
    sim = builds.sim_fixture("add2")
    oracle = make_oracle(builds.fixture_text("add2"))
    for port, v in [("A", 1), ("B", 2), ("Cin", 0)]:
        sim.poke(port, v)
        oracle.poke(port, v)
    oracle.step(1)  # the oracle has no lazy tick: step explicitly
    # First peek: exactly one hidden evaluation (cycle-1 value, BaseEval: 0).
    assert sim.peek("Sum") == oracle.peek("Sum") == 0
    # Dirty was cleared by that tick: further peeks read the same cycle.
    assert sim.peek("Cout") == oracle.peek("Cout") == 0
    assert sim.peek("Sum") == 0  # second peek identical, state unchanged
    # The hidden tick counted as cycle 1: one explicit step lands on cycle 2.
    sim.step(1)
    oracle.step(1)
    assert sim.peek("Sum") == oracle.peek("Sum") == 3
    assert sim.peek("Cout") == oracle.peek("Cout") == 0


def test_first_peek_after_poke_ticks_exactly_once_handwritten_and(builds):
    sim = builds.sim_from_text("hand_and", AND_TEXT)
    oracle = make_oracle(AND_TEXT)
    sim.poke("a", 1)
    sim.poke("b", 1)
    oracle.poke("a", 1)
    oracle.poke("b", 1)
    oracle.step(1)
    assert sim.peek("y") == oracle.peek("y") == 1  # one hidden tick
    assert sim.peek("y") == 1  # no second hidden tick
    sim.step(1)
    oracle.step(1)
    assert sim.peek("y") == oracle.peek("y") == 1


def test_peek_of_input_never_ticks(builds):
    # clk=1 held: out == 2**n - 1 after n ticks (BaseEval-derived).
    sim = builds.sim_fixture("clock")
    sim.poke("clk", 1)
    assert sim.peek("clk") == 1  # input peek returns the poked value...
    assert sim.peek("clk") == 1  # ...repeatedly...
    sim.step(1)
    # ...without ever ticking: exactly ONE evaluation total has happened.
    # Had either input peek ticked, out would read 0x3 or 0x7 here.
    assert sim.peek("out") == 0x1


def test_peek_of_input_does_not_clear_dirty(builds):
    sim = builds.sim_fixture("clock")
    sim.poke("clk", 1)
    assert sim.peek("clk") == 1
    # Dirty must have survived the input peek: this output peek performs
    # the (single) lazy tick. Had peek(clk) cleared dirty, out would read
    # the stored 0x0; had it also ticked, out would read 0x3.
    assert sim.peek("out") == 0x1
    assert sim.peek("out") == 0x1  # lazy tick cleared dirty: no second tick
    sim.step(1)
    assert sim.peek("out") == 0x3


def test_step_zero_is_noop_and_preserves_dirty(builds):
    # Part A: step(0) advances nothing.
    sim = builds.sim_fixture("clock")
    sim.poke("clk", 1)
    sim.step(0)
    sim.step(1)
    # step(1) evaluated once and cleared dirty; if step(0) had also ticked,
    # out would read 0x3.
    assert sim.peek("out") == 0x1

    # Part B: step(0) does NOT clear dirty.
    sim2 = builds.sim_fixture("clock")
    sim2.poke("clk", 1)
    sim2.step(0)
    # The lazy tick must still fire here; if step(0) had cleared dirty this
    # would read the stored 0x0.
    assert sim2.peek("out") == 0x1


def test_unknown_poke_does_not_arm_dirty(builds, capfd):
    # An unknown-name poke must be a COMPLETE no-op: in particular it must
    # not set dirty (easy bug: `dirty = 1` hoisted above the name scan would
    # pass every other test in the suite).
    sim = builds.sim_fixture("clock")
    sim.poke("bogus", 1)
    capfd.readouterr()  # drain the C-level diagnostic
    # No lazy tick may fire: out still reads the stored cycle-0 value.
    assert sim.peek("out") == 0x0
    # With dirty legitimately armed, an unknown poke adds nothing: the one
    # lazy tick fires, no more (clock counter: 0x1 == exactly one tick).
    sim.poke("clk", 1)
    sim.poke("bogus", 1)
    capfd.readouterr()
    assert sim.peek("out") == 0x1
    # And an unknown poke after the lazy tick must not re-arm dirty.
    sim.poke("bogus", 1)
    capfd.readouterr()
    assert sim.peek("out") == 0x1


def test_negative_step_is_noop_and_preserves_dirty(builds):
    # The spec defines step(0) as a no-op; negative counts fall out of the
    # same loop. Dirty must survive: exactly one (lazy) tick fires in total.
    sim = builds.sim_fixture("clock")
    sim.poke("clk", 1)
    sim.step(-3)
    assert sim.peek("out") == 0x1


def test_repoke_rearms_lazy_tick(builds):
    # Clock counter: poke,peek,poke,peek == exactly two ticks total.
    sim = builds.sim_fixture("clock")
    sim.poke("clk", 1)
    assert sim.peek("out") == 0x1  # tick 1
    sim.poke("clk", 1)  # re-poke re-arms dirty (same value is irrelevant)
    assert sim.peek("out") == 0x3  # tick 2

    # add2 with a changing input timeline, against BaseEval stepped twice.
    sim2 = builds.sim_fixture("add2")
    oracle = make_oracle(builds.fixture_text("add2"))
    for port, v in [("A", 1), ("B", 2), ("Cin", 0)]:
        sim2.poke(port, v)
        oracle.poke(port, v)
    oracle.step(1)
    assert sim2.peek("Sum") == oracle.peek("Sum")  # tick 1 (A=1 applied)
    sim2.poke("A", 3)
    oracle.poke("A", 3)
    oracle.step(1)
    assert sim2.peek("Sum") == oracle.peek("Sum")  # tick 2 (A=3 applied)
    assert sim2.peek("Cout") == oracle.peek("Cout")
    # Cycle counters stayed aligned: explicit stepping keeps agreeing.
    for _ in range(4):
        sim2.step(1)
        oracle.step(1)
        assert sim2.peek("Sum") == oracle.peek("Sum")
        assert sim2.peek("Cout") == oracle.peek("Cout")
