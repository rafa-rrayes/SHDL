"""SR16 golden model: a bit-exact architectural simulator of ISA.md.

This is the reference the gate-level CPU is tested against. It models
architectural state only (registers, PC, flags, memory, halted) — no FSM,
no buses — but charges the documented cycle cost per instruction so traces
line up with the hardware clock-for-clock.

    g = Golden()
    g.load(assemble(src))
    g.run()                  # until HALT (or the step limit trips)
    assert g.regs[1] == expected
"""

from __future__ import annotations

MEM_WORDS = 256  # must match RAM256 in ram.shdl (addresses alias mod 256)
_MASK16 = 0xFFFF

__all__ = ["Golden", "MEM_WORDS"]


def _sext(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


class Golden:
    def __init__(self):
        self.regs = [0] * 8
        self.pc = 0
        self.z = self.n = self.c = self.v = 0
        self.halted = False
        self.mem = [0] * MEM_WORDS

    # --- host interface -----------------------------------------------------

    def load(self, words: list[int]) -> None:
        if len(words) > MEM_WORDS:
            raise ValueError(f"program of {len(words)} words exceeds {MEM_WORDS}")
        for i, w in enumerate(words):
            self.mem[i] = w & _MASK16

    def run(self, max_steps: int = 10_000) -> int:
        """Execute until HALT; returns total clock cycles consumed."""
        cycles = 0
        for _ in range(max_steps):
            if self.halted:
                return cycles
            cycles += self.step()
        if not self.halted:
            raise RuntimeError(f"not halted after {max_steps} instructions")
        return cycles

    # --- helpers -------------------------------------------------------------

    def _rd_mem(self, addr: int) -> int:
        return self.mem[addr % MEM_WORDS]

    def _wr_mem(self, addr: int, value: int) -> None:
        self.mem[addr % MEM_WORDS] = value & _MASK16

    def _flags_zn(self, r: int) -> None:
        self.z = int(r == 0)
        self.n = (r >> 15) & 1

    def _add(self, a: int, b: int, cin: int) -> int:
        """16-bit add setting Z N C V; returns the masked result."""
        full = a + b + cin
        r = full & _MASK16
        self.c = full >> 16
        self.v = ((~(a ^ b)) & (a ^ r) & 0x8000) >> 15
        self._flags_zn(r)
        return r

    def _sub_flags(self, a: int, b: int) -> int:
        """a - b as a + ~b + 1 (C = no borrow, ARM convention)."""
        return self._add(a, (~b) & _MASK16, 1)

    # --- one instruction -----------------------------------------------------

    def step(self) -> int:
        """Execute one instruction; returns its cycle cost (0 when halted)."""
        if self.halted:
            return 0

        ir = self._rd_mem(self.pc)
        self.pc = (self.pc + 1) & _MASK16

        op = ir >> 12
        rd = (ir >> 9) & 7
        rs1 = (ir >> 6) & 7
        rs2 = (ir >> 3) & 7
        funct = ir & 7
        regs = self.regs
        cycles = 2

        if op == 0:  # ALU
            a, b = regs[rs1], regs[rs2]
            if funct == 0:
                regs[rd] = self._add(a, b, 0)
            elif funct == 1:
                regs[rd] = self._sub_flags(a, b)
            elif funct == 2:
                regs[rd] = a & b
                self._flags_zn(regs[rd])
            elif funct == 3:
                regs[rd] = a | b
                self._flags_zn(regs[rd])
            elif funct == 4:
                regs[rd] = a ^ b
                self._flags_zn(regs[rd])
            elif funct == 5:
                regs[rd] = a  # MOV: no flags
            elif funct == 6:
                self._sub_flags(a, b)  # CMP: flags only
            else:
                regs[rd] = self._add(a, b, self.c)

        elif op == 1:  # shifts / NOT (rs2 ignored; V never changes)
            a = regs[rs1]
            if funct == 0:  # SHL
                r, c = (a << 1) & _MASK16, (a >> 15) & 1
            elif funct == 1:  # SHR
                r, c = a >> 1, a & 1
            elif funct == 2:  # SAR
                r, c = (a >> 1) | (a & 0x8000), a & 1
            elif funct == 3:  # ROL
                r, c = ((a << 1) | (a >> 15)) & _MASK16, (a >> 15) & 1
            elif funct == 4:  # ROR
                r, c = (a >> 1) | ((a & 1) << 15), a & 1
            else:  # NOT (5; 6-7 behave as NOT)
                r, c = (~a) & _MASK16, self.c  # C unchanged
            regs[rd] = r
            self.c = c
            self._flags_zn(r)

        elif op == 2:  # LDI
            regs[rd] = _sext(ir, 8) & _MASK16

        elif op == 3:  # LDIH
            regs[rd] = ((ir & 0xFF) << 8) | (regs[rd] & 0xFF)

        elif op == 4:  # LD
            regs[rd] = self._rd_mem((regs[rs1] + _sext(ir, 6)) & _MASK16)

        elif op == 5:  # ST (data register sits in the rd field)
            self._wr_mem((regs[rs1] + _sext(ir, 6)) & _MASK16, regs[rd])

        elif op == 6:  # ADDI
            regs[rd] = self._add(regs[rs1], _sext(ir, 6) & _MASK16, 0)

        elif op == 7:  # Bcc
            taken = {
                0: self.z == 1,
                1: self.z == 0,
                2: self.c == 1,
                3: self.c == 0,
                4: self.n == 1,
                5: self.n == 0,
                6: self.n != self.v,
                7: self.n == self.v,
            }[rd]
            if taken:
                self.pc = (self.pc + _sext(ir, 9)) & _MASK16

        elif op == 8:  # JMP
            self.pc = ir & 0xFFF

        elif op == 9:  # CALL (pushes the already-incremented PC)
            regs[7] = (regs[7] - 1) & _MASK16
            self._wr_mem(regs[7], self.pc)
            self.pc = ir & 0xFFF

        elif op == 10:  # MISC
            if funct == 0:  # PUSH (old value, even R7)
                value = regs[rd]
                regs[7] = (regs[7] - 1) & _MASK16
                self._wr_mem(regs[7], value)
            elif funct == 1:  # POP (load wins for R7)
                value = self._rd_mem(regs[7])
                regs[7] = (regs[7] + 1) & _MASK16
                regs[rd] = value
                cycles = 3
            elif funct == 2:  # RET
                self.pc = self._rd_mem(regs[7])
                regs[7] = (regs[7] + 1) & _MASK16
                cycles = 3
            elif funct == 3:  # JR (register in rs1 field)
                self.pc = regs[rs1]
            elif funct == 4:  # NOP
                pass
            else:  # HALT (5; 6-7 reserved)
                self.halted = True

        else:  # opcodes B..F: reserved, trap to HALTED
            self.halted = True

        return cycles
