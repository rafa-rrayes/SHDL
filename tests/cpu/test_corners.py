"""CPU-13: lockstep input-space corners no existing program reaches.

Two blind spots in the program/instruction suites:

1. **Writeback to R0.** No shipped program or directed test targets rd=0, yet
   R0 is an ordinary GPR (ISA.md §1 — there is no hardwired-zero register). A
   writeback path that special-cased rd=0 (a common RISC convention SR16 does
   *not* adopt) would be invisible everywhere else. We write R0 through every
   writeback source (ALU, immediate, memory load, stack pop) and witness the
   value both in the golden model and directly at the circuit's R0out pin.

2. **Shift-group V preservation with V pre-set.** ISA.md §3.2: "V is never
   changed by this group." Every other test reaches the shifts with V=0, so a
   bug that *cleared* V on a shift would pass. We pre-set V=1 with a signed
   ADD overflow, run each shift funct, and assert V stays 1 throughout.

Both run through conftest.lockstep, so the full architectural state and cycle
cost are already compared against the golden model after every instruction;
the explicit asserts add the hand-derived witness on top.
"""

from __future__ import annotations

from .conftest import lockstep


def test_writeback_to_r0_all_sources(sr16):
    # CPU-13: rd=0 writeback visibility across every RegWDataSel source.
    golden = lockstep(sr16, """
        ; ALU result -> R0
        LI   r1, 5
        LI   r2, 3
        ADD  r0, r1, r2        ; R0 = 8
        ; immediate -> R0 (LDI / LDIH writeback)
        LDI  r0, 0x21          ; R0 = 0x0021
        LDIH r0, 0x43          ; R0 = 0x4321
        ; memory load -> R0
        LI   r1, 0x50
        LI   r2, 0xCAFE
        ST   [r1], r2
        LD   r0, [r1]          ; R0 = 0xCAFE
        ; shift result -> R0
        LI   r1, 0x0001
        SHL  r0, r1            ; R0 = 2
        ; stack pop -> R0 (MEMRD writeback path)
        LI   r1, 0xBEEF
        PUSH r1
        POP  r0                ; R0 = 0xBEEF
        HALT
    """)
    # Hand-derived final R0, and the circuit must agree (lockstep already
    # compared all 8 regs every instruction; this pins the headline).
    assert golden.regs[0] == 0xBEEF
    assert sr16.state()["regs"][0] == 0xBEEF


def test_writeback_to_r0_zero_value_then_nonzero(sr16):
    # CPU-13: R0 is mutable in both directions (not stuck-at-zero, not
    # stuck-at-first-write). Write nonzero, then back to 0, then nonzero.
    golden = lockstep(sr16, """
        LI   r1, 0x1234
        ADD  r0, r1, r0        ; R0 = 0x1234
        SUB  r0, r0, r1        ; R0 = 0
        ADD  r0, r1, r1        ; R0 = 0x2468
        HALT
    """, check_mem=False)
    assert golden.regs[0] == 0x2468
    assert sr16.state()["regs"][0] == 0x2468


def test_shift_group_preserves_v_when_set(sr16):
    # CPU-13: every shift funct must leave a pre-set V untouched (ISA.md §3.2).
    # Pre-set V=1 via signed overflow (0x7FFF + 1 = 0x8000), then run each
    # shift; V must read 1 after every one. SHIFT_VALUES picked so the shift
    # itself produces no adder, hence cannot recompute V.
    golden = lockstep(sr16, """
        ; set V=1: 0x7FFF + 1 -> 0x8000 (signed overflow)
        LI   r1, 0x7FFF
        LI   r2, 1
        ADD  r3, r1, r2        ; V=1, N=1
        ; each shift must preserve V=1
        LI   r4, 0xAAAA
        SHL  r5, r4            ; V unchanged
        SHR  r5, r4            ; V unchanged
        SAR  r5, r4            ; V unchanged
        ROL  r5, r4            ; V unchanged
        ROR  r5, r4            ; V unchanged
        NOT  r5, r4            ; V unchanged
        HALT
    """, check_mem=False)
    # Golden never touched V in the shift group; witness the final value.
    assert golden.v == 1
    assert sr16.state()["v"] == 1


def test_shift_group_preserves_cleared_v(sr16):
    # CPU-13 complement: starting from V=0, the shifts must NOT spuriously set
    # V (a shift wiring into the V-overflow detector would flip it). The
    # adder-overflow corner 0x8000 is fed through every shift.
    golden = lockstep(sr16, """
        LI   r1, 1
        LI   r2, 2
        ADD  r3, r1, r2        ; V=0
        LI   r4, 0x8000        ; the value that maximizes adder-overflow risk
        SHL  r5, r4
        SHR  r5, r4
        SAR  r5, r4
        ROL  r5, r4
        ROR  r5, r4
        HALT
    """, check_mem=False)
    assert golden.v == 0
    assert sr16.state()["v"] == 0
