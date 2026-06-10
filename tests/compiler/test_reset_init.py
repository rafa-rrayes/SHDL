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


def test_reset_with_pending_poke_clears_dirty(builds):
    # poke -> reset -> peek, with NO step in between: reset must disarm the
    # pending lazy tick. Mutation-killing test: with `dirty = 0;` deleted
    # from the emitted reset(), the first output peek here fires a tick from
    # the seeded state and Q reads 1 (BaseEval idle transient), not 0.
    sim = builds.sim_fixture("srlatch")
    sim.poke("S", 1)  # arm dirty; deliberately no step
    sim.reset()
    assert snapshot(sim) == {"S": 0, "R": 0, "Q": 0, "Qn": 1}
    assert snapshot(sim)["Q"] == 0  # still no tick on repeated reads


#: Multi-hop output-alias chain (g1.O -> W2 -> W1) seeded via the OUTERMOST
#: alias. The model must resolve "W1" through the chain to gate g1; the
#: BaseEval oracle must follow the same multi-hop chain (regression: its
#: _seeded_gate used to resolve one hop only and silently dropped the seed).
ALIAS_INIT_TEXT = """\
component AliasInit(a) -> (W1, W2) {
    g1: NOT;
    connect { a -> g1.A; g1.O -> W2; W2 -> W1; }
}
meta { "ports": { "inputs": { "a": ["a"] }, "outputs": { "W1": ["W1"], "W2": ["W2"] } }, "init": { "W1": 1 } }
"""


def test_multi_hop_alias_init_seeds_driving_gate(builds):
    sim = builds.sim_from_text("alias_init", ALIAS_INIT_TEXT)
    oracle = make_oracle(ALIAS_INIT_TEXT)
    # Fresh load: the seed must be visible through BOTH aliases, lib and
    # oracle agreeing.
    for port in ("W1", "W2"):
        assert sim.peek(port) == oracle.peek(port) == 1
    # The seed is power-on state, not pinned: with a=1 the NOT flips to 0 at
    # cycle 1 on both sides.
    sim.poke("a", 1)
    oracle.poke("a", 1)
    sim.step(1)
    oracle.step(1)
    assert sim.peek("W1") == oracle.peek("W1") == 0
