"""Exp 6: 16-bit multiplication throughput shootout.

Algorithms (all compute 12 x 11 = 132 in R3, golden-verified first):
  repadd    - programs/mul.s as-is: repeated addition, 6+6n clocks (n = multiplier)
  shiftadd  - generic 16x16 early-exit shift-add (loops bit_length(b) times)
  constfold - straight-line Horner chain for the constant x11 (what a compiler would emit)

Modes: latency (load+run per mult), throughput (K back-to-back mults in one program),
worst case operands, and --parallel (process-level scaling).
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sr16tools.asm import assemble
from sr16tools.driver import SR16
from sr16tools.golden import Golden

CPU_DIR = Path(__file__).resolve().parents[1]
LIB = "/tmp/sr16.dylib"
TUNED = dict(t_settle=29, t_cap=16, t_gap=4)  # Exp 4b: 26-28 is a parity-flickering marginal band

REPADD = (CPU_DIR / "programs" / "mul.s").read_text()

SHIFTADD = """
        LI   r1, {a}
        LI   r2, {b}
        LI   r3, 0
loop:   SHR  r2, r2         ; C = old bit0
        BCC  skip
        ADD  r3, r3, r1
skip:   SHL  r1, r1
        CMP  r2, r0         ; r0 = 0 at power-on, never written
        BNE  loop
        HALT
"""

CONSTFOLD = """
        LI   r1, 12
        MOV  r3, r1         ; x11 = 1011b, Horner MSB->LSB
        SHL  r3, r3
        SHL  r3, r3
        ADD  r3, r3, r1
        SHL  r3, r3
        ADD  r3, r3, r1
        HALT
"""

SHIFTADD_LOOP = """
        LI   r5, {k}
outer:  LI   r1, 12
        LI   r2, 11
        LI   r3, 0
loop:   SHR  r2, r2
        BCC  skip
        ADD  r3, r3, r1
skip:   SHL  r1, r1
        CMP  r2, r0
        BNE  loop
        ADDI r5, r5, -1
        BNE  outer
        HALT
"""

CONSTFOLD_LOOP = """
        LI   r5, {k}
        LI   r1, 12
outer:  MOV  r3, r1
        SHL  r3, r3
        SHL  r3, r3
        ADD  r3, r3, r1
        SHL  r3, r3
        ADD  r3, r3, r1
        ADDI r5, r5, -1
        BNE  outer
        HALT
"""


def golden_check(words, want_r3):
    g = Golden()
    g.load(words)
    steps = 0
    while not g.halted:
        g.step()
        steps += 1
        assert steps < 500_000
    assert g.regs[3] == want_r3 & 0xFFFF, f"golden r3={g.regs[3]} want {want_r3}"
    return g


def lockstep_ok(cpu, words, max_instr=5000):
    g = Golden()
    g.load(words)
    cpu.reset()
    cpu.load_program(words)
    n = 0
    while not g.halted:
        assert n < max_instr
        want = g.step()
        got = cpu.step_instruction()
        n += 1
        st = cpu.state()
        assert got == want and st["pc"] == g.pc and st["regs"] == g.regs, (
            f"diverged at instr {n}: {st} vs pc={g.pc} regs={g.regs}")
    return n


def run_timed(cpu, words):
    cpu.reset()
    t_l0 = time.perf_counter()
    cpu.load_program(words)
    t0 = time.perf_counter()
    cycles = cpu.run(max_instructions=200_000)
    t1 = time.perf_counter()
    return cycles, t0 - t_l0, t1 - t0  # cycles, load s, run s


def worker(k: int):
    """One process: K back-to-back constfold mults at tuned budgets; prints CSV."""
    cpu = SR16(LIB, **TUNED)
    words = assemble(CONSTFOLD_LOOP.format(k=k))
    cycles, t_load, t_run = run_timed(cpu, words)
    assert cpu.state()["regs"][3] == 132
    print(f"WORKER,{k},{cycles},{t_load + t_run:.4f}")


def parallel(ks=(1, 2, 4, 8, 10), k=80):
    print(f"== parallel scaling: N processes x {k} constfold mults each (tuned clock) ==")
    for n in ks:
        t0 = time.perf_counter()
        procs = [subprocess.Popen([sys.executable, __file__, "--worker", str(k)],
                                  stdout=subprocess.PIPE, text=True) for _ in range(n)]
        outs = [p.communicate()[0] for p in procs]
        wall = time.perf_counter() - t0
        assert all(p.returncode == 0 for p in procs), outs
        sim_s = [float(o.strip().split(",")[3]) for o in outs if o.startswith("WORKER")]
        mults = n * k
        print(f"  N={n:2}: {mults:4} mults in {wall:5.2f}s wall -> {mults / wall:6.1f} mults/s "
              f"(mean in-sim {sum(sim_s) / len(sim_s):.2f}s/worker)")


def main():
    sa = SHIFTADD.format(a=12, b=11)

    print("== correctness: golden + gate-level lockstep (tuned clock) ==")
    cpu = SR16(LIB, **TUNED)
    for name, src, r3 in (("repadd", REPADD, 132), ("shiftadd", sa, 132),
                          ("constfold", CONSTFOLD, 132),
                          ("shiftadd worst 65535x65535", SHIFTADD.format(a=65535, b=65535),
                           (65535 * 65535) & 0xFFFF)):
        words = assemble(src)
        golden_check(words, r3)
        n = lockstep_ok(cpu, words)
        print(f"  {name:<28} {len(words):>2} words, {n:>3} instr: lockstep-clean, r3 ok")

    print("== single-multiply latency (reset+load+run, one 12x11) ==")
    print(f"  {'algorithm':<10} {'budget':<6} {'clocks':>6} {'load ms':>8} {'run ms':>8} "
          f"{'total ms':>9} {'mults/s':>8}")
    for name, src in (("repadd", REPADD), ("shiftadd", sa), ("constfold", CONSTFOLD)):
        words = assemble(src)
        for label, kw in (("stock", {}), ("tuned", TUNED)):
            c = SR16(LIB, **kw)
            cycles, t_load, t_run = run_timed(c, words)
            assert c.state()["regs"][3] == 132
            tot = t_load + t_run
            print(f"  {name:<10} {label:<6} {cycles:>6} {t_load * 1e3:>8.1f} "
                  f"{t_run * 1e3:>8.1f} {tot * 1e3:>9.1f} {1 / tot:>8.1f}")

    print("== back-to-back throughput (K mults in one program, run phase only) ==")
    for name, tmpl, k in (("shiftadd", SHIFTADD_LOOP, 30), ("constfold", CONSTFOLD_LOOP, 80)):
        words = assemble(tmpl.format(k=k))
        golden_check(words, 132)
        for label, kw in (("stock", {}), ("tuned", TUNED)):
            c = SR16(LIB, **kw)
            cycles, _, t_run = run_timed(c, words)
            assert c.state()["regs"][3] == 132
            print(f"  {name:<10} {label:<6} K={k}: {cycles:>6} clocks "
                  f"({cycles / k:5.1f}/mult), {t_run:6.2f}s -> {k / t_run:6.1f} mults/s")

    print("== worst-case operands (65535 x 65535), tuned ==")
    words = assemble(SHIFTADD.format(a=65535, b=65535))
    c = SR16(LIB, **TUNED)
    cycles, _, t_run = run_timed(c, words)
    print(f"  shiftadd: {cycles} clocks, {t_run * 1e3:.0f} ms "
          f"(repadd would be 6+6x65535 = 393,216 clocks ~ {393216 * 68 * 23.2e-6:.0f}s tuned)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(int(sys.argv[2]))
    elif len(sys.argv) > 1 and sys.argv[1] == "--parallel":
        parallel()
    else:
        main()
