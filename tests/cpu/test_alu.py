"""Gate-level ALU vs the bit-exact Python reference (sr16tools.alu_ref)."""

from __future__ import annotations

import random

import pytest
from sr16tools.alu_ref import alu_ref

SETTLE = 100  # ripple-carry + mux tree + Z-reduce

VECTORS = [
    (0x0000, 0x0000),
    (0x0001, 0x0001),
    (0xFFFF, 0x0001),
    (0xFFFF, 0xFFFF),
    (0x7FFF, 0x0001),  # signed overflow on ADD
    (0x8000, 0x0001),  # signed overflow on SUB
    (0x8000, 0x8000),
    (0x1234, 0x5678),
    (0xAAAA, 0x5555),
    (0x0001, 0x0002),  # borrow on SUB
]


@pytest.mark.parametrize("op", list(range(13)))
def test_alu_matches_reference(cpu_builds, op):
    s = cpu_builds.sim("alu")
    rng = random.Random(1000 + op)
    vectors = VECTORS + [(rng.getrandbits(16), rng.getrandbits(16)) for _ in range(6)]
    for a, b in vectors:
        for cin in (0, 1):
            s.poke("A", a)
            s.poke("B", b)
            s.poke("Op", op)
            s.poke("Cin", cin)
            s.step(SETTLE)
            want_r, want_z, want_n, want_c, want_v = alu_ref(op, a, b, cin)
            got = (s.peek("R"), s.peek("Z"), s.peek("N"), s.peek("C"), s.peek("V"))
            assert got == (want_r, want_z, want_n, want_c, want_v), (
                f"op={op} a={a:#06x} b={b:#06x} cin={cin}: "
                f"got R,Z,N,C,V={got}, want {(want_r, want_z, want_n, want_c, want_v)}"
            )
