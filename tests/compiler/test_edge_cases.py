"""Degenerate circuits and unknown-signal handling.

C-level fprintf goes to fd 2, which only capfd (not capsys) can see.
"""

from __future__ import annotations

from .harness import GND_TEXT, VCC_TEXT, WIRE_TEXT, ZERO_OUTPUT_TEXT, make_oracle


def test_zero_gate_passthrough_builds_and_runs(builds):
    dual = builds.dual_from_text("hand_wire", WIRE_TEXT)
    dual.poke("a", 1)
    dual.step_compare(1)
    assert dual.sim.peek("y") == 1
    dual.poke("a", 0)
    dual.step_compare(1)
    assert dual.sim.peek("y") == 0


def test_zero_input_circuit_builds_and_runs(builds):
    # VCC-only and GND-only circuits: no pokes possible at all.
    sim = builds.sim_from_text("hand_vcc", VCC_TEXT)
    oracle = make_oracle(VCC_TEXT)
    got = [sim.peek("y")]
    for _ in range(3):
        sim.step(1)
        oracle.step(1)
        got.append(sim.peek("y"))
        assert got[-1] == oracle.peek("y")
    assert got == [0, 1, 1, 1]  # derived from BaseEval

    sim2 = builds.sim_from_text("hand_gnd", GND_TEXT)
    sim2.step(3)
    assert sim2.peek("y") == 0


def test_zero_output_circuit_builds_and_runs(builds):
    sim = builds.sim_from_text("hand_sink", ZERO_OUTPUT_TEXT)
    oracle = make_oracle(ZERO_OUTPUT_TEXT)
    sim.poke("a", 1)
    oracle.poke("a", 1)
    sim.step(3)
    oracle.step(3)
    assert sim.peek("a") == oracle.peek("a") == 1
    sim.reset()
    assert sim.peek("a") == 0


def test_unknown_poke_is_noop_with_stderr_message(builds, capfd):
    sim = builds.sim_fixture("add2")
    oracle = make_oracle(builds.fixture_text("add2"))
    for port, v in [("A", 1), ("B", 2), ("Cin", 0)]:
        sim.poke(port, v)
        oracle.poke(port, v)
    capfd.readouterr()  # drain build/test noise
    sim.poke("bogus", 7)
    err = capfd.readouterr().err
    assert err.strip(), "unknown poke must report an error on stderr"
    assert "bogus" in err, f"diagnostic should name the signal: {err!r}"
    # Known-name behavior unaffected: the bad poke changed nothing.
    sim.step(6)
    oracle.step(6)
    for port in ("A", "B", "Cin", "Sum", "Cout"):
        assert sim.peek(port) == oracle.peek(port), port


def test_unknown_peek_returns_zero_with_stderr_message(builds, capfd):
    sim = builds.sim_fixture("add2")
    capfd.readouterr()
    assert sim.peek("nonesuch") == 0
    err = capfd.readouterr().err
    assert err.strip(), "unknown peek must report an error on stderr"
    assert "nonesuch" in err, f"diagnostic should name the signal: {err!r}"


def test_unknown_peek_does_not_consume_lazy_tick(builds, capfd):
    # clk=1 held: out == 2**n - 1 after n ticks (BaseEval-derived counter).
    sim = builds.sim_fixture("clock")
    sim.poke("clk", 1)
    assert sim.peek("nonesuch") == 0  # unknown name: does nothing
    capfd.readouterr()
    # The lazy tick still belongs to the first KNOWN output peek.
    assert sim.peek("out") == 0x1
