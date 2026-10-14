"""Real programs on the gate-level SR16 vs the golden model (lockstep).

Each test also asserts the headline result as a hand-derived constant
(fib(20) = 6765, gcd(252,105) = 21, ...) so a common-mode bug in the golden
model cannot silently vouch for the circuit.
"""

from __future__ import annotations

from .conftest import lockstep

FIB = """
        LI   r1, 0         ; fib(i)
        LI   r2, 1         ; fib(i+1)
        LI   r3, 20        ; iterations left
loop:   CMP  r3, r0
        BEQ  done
        ADD  r4, r1, r2
        MOV  r1, r2
        MOV  r2, r4
        ADDI r3, r3, -1
        JMP  loop
done:   LI   r5, 0xF0
        ST   [r5], r1      ; fib(20) -> mem[0xF0]
        HALT
"""


def test_fibonacci(sr16):
    golden = lockstep(sr16, FIB)
    assert golden.regs[1] == 6765  # fib(20), hand-derived
    assert golden.mem[0xF0] == 6765


ARRAY_SUM = """
        LI   r1, 0x40      ; table base
        LI   r2, 8         ; count
        LI   r3, 0         ; sum
loop:   CMP  r2, r0
        BEQ  done
        LD   r4, [r1]
        ADD  r3, r3, r4
        ADDI r1, r1, 1
        ADDI r2, r2, -1
        JMP  loop
done:   LI   r5, 0xF1
        ST   [r5], r3
        HALT
        .org 0x40
        .word 0x1111
        .word 0x2222
        .word 0xFFFF
        .word 0x0001
        .word 0x8000
        .word 0x8000
        .word 0x4242
        .word 0x0007
"""


def test_array_sum_with_wraparound(sr16):
    golden = lockstep(sr16, ARRAY_SUM)
    # (0x1111+0x2222+0xFFFF+1+0x8000+0x8000+0x4242+7) mod 2^16, hand-derived
    assert golden.regs[3] == 0x757C
    assert golden.mem[0xF1] == 0x757C


GCD = """
        LI   r1, 252
        LI   r2, 105
loop:   CMP  r1, r2
        BEQ  done
        BLO  less          ; unsigned r1 < r2
        SUB  r1, r1, r2
        JMP  loop
less:   SUB  r2, r2, r1
        JMP  loop
done:   HALT
"""


def test_gcd_euclid_subtraction(sr16):
    golden = lockstep(sr16, GCD)
    assert golden.regs[1] == 21  # gcd(252, 105), hand-derived


RECURSIVE_SUM = """
        LI   r1, 6
        CALL sum           ; r2 = 6+5+4+3+2+1
        LI   r3, 1         ; post-return marker
        HALT
sum:    CMP  r1, r0
        BNE  rec
        LI   r2, 0
        RET
rec:    PUSH r1
        ADDI r1, r1, -1
        CALL sum
        POP  r1
        ADD  r2, r2, r1
        RET
"""


def test_nested_call_stack_recursion(sr16):
    golden = lockstep(sr16, RECURSIVE_SUM)
    assert golden.regs[2] == 21  # sum(1..6), hand-derived
    assert golden.regs[3] == 1
    assert golden.regs[7] == 0  # stack fully unwound to reset SP


MEMCPY_WORDS = (0xDEAD, 0xBEEF, 0x0000, 0xFFFF, 0x1234, 0x8001)

MEMCPY = """
        LI   r1, 0x40      ; src
        LI   r2, 0x70      ; dst
        LI   r3, 6         ; words
loop:   CMP  r3, r0
        BEQ  done
        LD   r4, [r1]
        ST   [r2], r4
        ADDI r1, r1, 1
        ADDI r2, r2, 1
        ADDI r3, r3, -1
        JMP  loop
done:   HALT
        .org 0x40
""" + "\n".join(f"        .word {w:#06x}" for w in MEMCPY_WORDS)


def test_memcpy(sr16):
    golden = lockstep(sr16, MEMCPY)
    assert tuple(golden.mem[0x70:0x76]) == MEMCPY_WORDS
