"""CPU-11: ALU internal Op codes 13-15 (reserved) pinned at the unit level.

`Op[4]` is a 4-bit field, so the encodings 13, 14, 15 are reachable inputs to
the ALU even though the control unit never emits them (its `AluOp` decode tops
out at 12 = ROR — see control.shdl: AluOp[4] is set only together with one of
the shift functs 0-4, i.e. ops 8..12). alu.shdl wires res.D13/D14/D15 to
add.Sum, so the reference (sr16tools.alu_ref) models 13-15 as the adder
pass-through; this test drives those codes directly at the ALU pins and pins
that the gate-level ALU agrees bit-for-bit with the reference.

This is the unit pin the golden_tests.md CPU-11 row prefers (over the
decode-analysis proof that control never emits them).
"""

from __future__ import annotations

import random

import pytest
from sr16tools.alu_ref import alu_ref

SETTLE = 100  # ripple-carry + mux tree + Z-reduce (matches test_alu.py)

# Corner operand pairs that exercise the adder's carry/overflow corners, so a
# reserved code that quietly dropped the adder result would diverge.
VECTORS = [
    (0x0000, 0x0000),
    (0x0001, 0x0001),
    (0xFFFF, 0x0001),  # carry out
    (0xFFFF, 0xFFFF),
    (0x7FFF, 0x0001),  # signed overflow
    (0x8000, 0x8000),  # carry + overflow
    (0x1234, 0x5678),
    (0xAAAA, 0x5555),
]


@pytest.mark.parametrize("op", [13, 14, 15])
def test_alu_reserved_codes_are_adder_passthrough(cpu_builds, op):
    # CPU-11
    s = cpu_builds.sim("alu")
    rng = random.Random(13000 + op)
    vectors = VECTORS + [(rng.getrandbits(16), rng.getrandbits(16)) for _ in range(6)]
    for a, b in vectors:
        for cin in (0, 1):
            s.poke("A", a)
            s.poke("B", b)
            s.poke("Op", op)
            s.poke("Cin", cin)
            s.step(SETTLE)
            want = alu_ref(op, a, b, cin)
            got = (s.peek("R"), s.peek("Z"), s.peek("N"), s.peek("C"), s.peek("V"))
            assert got == want, (
                f"reserved op={op} a={a:#06x} b={b:#06x} cin={cin}: "
                f"got R,Z,N,C,V={got}, want {want}"
            )


def test_alu_reserved_codes_equal_add(cpu_builds):
    """13-15 produce the *same result word* as ADD (op 0) for the same A/B.

    A second, independent witness that the reserved encodings are the adder
    pass-through (ISA-irrelevant codes, but a real hardware input): R is
    identical to a plain ADD; only the carry-flag source differs (reserved
    codes are NOT in the adder-flag group, so C passes Cin rather than the
    adder carry — exactly as alu_ref models it).
    """
    # CPU-11
    s = cpu_builds.sim("alu")
    for a, b in VECTORS:
        s.poke("A", a)
        s.poke("B", b)
        s.poke("Op", 0)  # ADD
        s.poke("Cin", 0)
        s.step(SETTLE)
        add_r = s.peek("R")
        for op in (13, 14, 15):
            s.poke("Op", op)
            s.step(SETTLE)
            assert s.peek("R") == add_r, (
                f"reserved op={op} a={a:#06x} b={b:#06x}: "
                f"R={s.peek('R'):#06x} != ADD R={add_r:#06x}"
            )
