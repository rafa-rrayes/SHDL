"""Exp 5a: host-overhead ceiling — Python clock loop vs one giant step() call.

If 74 clocks of Python-orchestrated stepping cost the same as step(74*67) raw,
no driver rewrite (C, batching, fewer peeks) can buy anything.
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sr16tools.driver import SR16

LIB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sr16.dylib"


def timeit(fn, reps=5):
    return statistics.median(min((time.perf_counter(), fn(), time.perf_counter()))
                             if False else
                             [_one(fn) for _ in range(reps)])


def _one(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def main():
    for ts, tc, tg, label in ((200, 16, 4, "stock"), (27, 16, 4, "tuned")):
        cpu = SR16(LIB, t_settle=ts, t_cap=tc, t_gap=tg)
        cpu.reset()
        per_clock = ts + 2 * tc + 2 * tg
        n_ticks = 74 * per_clock

        t_loop = timeit(lambda: cpu.clock(74))
        t_instr = timeit(lambda: [cpu.step_instruction() for _ in range(37)])
        t_raw = timeit(lambda: cpu.step(n_ticks))

        print(f"== {label}: {per_clock} ticks/clock, 74 clocks = {n_ticks} ticks ==")
        print(f"  step({n_ticks}) single call : {t_raw * 1e3:7.1f} ms  (floor: zero host involvement)")
        print(f"  clock(74) Python loop    : {t_loop * 1e3:7.1f} ms  "
              f"(+{(t_loop - t_raw) / t_raw * 100:.2f}% = poke/step orchestration)")
        print(f"  37x step_instruction()   : {t_instr * 1e3:7.1f} ms  "
              f"(+{(t_instr - t_raw) / t_raw * 100:.2f}% = + Halted/State peeks)")


if __name__ == "__main__":
    main()
