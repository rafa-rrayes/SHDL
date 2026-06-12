"""Exp 3: per-asm-op census — clocks and wall time per opcode, mul.s + an all-ops probe."""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sr16tools.asm import assemble
from sr16tools.driver import SR16

LIB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sr16.dylib"
CPU_DIR = Path(__file__).resolve().parents[1]

ALU = ["ADD", "SUB", "AND", "OR", "XOR", "MOV", "CMP", "ADC"]
SHIFT = ["SHL", "SHR", "SAR", "ROL", "ROR", "NOT", "NOT?", "NOT?"]
MISC = ["PUSH", "POP", "RET", "JR", "NOP", "HALT", "HALT?", "HALT?"]
BCC = ["BEQ", "BNE", "BCS", "BCC", "BMI", "BPL", "BLT", "BGE"]


def mnemonic(word: int) -> str:
    op = word >> 12
    if op == 0b0000:
        return ALU[word & 7]
    if op == 0b0001:
        return SHIFT[word & 7]
    if op == 0b0010:
        return "LDI"
    if op == 0b0011:
        return "LDIH"
    if op == 0b0100:
        return "LD"
    if op == 0b0101:
        return "ST"
    if op == 0b0110:
        return "ADDI"
    if op == 0b0111:
        return BCC[(word >> 9) & 7]
    if op == 0b1000:
        return "JMP"
    if op == 0b1001:
        return "CALL"
    if op == 0b1010:
        return MISC[word & 7]
    return "RESERVED(HALT)"


def census(cpu: SR16, words: list[int], title: str) -> None:
    cpu.reset()
    cpu.load_program(words)
    stats = defaultdict(lambda: [0, 0, 0.0])  # mnemonic -> [count, clocks, secs]
    order = []
    while not cpu.peek("Halted"):
        pc = cpu.peek("PCout")
        word = words[pc] if pc < len(words) else 0
        t0 = time.perf_counter()
        clocks = cpu.step_instruction()
        dt = time.perf_counter() - t0
        m = mnemonic(word)
        if m not in stats:
            order.append(m)
        s = stats[m]
        s[0] += 1
        s[1] += clocks
        s[2] += dt
    total_clk = sum(s[1] for s in stats.values())
    total_t = sum(s[2] for s in stats.values())
    print(f"== {title}: {sum(s[0] for s in stats.values())} instr, "
          f"{total_clk} clocks, {total_t * 1e3:.0f} ms ==")
    print(f"  {'op':<10} {'n':>4} {'clk':>5} {'clk/n':>6} {'ms':>8} {'ms/op':>7} {'%time':>6}")
    for m in sorted(stats, key=lambda k: -stats[k][2]):
        n, clk, t = stats[m]
        print(f"  {m:<10} {n:>4} {clk:>5} {clk / n:>6.1f} {t * 1e3:>8.1f} "
              f"{t / n * 1e3:>7.2f} {t / total_t * 100:>5.1f}%")


def main():
    cpu = SR16(LIB)

    census(cpu, assemble((CPU_DIR / "programs" / "mul.s").read_text()), "mul.s (12 x 11)")
    print()

    # touch every instruction class once; R7=SP defaults to 0 -> stack at top of RAM
    probe = """
        LI   r1, 5
        LI   r2, 3
        ADD  r3, r1, r2
        SUB  r4, r1, r2
        AND  r5, r1, r2
        XOR  r5, r1, r2
        MOV  r6, r3
        CMP  r1, r2
        ADC  r3, r3, r2
        SHL  r4, r4
        SHR  r4, r4
        NOT  r5, r5
        ADDI r1, r1, 1
        ST   [r0+31], r3
        LD   r6, [r0+31]
        PUSH r3
        POP  r6
        CALL sub
        JMP  end
sub:    NOP
        RET
end:    BEQ  skip
skip:   HALT
"""
    census(cpu, assemble(probe), "all-ops probe")


if __name__ == "__main__":
    main()
