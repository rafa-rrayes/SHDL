"""Multi-bit port semantics: LSB-first scatter/gather, masking, 64-bit width."""

from __future__ import annotations

from shdlc.compile import compile_text

from .harness import WIDE64_TEXT, make_oracle

U64_MAX = 0xFFFFFFFFFFFFFFFF

#: Port wire lists deliberately NOT in header order: bit 0 of "P" is wire w2,
#: bit 1 is w0, bit 2 is w1; the output port "Q" is scrambled differently.
#: Flattener-emitted ports are always in header order, so without this the
#: only scrambled coverage would be probabilistic (fuzz).
SCRAMBLED_TEXT = """\
component Scrambled(w0, w1, w2) -> (y0, y1, y2) {
    connect { w0 -> y0; w1 -> y1; w2 -> y2; }
}
meta { "ports": { "inputs": { "P": ["w2", "w0", "w1"] }, "outputs": { "Q": ["y1", "y2", "y0"] } } }
"""


def test_scrambled_port_wire_order(builds):
    # The emitted wire table must follow the meta.ports list order exactly.
    _, c_source = compile_text(SCRAMBLED_TEXT)
    assert "static const uint16_t in_wires_P[] = { IN_w2, IN_w0, IN_w1 };" in c_source
    # Behavioral: bit b of a poked value lands on wires[b], and the output
    # port gathers its own scrambled mapping — bit-for-bit with BaseEval.
    sim = builds.sim_from_text("scrambled", SCRAMBLED_TEXT)
    oracle = make_oracle(SCRAMBLED_TEXT)
    for value in range(8):
        sim.poke("P", value)
        oracle.poke("P", value)
        assert sim.peek("P") == value
        sim.step(1)
        oracle.step(1)
        assert sim.peek("Q") == oracle.peek("Q")
    # Spot-check the mapping by hand: P=0b001 sets w2, which is Q's bit 1.
    sim.poke("P", 0b001)
    oracle.poke("P", 0b001)
    sim.step(1)
    oracle.step(1)
    assert sim.peek("Q") == oracle.peek("Q") == 0b010


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
