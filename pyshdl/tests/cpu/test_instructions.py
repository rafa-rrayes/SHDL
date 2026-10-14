"""Per-instruction directed tests: every opcode, funct and cond of ISA.md §3.

All programs run through ``conftest.lockstep``: architectural state and cycle
cost are compared against the golden model after EVERY instruction, and every
memory word the golden model wrote is compared through the DMA port at the
end. The golden model was itself cross-checked line-by-line against ISA.md
(the document wins on any disagreement).

Reserved encodings (shift functs 6–7, MISC functs 6–7, opcodes 0xB–0xF) are
emitted with ``.word`` since the assembler refuses to produce them.
"""

from __future__ import annotations

import pytest

from .conftest import lockstep

# --- op 0000: ALU group ------------------------------------------------------


def test_alu_add_sub_adc_flag_corners(sr16):
    lockstep(
        sr16,
        """
        ; ADD: carry + zero
        LI   r1, 0xFFFF
        LI   r2, 1
        ADD  r3, r1, r2        ; 0x0000, Z=1 C=1 V=0
        ; ADD: signed overflow
        LI   r1, 0x7FFF
        ADD  r4, r1, r2        ; 0x8000, N=1 V=1 C=0
        ; ADD: both carry and overflow
        LI   r1, 0x8000
        LI   r2, 0x8000
        ADD  r5, r1, r2        ; 0x0000, Z=1 C=1 V=1
        ADD  r6, r0, r0        ; zero operands
        ; rd = rs1 = rs2 aliasing
        LI   r3, 5
        ADD  r3, r3, r3        ; 10
        ; SUB: no-borrow / borrow / zero / overflow (ARM C convention)
        LI   r1, 5
        LI   r2, 3
        SUB  r4, r1, r2        ; 2, C=1 (no borrow)
        SUB  r5, r2, r1        ; -2, N=1 C=0
        SUB  r6, r1, r1        ; 0, Z=1 C=1
        LI   r1, 0x8000
        LI   r2, 1
        SUB  r3, r1, r2        ; 0x7FFF, V=1 C=1
        ; ADC: with C=1 then with C=0
        LI   r1, 0xFFFF
        LI   r2, 1
        ADD  r3, r1, r2        ; sets C=1
        LI   r4, 10
        LI   r5, 20
        ADC  r6, r4, r5        ; 31
        ADD  r3, r4, r5        ; sets C=0
        ADC  r6, r4, r5        ; 30
        ; ADC carry chain: 0xFFFF + 0 + C
        LI   r1, 0xFFFF
        ADD  r3, r1, r2        ; C=1
        ADC  r3, r1, r0        ; 0x0000, Z=1 C=1
        HALT
    """,
        check_mem=False,
    )


def test_alu_logic_mov_cmp(sr16):
    lockstep(
        sr16,
        """
        LI   r1, 0xAAAA
        LI   r2, 0x5555
        AND  r3, r1, r2        ; 0, Z=1
        OR   r4, r1, r2        ; 0xFFFF, N=1
        XOR  r5, r1, r2        ; 0xFFFF
        XOR  r6, r1, r1        ; 0, Z=1
        LI   r2, 0xFFFF
        AND  r3, r1, r2        ; 0xAAAA, N=1
        OR   r4, r0, r0        ; 0, Z=1
        ; MOV copies and must NOT touch flags (CMP sets them first)
        LI   r1, 3
        LI   r2, 5
        CMP  r1, r2            ; N=1, C=0
        MOV  r6, r1
        CMP  r2, r1            ; N=0, C=1
        MOV  r6, r2
        ; CMP writes flags only, never a register
        LI   r3, 99
        CMP  r3, r3            ; Z=1 C=1, r3 stays 99
        HALT
    """,
        check_mem=False,
    )


# --- op 0001: shift group ----------------------------------------------------

SHIFT_VALUES = (0x0001, 0x8000, 0xAAAA, 0xFFFF, 0x8001, 0)


def test_shift_group_all_functs(sr16):
    body = []
    for v in SHIFT_VALUES:
        body += [
            f"LI r1, {v:#06x}",
            "SHL r2, r1",
            "SHR r3, r1",
            "SAR r4, r1",
            "ROL r5, r1",
            "ROR r6, r1",
            "NOT r2, r1",
        ]
    lockstep(sr16, "\n".join(body) + "\nHALT\n", check_mem=False)


def test_shift_not_preserves_carry(sr16):
    lockstep(
        sr16,
        """
        LI   r1, 5
        LI   r2, 3
        CMP  r1, r2        ; C=1
        NOT  r3, r1        ; C must stay 1
        CMP  r2, r1        ; C=0
        NOT  r4, r1        ; C must stay 0
        ; rd == rs1 aliasing
        LI   r5, 0x00F0
        NOT  r5, r5
        SHL  r5, r5
        HALT
    """,
        check_mem=False,
    )


def test_shift_reserved_functs_behave_as_not(sr16):
    # funct 6 / 7 (op=0001, rd=2, rs1=1): ISA.md §3.2 — behave exactly as NOT
    lockstep(
        sr16,
        """
        LI    r1, 0x1234
        .word 0x1446       ; op=1 rd=2 rs1=1 funct=6
        .word 0x1647       ; op=1 rd=3 rs1=1 funct=7
        HALT
    """,
        check_mem=False,
    )


# --- op 0010/0011: immediates ------------------------------------------------


def test_immediates_ldi_ldih(sr16):
    lockstep(
        sr16,
        """
        LDI  r1, 0         ; 0x0000, Z untouched (LDI sets no flags)
        LDI  r2, 127       ; 0x007F
        LDI  r3, -128      ; 0xFF80 (sign extension)
        LDI  r4, -1        ; 0xFFFF
        LDI  r5, 255       ; 0xFFFF (raw 0xFF sign-extends)
        ; LDIH overwrites the high byte, preserves the low byte
        LDI  r1, 0x34
        LDIH r1, 0x12      ; 0x1234
        LDI  r2, -1        ; 0xFFFF
        LDIH r2, 0         ; 0x00FF — LDI's sign extension must not leak
        LDIH r3, 0xAB      ; high byte over previous 0xFF80 -> 0xAB80
        ; LI pseudo-op: one-word and two-word forms
        LI   r4, 100
        LI   r5, -100
        LI   r6, 0x8001
        LI   r1, 0xFFFF
        HALT
    """,
        check_mem=False,
    )


# --- op 0100/0101/0110: memory + ADDI ---------------------------------------


def test_memory_ld_st_offsets_and_aliasing(sr16):
    lockstep(
        sr16,
        """
        LI   r1, 0x70
        LI   r2, 0xBEEF
        ST   [r1], r2
        LD   r3, [r1]
        ST   [r1+31], r2       ; max simm6
        LD   r4, [r1+31]
        ST   [r1-32], r2       ; min simm6
        LD   r5, [r1-32]
        ; physical aliasing: address mod 256 (ISA.md §1)
        LI   r1, 0x0140        ; 320 -> word 0x40
        LI   r2, 0xCAFE
        ST   [r1], r2
        LI   r3, 0x40
        LD   r4, [r3]          ; reads 0xCAFE through the alias
        ; negative effective address wraps mod 2^16 then aliases
        LI   r1, 0x10
        ST   [r1-32], r2       ; 0x10-32 = 0xFFF0 -> word 0xF0
        ; LD into its own base register
        LI   r1, 0x70
        LD   r1, [r1]          ; r1 <- 0xBEEF
        HALT
    """,
    )


def test_addi_edges_and_flags(sr16):
    lockstep(
        sr16,
        """
        LI   r1, 100
        ADDI r2, r1, 31        ; max imm
        ADDI r3, r1, -32       ; min imm
        ADDI r4, r0, 0         ; Z=1
        LI   r1, 0xFFFF
        ADDI r5, r1, 1         ; 0, Z=1 C=1
        LI   r1, 0x7FFF
        ADDI r6, r1, 1         ; 0x8000, N=1 V=1
        ADDI r1, r1, -1        ; rd == rs1
        HALT
    """,
        check_mem=False,
    )


# --- op 0111: all 8 branch conditions, taken and not taken -------------------


def test_branch_conditions_all_taken_and_not(sr16):
    # r6 accumulates a path signature; every Bcc gets a taken and a
    # not-taken exercise. Flag recipes (via CMP a, b = flags of a-b):
    #   5,5 -> Z=1 C=1 N=0 V=0        5,3 -> C=1 N=0 V=0
    #   3,5 -> C=0 N=1 V=0            0x8000,1 -> N=0 V=1 C=1
    #   0x7FFF,0xFFFF -> N=1 V=1 C=0
    lockstep(
        sr16,
        """
        LI   r6, 0
        LI   r1, 5
        LI   r2, 5
        LI   r3, 3
        CMP  r1, r2
        BEQ  t1
        ADDI r6, r6, 1     ; skipped
t1:     CMP  r1, r3
        BEQ  t2            ; not taken
        ADDI r6, r6, 2
t2:     CMP  r1, r3
        BNE  t3
        ADDI r6, r6, 3     ; skipped
t3:     CMP  r1, r2
        BNE  t4            ; not taken
        ADDI r6, r6, 4
t4:     CMP  r1, r3        ; C=1
        BCS  t5
        ADDI r6, r6, 5     ; skipped
t5:     CMP  r3, r1        ; C=0
        BCS  t6            ; not taken
        ADDI r6, r6, 6
t6:     CMP  r3, r1        ; C=0
        BCC  t7
        ADDI r6, r6, 7     ; skipped
t7:     CMP  r1, r3        ; C=1
        BCC  t8            ; not taken
        ADDI r6, r6, 8
t8:     CMP  r3, r1        ; N=1
        BMI  t9
        ADDI r6, r6, 9     ; skipped
t9:     CMP  r1, r3        ; N=0
        BMI  t10           ; not taken
        ADDI r6, r6, 10
t10:    CMP  r1, r3        ; N=0
        BPL  t11
        ADDI r6, r6, 11    ; skipped
t11:    CMP  r3, r1        ; N=1
        BPL  t12           ; not taken
        ADDI r6, r6, 12
        ; signed: BLT taken on N=1 V=0 and on N=0 V=1
t12:    CMP  r3, r1        ; N=1 V=0
        BLT  t13
        ADDI r6, r6, 13    ; skipped
t13:    LI   r4, 0x8000
        LI   r5, 1
        CMP  r4, r5        ; N=0 V=1 (0x8000 < 1 signed)
        BLT  t14
        ADDI r6, r6, 14    ; skipped
t14:    CMP  r1, r3        ; N=0 V=0
        BLT  t15           ; not taken
        ADDI r6, r6, 15
        ; BGE taken on N=V (both 0, then both 1)
t15:    CMP  r1, r3        ; N=0 V=0
        BGE  t16
        ADDI r6, r6, 16    ; skipped
t16:    LI   r4, 0x7FFF
        LI   r5, 0xFFFF
        CMP  r4, r5        ; N=1 V=1 (0x7FFF >= -1 signed)
        BGE  t17
        ADDI r6, r6, 17    ; skipped
t17:    CMP  r3, r1        ; N=1 V=0
        BGE  t18           ; not taken
        ADDI r6, r6, 18
t18:    HALT
    """,
        check_mem=False,
    )


def test_branch_backward(sr16):
    lockstep(
        sr16,
        """
        LI   r1, 4
        LI   r2, 0
loop:   ADD  r2, r2, r1
        ADDI r1, r1, -1
        CMP  r1, r0
        BNE  loop          ; backward, taken 3 times
        HALT
    """,
        check_mem=False,
    )


# --- op 1000/1001 + MISC jumps: JMP / CALL / JR / RET ------------------------


def test_jmp_jr(sr16):
    lockstep(
        sr16,
        """
        JMP  over
        LI   r1, 99        ; must be skipped
over:   LI   r2, 7
        LI   r3, target
        JR   r3
        LI   r1, 98        ; must be skipped
target: LI   r4, 1
        HALT
    """,
        check_mem=False,
    )


def test_call_ret_nested(sr16):
    lockstep(
        sr16,
        """
        LI   r1, 1
        CALL f
        LI   r4, 4         ; runs after RET
        HALT
f:      ADDI r1, r1, 10
        CALL g             ; nested call
        ADDI r1, r1, 20
        RET
g:      ADDI r1, r1, 31
        RET
    """,
    )


# --- op 1010: stack & control ------------------------------------------------


def test_push_pop_stack_discipline(sr16):
    lockstep(
        sr16,
        """
        ; R7 = 0 at reset: first PUSH wraps to top of RAM (ISA.md §1)
        LI   r1, 0x1111
        LI   r2, 0x2222
        PUSH r1            ; r7: 0 -> 0xFFFF, mem[0xFF] = 0x1111
        PUSH r2
        POP  r3            ; 0x2222 (LIFO)
        POP  r4            ; 0x1111
        ; PUSH R7 stores the OLD value
        LI   r7, 0x80
        PUSH r7            ; mem[0x7F] = 0x80
        POP  r5            ; 0x80
        ; POP R7: the loaded value wins over the SP increment
        LI   r6, 0x55
        PUSH r6
        POP  r7            ; r7 = 0x55
        HALT
    """,
    )


def test_nop_and_halt(sr16):
    golden = lockstep(
        sr16,
        """
        NOP
        LI   r1, 1
        NOP
        HALT
        LI   r2, 99        ; must never run
    """,
        check_mem=False,
    )
    assert golden.regs[2] == 0
    # HALTED is terminal (ISA.md §4): extra clocks change nothing
    before = sr16.state()
    sr16.clock(3)
    assert sr16.state() == before


RESERVED_WORDS = [
    0xA006,  # MISC funct 6 (reserved -> HALT)
    0xA007,  # MISC funct 7 (reserved -> HALT)
    0xB000,
    0xC123,
    0xDFFF,
    0xE000,
    0xF00F,  # opcodes 1011..1111
]


@pytest.mark.parametrize("word", [hex(w) for w in RESERVED_WORDS])
def test_reserved_encodings_trap_to_halt(sr16, word):
    golden = lockstep(
        sr16,
        f"""
        LI    r1, 7
        .word {word}
        LI    r2, 99       ; canary: must never run
    """,
        check_mem=False,
    )
    assert golden.halted and golden.regs[2] == 0


def test_pc_wrap_and_fetch_aliasing(sr16):
    """PC is 16-bit; instruction fetch aliases mod 2^A (ISA.md §1).

    JR to 0xFFFF fetches mem[0xFF] (HALT) and the incremented PC wraps to 0.
    JMP to 0x105 fetches mem[0x05].
    """
    golden = lockstep(
        sr16,
        """
        JMP  0x105         ; lands on the word at physical 0x05
        LI   r1, 99        ; never runs
        .org 0x05
        LI   r2, 42        ; executed with PC = 0x105
        LI   r3, 0xFFFF
        JR   r3            ; PC = 0xFFFF -> fetches mem[0xFF]
        LI   r1, 98        ; never runs
        .org 0xFF
        .word 0xA005       ; HALT at the top physical word
    """,
        check_mem=False,
    )
    assert golden.regs[2] == 42
    assert golden.regs[1] == 0
    assert golden.pc == 0  # 0xFFFF + 1 wrapped


# --- DMA load/readback fidelity across the full address space ----------------


def test_program_load_fidelity_full_image(sr16):
    image = [(i * 0x0101 ^ 0xA5A5) & 0xFFFF for i in range(256)]
    sr16.reset()
    sr16.load_program(image)
    for addr in range(256):
        got = sr16.read_mem(addr)
        assert got == image[addr], f"mem[{addr:#04x}]: {got:#06x} != {image[addr]:#06x}"
