"""Exp 1: ABI microbenchmarks — per-tick cost, per-call overhead, name-scan order."""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sr16tools.driver import SR16

LIB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sr16.dylib"


def bench(fn, reps, inner=1):
    """Best-of-reps median: returns seconds per call of fn (fn runs `inner` work units)."""
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) / inner)
    return statistics.median(samples)


def main():
    cpu = SR16(LIB)
    cpu.reset()
    lib = cpu._lib

    # --- step(n) scaling: separates per-call overhead from per-tick cost ----
    print("== step(n) cost ==")
    rows = []
    for n in (0, 1, 2, 4, 16, 64, 240, 1000):
        reps = 200 if n <= 16 else (50 if n <= 240 else 10)
        t = bench(lambda: lib.step(n), reps)
        rows.append((n, t))
        print(f"  step({n:>4}): {t * 1e6:9.2f} us/call")
    # least squares fit t = a + b*n over n>=1
    xs = [n for n, _ in rows if n >= 1]
    ys = [t for n, t in rows if n >= 1]
    npts = len(xs)
    mx, my = sum(xs) / npts, sum(ys) / npts
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    print(f"  fit: t = {a * 1e6:.2f} us + n * {b * 1e6:.3f} us/tick")
    print(f"  => one tick = {b * 1e6:.2f} us ({b * 1e9 / 42530:.3f} ns/gate-eval)")
    print(f"  => one stock clock (240 ticks) = {240 * b * 1e3:.2f} ms")

    # --- poke: scan position 1 (Phi1) vs 6 (LdData) --------------------------
    print("== poke cost (in-port scan order: Phi1, Phi2, LdEn, LdWe, LdAddr, LdData) ==")
    for name, width in (("Phi1", 1), ("LdAddr", 16), ("LdData", 16)):
        t = bench(lambda: [lib.poke(name.encode(), 0) for _ in range(1000)], 30, inner=1000)
        print(f"  poke({name:7}) [{width:>2} bits]: {t * 1e9:7.0f} ns/call")
    cpu.step(1)  # clear dirty

    # --- peek: scan position effects + dirty (lazy tick) ----------------------
    print("== peek cost (out-port scan order: Halted ... R7out, then in-ports) ==")
    for name in ("Halted", "State", "R7out", "Phi1"):
        t = bench(lambda: [lib.peek(name.encode()) for _ in range(1000)], 30, inner=1000)
        print(f"  peek({name:7}) clean: {t * 1e9:7.0f} ns/call")

    def dirty_peek():
        lib.poke(b"LdAddr", 0)  # sets dirty -> next out-port peek ticks once
        return lib.peek(b"Halted")

    t = bench(lambda: [dirty_peek() for _ in range(100)], 30, inner=100)
    print(f"  poke+peek dirty (incl. 1 lazy tick): {t * 1e6:9.2f} us/call")

    # --- Python/ctypes layer overhead ---------------------------------------
    print("== Python wrapper overhead ==")
    t_raw = bench(lambda: [lib.step(0) for _ in range(1000)], 30, inner=1000)
    t_wrap = bench(lambda: [cpu.step(0) for _ in range(1000)], 30, inner=1000)
    t_peek_wrap = bench(lambda: [cpu.peek("Halted") for _ in range(1000)], 30, inner=1000)
    print(f"  raw  lib.step(0):       {t_raw * 1e9:7.0f} ns/call (pure ctypes dispatch)")
    print(f"  cpu.step(0):            {t_wrap * 1e9:7.0f} ns/call (+method)")
    print(f"  cpu.peek('Halted'):     {t_peek_wrap * 1e9:7.0f} ns/call (+encode)")


if __name__ == "__main__":
    main()
