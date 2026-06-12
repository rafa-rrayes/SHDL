"""Bit-exact reference for the ALU component (alu.shdl).

Mirrors the *hardware outputs*, including the pass-through/always-computed
flag behavior (C passes Cin for ops that don't drive it; V is always the
adder overflow). Flag write gating is the control unit's job, not the ALU's.
"""

from __future__ import annotations

MASK = 0xFFFF

ADD, SUB, ADC, AND, OR, XOR, MOV, NOT = range(8)
SHL, SHR, SAR, ROL, ROR = range(8, 13)


def alu_ref(op: int, a: int, b: int, cin: int) -> tuple[int, int, int, int, int]:
    """(R, Z, N, C, V) for the 4-bit internal op, 16-bit a/b, 1-bit cin."""
    a &= MASK
    b &= MASK

    b2 = (b ^ MASK) if op == SUB else b
    cin_eff = 1 if op == SUB else (cin if op == ADC else 0)
    total = a + b2 + cin_eff
    sum16 = total & MASK
    cout = (total >> 16) & 1
    v = 1 if ((~(a ^ b2)) & (a ^ sum16) & 0x8000) else 0

    results = {
        ADD: sum16, SUB: sum16, ADC: sum16,
        AND: a & b, OR: a | b, XOR: a ^ b,
        MOV: a, NOT: (~a) & MASK,
        SHL: (a << 1) & MASK,
        SHR: a >> 1,
        SAR: (a >> 1) | (a & 0x8000),
        ROL: ((a << 1) & MASK) | (a >> 15),
        ROR: (a >> 1) | ((a & 1) << 15),
        13: sum16, 14: sum16, 15: sum16,
    }
    r = results[op]

    z = 1 if r == 0 else 0
    n = (r >> 15) & 1
    if op in (ADD, SUB, ADC):
        c = cout
    elif op in (SHL, ROL):
        c = (a >> 15) & 1
    elif op in (SHR, SAR, ROR):
        c = a & 1
    else:
        c = cin
    return r, z, n, c, v
