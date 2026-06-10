"""reset() semantics: constructor reset, init seeds, idempotence, input clearing.

srlatch's meta.init is {"Q": 0, "Qn": 1}: a fresh load must show Q=0, Qn=1
WITHOUT any poke or step — proving the constructor ran reset, the init seeds
were applied, and peek needed no hidden tick (dirty is clear).
"""

from __future__ import annotations

from .harness import make_oracle

SR_PORTS = ["S", "R", "Q", "Qn"]


def snapshot(sim_like, ports=SR_PORTS):
    return {p: sim_like.peek(p) for p in ports}


def test_fresh_load_applies_init_seeds_without_tick(builds):
    sim = builds.sim_fixture("srlatch")  # fresh dylib copy: constructor just ran
    assert sim.peek("Q") == 0  # meta.init {"Q": 0, "Qn": 1}
    assert sim.peek("Qn") == 1
    assert sim.peek("S") == 0 and sim.peek("R") == 0  # inputs cleared
    # Repeat: peeks must not have changed state. Had any peek ticked, the
    # idle transient (BaseEval: Q reads 1 at cycle 1) would show here.
    assert sim.peek("Q") == 0 and sim.peek("Qn") == 1
    # And it matches the oracle's fresh state exactly.
    oracle = make_oracle(builds.fixture_text("srlatch"))
    assert snapshot(sim) == snapshot(oracle)


def test_reset_returns_to_fresh_load_state(builds):
    sim = builds.sim_fixture("srlatch")
    oracle = make_oracle(builds.fixture_text("srlatch"))
    fresh = snapshot(sim)
    assert fresh == snapshot(oracle)

    # Disturb everything: set the latch (Q -> 1 per BaseEval) and leave an
    # input held high so reset provably clears inputs too.
    sim.poke("S", 1)
    oracle.poke("S", 1)
    sim.step(4)
    oracle.step(4)
    assert snapshot(sim) == snapshot(oracle)  # lockstep sanity
    assert sim.peek("Q") == 1  # derived from BaseEval (set held 4 cycles)

    sim.reset()
    oracle.reset()
    assert snapshot(sim) == fresh  # state AND inputs back to power-on
    assert sim.peek("S") == 0  # the held input was cleared

    # Idempotent: reset(); reset() is the same as one reset.
    sim.reset()
    sim.reset()
    assert snapshot(sim) == fresh


def test_peek_after_reset_does_not_change_state(builds):
    sim = builds.sim_fixture("srlatch")
    sim.poke("S", 1)
    sim.step(4)
    sim.reset()
    # reset cleared dirty: peeks must not trigger the lazy tick, no matter
    # how many times outputs are read.
    first = snapshot(sim)
    for _ in range(3):
        assert snapshot(sim) == first
    assert first["Q"] == 0 and first["Qn"] == 1
