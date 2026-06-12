"""Release-ABI contract pins (Domain O) driven through ctypes.

These exercise edge cases of the six exported functions against real built
libraries, with all expected values sourced from BaseEval or hand-derivation,
never from the C implementation:

- ABI-4: step(negative) is a true no-op, discriminated with a step(1) probe.
- ABI-6 / AMB-1: signal names are case-sensitive.
- ABI-7 / AMB-13: peek zero-extends above the port width -- after an over-wide
  poke and after reset.
- ABI-14: poke on an OUTPUT port name takes the unknown-signal path.
- ABI-15: an empty-string name takes the unknown-signal path, even on a
  zero-port circuit (the dummy table entries must never match).
- ABI-16 / AMB-32: NULL signal to poke/peek takes the unknown-signal path
  (guarded, never an unguarded strcmp / segfault).
- ABI-17: double poke of the same port in one dirty batch -- last value wins,
  still exactly one lazy tick.
- ABI-19: the fully-empty circuit (0/0/0) loads and obeys the ABI.
- ABI-12 holes: zero-output-port circuit through run_batch; dirty stays set
  when nothing was poked and cycles <= 0.
- ABI-8: a >64-bit port flattens fine but shdlc rejects it end-to-end.
"""

from __future__ import annotations

import ctypes

import pytest

from shdlc.model import ModelError

from .harness import (
    GND_TEXT,
    WIDE64_TEXT,
    ZERO_OUTPUT_TEXT,
    make_oracle,
)

U64_MAX = 0xFFFFFFFFFFFFFFFF

# A fully-empty circuit: zero inputs, zero outputs, zero gates. The empty
# connect block is legal Base SHDL.
EMPTY_TEXT = """\
component HandEmpty() -> () {
    connect { }
}
meta { "ports": { "inputs": {}, "outputs": {} } }
"""

# Single-bit AND for the case-sensitivity / output-poke / double-poke cases.
AND_LOWER = """\
component CaseAnd(a, b) -> (y) {
    g: AND;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"], "b": ["b"] }, "outputs": { "y": ["y"] } } }
"""


def _raw_poke(sim, signal, value: int) -> None:
    """poke through the raw C symbol so we can pass NULL (ctypes None)."""
    sim._lib.poke(signal, ctypes.c_uint64(value))


def _raw_peek(sim, signal) -> int:
    return int(sim._lib.peek(signal))


# ---------------------------------------------------------------------------
# ABI-4: step(negative) is a true no-op (step(1) discriminator).
# ---------------------------------------------------------------------------


def test_negative_step_is_a_true_noop_with_step1_discriminator(builds):
    # The clock counter reads 2**n - 1 after exactly n ticks. A lone lazy peek
    # cannot tell "no-op" from "one tick + dirty clear"; a following explicit
    # step(1) can: a true no-op leaves dirty armed so the first peek still
    # ticks, and step(1) advances to exactly cycle 1 -> 0x1, not 0x3.
    sim = builds.sim_fixture("clock")
    sim.poke("clk", 1)
    sim.step(-5)  # must change nothing AND must not clear dirty
    sim.step(1)  # advances to cycle 1 (the only tick so far)
    assert sim.peek("out") == 0x1
    # A second, fresh instance proves dirty survived the negative step on its
    # own: with no explicit step the first output peek lazy-ticks once.
    sim2 = builds.sim_fixture("clock")
    sim2.poke("clk", 1)
    sim2.step(-5)
    assert sim2.peek("out") == 0x1  # exactly one (lazy) tick total


# ---------------------------------------------------------------------------
# ABI-6 / AMB-1: signal names are case-sensitive.
# ---------------------------------------------------------------------------


def test_signal_names_are_case_sensitive(builds, capfd):
    sim = builds.sim_from_text("case_and", AND_LOWER)
    oracle = make_oracle(AND_LOWER)
    # Correct case pokes; wrong case must miss (unknown-signal path).
    sim.poke("a", 1)
    sim.poke("b", 1)
    oracle.poke("a", 1)
    oracle.poke("b", 1)
    capfd.readouterr()
    sim.poke("A", 0)  # wrong case: a complete no-op, names are case-sensitive
    sim.poke("B", 0)
    err = capfd.readouterr().err
    assert "unknown signal" in err and ('"A"' in err or "'A'" in err or "A" in err)
    oracle.step(1)
    sim.step(1)
    assert sim.peek("y") == oracle.peek("y") == 1  # 'a','b' still 1: AND -> 1
    # Wrong-case output peek also misses.
    capfd.readouterr()
    assert _raw_peek(sim, b"Y") == 0  # 'Y' != 'y'
    assert "unknown signal" in capfd.readouterr().err


# ---------------------------------------------------------------------------
# ABI-7 / AMB-13: peek zero-extends above the port width.
# ---------------------------------------------------------------------------


def test_peek_zero_extends_above_port_width(builds):
    # add2's Sum is a 2-bit port; Cout is 1-bit. Their peeks must carry no
    # bits above the width, regardless of state -- ctypes restype is c_uint64,
    # so any stray high bit would show here.
    sim = builds.sim_fixture("add2")
    oracle = make_oracle(builds.fixture_text("add2"))
    for a, b, cin in [(3, 3, 1), (2, 2, 0), (0, 0, 0), (3, 0, 1)]:
        sim.reset()
        oracle.reset()
        # Deliberately over-wide pokes: the lib must mask to width on the way
        # in and zero-extend on the way out.
        sim.poke("A", a | (1 << 40))
        sim.poke("B", b | (1 << 50))
        sim.poke("Cin", cin | (1 << 60))
        oracle.poke("A", a)
        oracle.poke("B", b)
        oracle.poke("Cin", cin)
        sim.step(6)
        oracle.step(6)
        sum_v, cout_v = sim.peek("Sum"), sim.peek("Cout")
        assert sum_v == oracle.peek("Sum"), (a, b, cin)
        assert cout_v == oracle.peek("Cout"), (a, b, cin)
        assert sum_v >> 2 == 0, f"Sum has bits above width 2: {sum_v:#x}"
        assert cout_v >> 1 == 0, f"Cout has bits above width 1: {cout_v:#x}"
    # After reset: width-respecting zeros, no stray high bits.
    sim.reset()
    assert sim.peek("Sum") == 0 and sim.peek("Cout") == 0


# ---------------------------------------------------------------------------
# ABI-14: poke on an OUTPUT port name -> unknown-signal path, complete no-op.
# ---------------------------------------------------------------------------


def test_poke_on_output_port_name_is_unknown_signal(builds, capfd):
    sim = builds.sim_from_text("case_and", AND_LOWER)
    oracle = make_oracle(AND_LOWER)
    sim.poke("a", 1)
    sim.poke("b", 1)
    oracle.poke("a", 1)
    oracle.poke("b", 1)
    capfd.readouterr()
    # 'y' is an OUTPUT port: poke must not match it (poke scans inputs only),
    # must report unknown, and must not arm/disturb anything.
    sim.poke("y", 0)
    err = capfd.readouterr().err
    assert "unknown signal" in err and "y" in err
    oracle.step(1)
    sim.step(1)
    assert sim.peek("y") == oracle.peek("y") == 1  # unaffected by the bad poke


# ---------------------------------------------------------------------------
# ABI-15: empty-string name -> unknown-signal path, even on a zero-port circuit.
# ---------------------------------------------------------------------------


def test_empty_string_name_is_unknown_even_on_zero_port_circuit(builds, capfd):
    # GND_TEXT has one output and zero inputs; EMPTY_TEXT has zero of both.
    # The dummy { "", 0, 0 } / "" table entries must never be matched by "".
    for key, text, peekable in [
        ("hand_gnd", GND_TEXT, True),
        ("hand_empty_abi", EMPTY_TEXT, False),
    ]:
        sim = builds.sim_from_text(key, text)
        capfd.readouterr()
        _raw_poke(sim, b"", 1)
        assert "unknown signal" in capfd.readouterr().err
        assert _raw_peek(sim, b"") == 0
        assert "unknown signal" in capfd.readouterr().err
        if peekable:
            # The real output still works -- the empty poke changed nothing.
            sim.step(1)
            assert sim.peek("y") == 0  # GND


# ---------------------------------------------------------------------------
# ABI-16 / AMB-32: NULL signal -> unknown-signal path (guarded), never UB.
# ---------------------------------------------------------------------------


def test_null_signal_name_takes_unknown_path(builds, capfd):
    sim = builds.sim_from_text("case_and", AND_LOWER)
    capfd.readouterr()
    # If the strcmp were unguarded, this would segfault the test process.
    _raw_poke(sim, None, 1)
    assert "unknown signal" in capfd.readouterr().err
    assert _raw_peek(sim, None) == 0
    assert "unknown signal" in capfd.readouterr().err
    # NULL poke must not arm dirty: with a real poke and one tick the AND
    # reads its inputs cleanly, unperturbed by the NULL calls.
    oracle = make_oracle(AND_LOWER)
    sim.poke("a", 1)
    sim.poke("b", 1)
    oracle.poke("a", 1)
    oracle.poke("b", 1)
    _raw_poke(sim, None, 1)  # between poke and step: still a no-op
    capfd.readouterr()
    sim.step(1)
    oracle.step(1)
    assert sim.peek("y") == oracle.peek("y") == 1


def test_null_signal_on_zero_port_circuit(builds, capfd):
    # ABI-16 with no ports at all: the guard fires before any table scan.
    sim = builds.sim_from_text("hand_empty_abi", EMPTY_TEXT)
    capfd.readouterr()
    _raw_poke(sim, None, 1)
    assert "unknown signal" in capfd.readouterr().err
    assert _raw_peek(sim, None) == 0
    assert "unknown signal" in capfd.readouterr().err


# ---------------------------------------------------------------------------
# ABI-17: double poke of the same port in one dirty batch -> last value wins.
# ---------------------------------------------------------------------------


def test_double_poke_same_port_last_value_wins_one_tick(builds):
    # add2: poke A=1 then A=3 with no intervening peek/step. The second poke
    # overwrites; exactly one lazy tick happens on the first output peek.
    sim = builds.sim_fixture("add2")
    oracle = make_oracle(builds.fixture_text("add2"))
    sim.poke("B", 0)
    sim.poke("Cin", 0)
    oracle.poke("B", 0)
    oracle.poke("Cin", 0)
    sim.poke("A", 1)  # first value
    sim.poke("A", 3)  # last value wins
    oracle.poke("A", 3)
    oracle.step(1)  # the single lazy tick the lib will perform
    assert sim.peek("Sum") == oracle.peek("Sum")  # one hidden tick, A=3 applied
    assert sim.peek("Cout") == oracle.peek("Cout")
    # No second hidden tick: a re-peek reads the same committed cycle.
    again = sim.peek("Sum")
    sim2 = sim.peek("Sum")
    assert again == sim2


# ---------------------------------------------------------------------------
# ABI-19: the fully-empty circuit obeys the ABI.
# ---------------------------------------------------------------------------


def test_fully_empty_circuit_obeys_abi(builds, capfd):
    sim = builds.sim_from_text("hand_empty_abi", EMPTY_TEXT)
    # reset / step / step_settle / run_batch all run without crashing, and any
    # named poke/peek is unknown (there are no ports).
    sim.reset()
    sim.step(5)
    assert sim.step_settle(5) == 1  # immediately at a (trivial) fixed point
    capfd.readouterr()
    sim.poke("anything", 1)
    assert "unknown signal" in capfd.readouterr().err
    assert sim.peek("anything") == 0
    capfd.readouterr()
    # run_batch with no ports: three empty frames, zero outputs each.
    assert sim.run_batch([(), (), ()], 0, 3) == [(), (), ()]


# ---------------------------------------------------------------------------
# ABI-12 holes: zero-output-port circuit through run_batch; dirty-stays-set.
# ---------------------------------------------------------------------------


def test_run_batch_zero_output_ports(builds):
    # ZERO_OUTPUT_TEXT has one input, no outputs. run_batch must scatter the
    # input frames, advance, and never dereference `out` (dimension 0).
    sim = builds.sim_from_text("hand_sink_abi", ZERO_OUTPUT_TEXT)
    oracle = make_oracle(ZERO_OUTPUT_TEXT)
    frames = [(1,), (0,), (1,)]
    got = sim.run_batch(frames, 0, 4)
    assert got == [(), (), ()]  # zero outputs gathered per frame
    # The input state ends up matching the last frame, stepped, vs the oracle.
    for (v,) in frames:
        oracle.poke("a", v)
        oracle.step(4)
    assert sim.peek("a") == oracle.peek("a") == 1


def test_run_batch_dirty_stays_set_when_no_poke_and_cycles_nonpositive(builds):
    # ABI-12 hole: a no-input circuit (no scatter, nop==0) with cycles<=0 must
    # leave the lazy-peek path armed exactly as a bare poke+no-step would.
    # We use the clock fixture (one input) but compare a frame with cycles<=0
    # against the equivalent scalar sequence including its lazy peek.
    batch = builds.sim_fixture("clock")
    scalar = builds.sim_fixture("clock")
    for sim in (batch, scalar):
        sim.reset()
    # One frame, clk=1, cycles=0: run_batch must take the lazy-peek path and
    # the gathered output equals the scalar poke + lazy peek.
    got = batch.run_batch([(1,)], 1, 0)
    scalar.poke("clk", 1)
    assert got == [(scalar.peek("out"),)]  # exactly one lazy tick each: 0x1
    assert got == [(0x1,)]


# ---------------------------------------------------------------------------
# ABI-8: a >64-bit port flattens fine but shdlc rejects end-to-end.
# ---------------------------------------------------------------------------


def test_65bit_port_flattens_but_shdlc_rejects(tmp_path):
    # Flatten a .shdl with a 65-bit port (legal in the flattener: AMB-11),
    # then prove shdlc's model layer rejects it with a structured error
    # naming the port and width.
    from flattener.pipeline import flatten_program
    from shdlc.compile import compile_text

    src = tmp_path / "wide65.shdl"
    src.write_text("component Wide65(A[65]) -> (Y[65]) {\n    connect { A -> Y; }\n}\n")
    base_text = flatten_program(str(src), timestamp="2026-01-01T00:00:00Z").text
    assert base_text, "flattener must accept the 65-bit port"
    with pytest.raises(ModelError) as ei:
        compile_text(base_text)
    msg = str(ei.value)
    assert "65" in msg and ("A" in msg) and "1..64" in msg


def test_64bit_port_accepted_end_to_end(builds):
    # The width-64 boundary is accepted and round-trips a full uint64 value.
    sim = builds.sim_from_text("hand_wide64_abi", WIDE64_TEXT)
    oracle = make_oracle(WIDE64_TEXT)
    for value in (U64_MAX, 0x8000_0000_0000_0000, 1, 0):
        sim.poke("B", value)
        oracle.poke("B", value)
        sim.step(1)
        oracle.step(1)
        assert sim.peek("Y") == oracle.peek("Y") == value
