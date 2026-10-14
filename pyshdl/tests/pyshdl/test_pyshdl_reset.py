"""Power-on reset honoring ``init`` (V.2): the seeded state on a fresh load,
after reset(), and through component hierarchy."""

from __future__ import annotations


def test_power_on_state_is_init_seeded(examples):
    with examples.fresh("srLatch") as c:
        assert (c["Q"], c["Qn"]) == (0, 1)  # seeds, not all-zero


def test_reset_restores_the_power_on_state(examples):
    with examples.fresh("srLatch") as c:
        c["S"] = 1
        c.step(4)
        assert (c["Q"], c["Qn"]) == (1, 0)
        c.reset()
        assert (c["Q"], c["Qn"]) == (0, 1)
        # reset cleared the inputs too: the latch holds its seeded state.
        c.step(8)
        assert (c["Q"], c["Qn"]) == (0, 1)


def test_reset_is_idempotent(examples):
    with examples.fresh("srLatch") as c:
        c.reset()
        c.reset()
        assert (c["Q"], c["Qn"]) == (0, 1)


def test_init_seeds_survive_hierarchy(examples):
    # DLatch embeds SRLatch; the seeds carry through flattening.
    with examples.fresh("dLatch") as c:
        assert (c["Q"], c["Qn"]) == (0, 1)
        c["D"], c["EN"] = 1, 1
        c.step(8)
        assert (c["Q"], c["Qn"]) == (1, 0)
        c.reset()
        assert (c["Q"], c["Qn"]) == (0, 1)


def test_reset_equals_a_fresh_load(examples):
    with examples.fresh("dLatch") as fresh, examples.fresh("dLatch") as used:
        used["D"], used["EN"] = 1, 1
        used.step(11)
        used.reset()
        for port in (*used.inputs, *used.outputs):
            assert used[port] == fresh[port], port


def test_init_metadata_is_exposed(examples):
    with examples.fresh("srLatch") as latch, examples.fresh("adder8") as adder:
        assert latch.info.has_init
        assert set(latch.info.init.values()) <= {0, 1}
        assert not adder.info.has_init
        assert dict(adder.info.init) == {}
