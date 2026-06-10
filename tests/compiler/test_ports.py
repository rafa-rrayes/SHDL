"""Multi-bit port semantics: LSB-first scatter/gather, masking, 64-bit width."""

from __future__ import annotations

from .harness import WIDE64_TEXT, make_oracle

U64_MAX = 0xFFFFFFFFFFFFFFFF


def test_splitbyte_scatter_gather(builds):
    dual = builds.dual_fixture("splitByte")
    dual.poke("In", 0xAB)
    dual.step_compare(1)
    # LSB-first: In bits 1..4 -> Low, 5..8 -> High (BaseEval-derived).
    assert dual.sim.peek("Low") == 0xB
    assert dual.sim.peek("High") == 0xA
    # The split is a pure passthrough (depth 0): a fresh instance shows it
    # via the lazy peek too.
    sim = builds.sim_fixture("splitByte")
    sim.poke("In", 0xAB)
    assert sim.peek("Low") == 0xB
    assert sim.peek("High") == 0xA


def test_passthru_fixture(builds):
    dual = builds.dual_fixture("passthru")
    dual.poke("A", 2)
    dual.step_compare(1)
    assert dual.sim.peek("B") == 2  # passthrough of A (BaseEval-derived)
    assert dual.sim.peek("C") == 1  # XOR of A's bits after one cycle


def test_poke_masks_value_to_port_width(builds):
    # 8-bit port: 0x1FF must be masked to 0xFF (peek(input) never ticks).
    dual = builds.dual_fixture("splitByte")
    dual.poke("In", 0x1FF)  # DualSim pokes raw to the lib, masked to oracle
    assert dual.sim.peek("In") == 0xFF
    dual.step_compare(2)  # downstream values agree with the masked oracle

    # 2-bit port: a full 64-bit pattern masks down to 2 bits.
    dual2 = builds.dual_fixture("add2")
    dual2.poke("A", U64_MAX)
    dual2.poke("B", 0x1FE)
    assert dual2.sim.peek("A") == 0x3
    assert dual2.sim.peek("B") == 0x2
    dual2.step_compare(6)


def test_wide64_port_full_width(builds):
    """64-bit port: full-width values must survive poke/peek (UB guard)."""
    sim = builds.sim_from_text("hand_wide64", WIDE64_TEXT)
    oracle = make_oracle(WIDE64_TEXT)
    for value in (U64_MAX, 0x8000000000000000, 0xA5A5A5A5A5A5A5A5, 1, 0):
        sim.poke("B", value)
        oracle.poke("B", value)
        assert sim.peek("B") == value  # peek(input): masked stored value
        sim.step(1)
        oracle.step(1)
        assert sim.peek("Y") == oracle.peek("Y") == value  # passthrough
