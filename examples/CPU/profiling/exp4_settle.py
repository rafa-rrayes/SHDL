"""Exp 4: settle-margin search — smallest (t_settle, t_cap, t_gap) that stays golden-correct.

Correctness bar: full architectural lockstep vs sr16tools.golden after EVERY instruction
(pc, regs, flags, halted, per-instruction cycle count) on all three example programs.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sr16tools.asm import assemble
from sr16tools.driver import SR16
from sr16tools.golden import Golden

CPU_DIR = Path(__file__).resolve().parents[1]
LIB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sr16.dylib"

PROGRAMS = {
    p.stem: assemble(p.read_text()) for p in sorted((CPU_DIR / "programs").glob("*.s"))
}


def lockstep_ok(cpu: SR16, words: list[int], max_instr: int = 2000) -> tuple[bool, str]:
    golden = Golden()
    golden.load(words)
    cpu.reset()
    cpu.load_program(words)
    executed = 0
    while not golden.halted:
        if executed >= max_instr:
            return False, f"golden not halted after {max_instr} instr"
        want_cycles = golden.step()
        try:
            got_cycles = cpu.step_instruction()
        except RuntimeError as e:
            return False, f"instr #{executed}: {e}"
        executed += 1
        st = cpu.state()
        if got_cycles != want_cycles:
            return False, f"instr #{executed}: cycles {got_cycles} != {want_cycles}"
        if st["pc"] != golden.pc:
            return False, f"instr #{executed}: pc {st['pc']:#06x} != {golden.pc:#06x}"
        if st["regs"] != golden.regs:
            return False, f"instr #{executed}: regs {st['regs']} != {golden.regs}"
        got_f = (st["z"], st["n"], st["c"], st["v"])
        want_f = (golden.z, golden.n, golden.c, golden.v)
        if got_f != want_f:
            return False, f"instr #{executed}: flags {got_f} != {want_f}"
        if st["halted"] != int(golden.halted):
            return False, f"instr #{executed}: halted {st['halted']}"
    return True, f"ok ({executed} instr)"


def trial(t_settle: int, t_cap: int, t_gap: int) -> tuple[bool, str]:
    cpu = SR16(LIB, t_cap=t_cap, t_gap=t_gap, t_settle=t_settle)
    for name, words in PROGRAMS.items():
        ok, msg = lockstep_ok(cpu, words)
        if not ok:
            return False, f"{name}: {msg}"
    return True, "all programs lockstep-clean"


def search(label: str, lo_fail: int, hi_pass: int, mk) -> int:
    """Binary search the smallest passing value; mk(v) -> (t_settle, t_cap, t_gap)."""
    while hi_pass - lo_fail > 1:
        mid = (lo_fail + hi_pass) // 2
        ok, msg = trial(*mk(mid))
        print(f"  {label}={mid}: {'PASS' if ok else 'FAIL'}  {msg}")
        if ok:
            hi_pass = mid
        else:
            lo_fail = mid
    print(f"  -> minimal {label} = {hi_pass}")
    return hi_pass


def main():
    print(f"programs: { {k: len(v) for k, v in PROGRAMS.items()} }")

    print("== sweep t_settle (t_cap=16, t_gap=4 stock) ==")
    results = {}
    for ts in (200, 120, 80, 48, 24, 12, 6):
        ok, msg = trial(ts, 16, 4)
        results[ts] = ok
        print(f"  t_settle={ts}: {'PASS' if ok else 'FAIL'}  {msg}")
    lo = max((ts for ts, ok in results.items() if not ok), default=0)
    hi = min(ts for ts, ok in results.items() if ok)
    min_settle = search("t_settle", lo, hi, lambda v: (v, 16, 4))

    print("== shrink t_cap (at minimal settle + 0) ==")
    min_cap = search("t_cap", 0, 16, lambda v: (min_settle, v, 4))

    print("== shrink t_gap ==")
    ok, msg = trial(min_settle, min_cap, 0)
    print(f"  t_gap=0: {'PASS' if ok else 'FAIL'}  {msg}")
    min_gap = 0 if ok else search("t_gap", 0, 4, lambda v: (min_settle, min_cap, v))

    total = min_settle + 2 * min_cap + min_gap * 2
    print(f"== minimal clock: settle={min_settle} cap={min_cap} gap={min_gap} "
          f"-> {total} ticks/clock (stock 240) ==")

    # re-verify at the found minimum and time mul.s there + at a 25% margin
    for label, ts, tc, tg in (
        ("minimal", min_settle, min_cap, min_gap),
        ("margin(+25%)", -(-min_settle * 5 // 4), -(-min_cap * 5 // 4), max(min_gap, 1)),
    ):
        cpu = SR16(LIB, t_cap=tc, t_gap=tg, t_settle=ts)
        words = PROGRAMS["mul"]
        cpu.reset()
        cpu.load_program(words)
        t0 = time.perf_counter()
        cycles = cpu.run()
        dt = time.perf_counter() - t0
        st = cpu.state()
        assert st["regs"][3] == 132, st
        per_clock = ts + 2 * tc + 2 * tg
        print(f"  {label:13} settle={ts:3} cap={tc:2} gap={tg}: {per_clock:3} ticks/clock, "
              f"mul.s run = {dt * 1e3:6.1f} ms ({cycles} clocks)  "
              f"speedup vs stock {240 / per_clock:.1f}x")


if __name__ == "__main__":
    main()
