"""The legacy "comprehensive" boundary catalog, re-run at the Python API
(V.2): pass-through sweeps, 0xFFFF patterns, bitwise-op circuits, and nibble
extraction. Largely subsumed by the conformance traces — mirrored here cheaply
because this is the surface users actually touch."""

from __future__ import annotations

PATTERNS_8 = (0x00, 0xFF, 0xAA, 0x55, 0xF0, 0x0F, 0x80, 0x01)


def test_passthrough_0_to_255(examples):
    # Adder with B = Cin = 0 is an 8-bit identity: every value crosses the
    # poke -> simulate -> peek path unchanged.
    with examples.fresh("adder8") as c:
        frames = [{"A": a, "B": 0, "Cin": 0} for a in range(256)]
        out = c.run_batch(frames, cycles=c.timing.max_depth)
        assert [row["Sum"] for row in out] == list(range(256))
        assert all(row["Cout"] == 0 for row in out)


def test_sign_extension_0xffff_patterns(examples):
    # busOps' SignExtend maps 8 -> 16 bits; the all-ones and MSB cases pin
    # the 16-bit boundary patterns end to end.
    with examples.fresh("busOps") as c:  # top component: SignExtend
        cases = {
            0xFF: 0xFFFF,
            0x80: 0xFF80,
            0x7F: 0x007F,
            0x00: 0x0000,
            0xAA: 0xFFAA,
            0x55: 0x0055,
        }
        for value, expected in cases.items():
            c["In"] = value
            c.settle()
            assert c["Out"] == expected, hex(value)


def test_bitwise_op_circuits(examples):
    ops = {0: lambda a, b: a & b, 1: lambda a, b: a | b, 2: lambda a, b: a ^ b}
    with examples.fresh("alu") as c:
        for op, fn in ops.items():
            for a in PATTERNS_8:
                for b in PATTERNS_8:
                    c["A"], c["B"], c["Op"] = a, b, op
                    c.settle()
                    expected = fn(a, b)
                    assert c["R"] == expected, (op, hex(a), hex(b))
                    assert c["Zero"] == (1 if expected == 0 else 0)


def test_alu_addition_boundaries(examples):
    with examples.fresh("alu") as c:
        for a, b, r, cout in ((200, 55, 255, 0), (255, 1, 0, 1), (0, 0, 0, 0), (255, 255, 254, 1)):
            c["A"], c["B"], c["Op"] = a, b, 3
            c.settle()
            assert (c["R"], c["Cout"]) == (r, cout), (a, b)


def test_nibble_extraction(examples):
    with examples.fresh("busOps", top="SplitByte") as c:
        for value in range(256):
            c["In"] = value
            c.settle()
            assert c["Low"] == value & 0xF, hex(value)
            assert c["High"] == value >> 4, hex(value)


def test_nibble_swap_is_an_involution(examples):
    with examples.fresh("busOps", top="SwapNibbles") as c:
        for value in PATTERNS_8 + (0x12, 0xCD):
            c["In"] = value
            c.settle()
            swapped = c["Out"]
            assert swapped == ((value & 0xF) << 4) | (value >> 4)
            c["In"] = swapped
            c.settle()
            assert c["Out"] == value
