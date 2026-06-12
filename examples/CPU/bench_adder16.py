"""Benchmark: 100_000 random 16-bit additions through the compiled Adder16.

Flattens adder16.shdl, compiles it with the strict release flags, measures
the worst-case ripple-settle time empirically (full carry propagation in
both directions), then times three drive strategies over the same inputs:

    scalar  -- poke/step/peek per add through ctypes (5 FFI calls each)
    batch   -- one run_batch() call, exact `settle` ticks per add
    settle  -- one run_batch() call with fixed-point early exit

Every result of every mode is checked against Python's (a + b) — an
insufficient settle budget fails loudly instead of flattering the numbers.

    uv run python examples/CPU/bench_adder16.py
"""

from __future__ import annotations

import ctypes
import random
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flattener.pipeline import flatten_program
from shdlc.cc import lib_suffix
from shdlc.compile import build_library, compile_text
from shdlc.harness import STRICT_CFLAGS, Sim

CPU_DIR = REPO / "examples" / "CPU"
EXAMPLES = REPO / "examples"

N_ADDS = 100_000
SETTLE_MARGIN = 4  # ticks on top of the measured worst case
SEED = 0xC0FFEE


def measure_settle(sim: Sim) -> int:
    """Ticks until the longest carry chain settles, in both directions.

    0xFFFF + 1 ripples a carry through all 16 stages; dropping back to
    0 + 0 tears the chain down again.  The benchmark budget is the max
    of the two plus a small margin.
    """
    worst = 0
    sim.poke("Cin", 0)
    for a, b, sum_, cout in ((0xFFFF, 0x0001, 0, 1), (0, 0, 0, 0)):
        sim.poke("A", a)
        sim.poke("B", b)
        ticks = 0
        while not (sim.peek("Sum") == sum_ and sim.peek("Cout") == cout):
            sim.step(1)
            ticks += 1
            assert ticks < 1000, "adder did not settle"
        worst = max(worst, ticks)
    return worst


def main() -> None:
    src = CPU_DIR / "adder16.shdl"
    base_text = flatten_program(str(src), include_dirs=[str(EXAMPLES)]).text
    circuit, _ = compile_text(base_text)
    print(f"Adder16: {len(circuit.gates)} gates")

    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp) / f"adder16{lib_suffix()}"
        t0 = time.perf_counter()
        build_library(base_text, lib, cflags=STRICT_CFLAGS)
        print(f"build  : {(time.perf_counter() - t0) * 1e3:.1f} ms")

        sim = Sim(lib)
        sim.reset()

        settle = measure_settle(sim) + SETTLE_MARGIN
        print(f"settle : {settle} ticks ({settle - SETTLE_MARGIN} measured "
              f"+ {SETTLE_MARGIN} margin)")

        rng = random.Random(SEED)
        pairs = [(rng.getrandbits(16), rng.getrandbits(16)) for _ in range(N_ADDS)]

        def verify(results, mode):
            bad = sum(
                1
                for (a, b), (s, c) in zip(pairs, results)
                if s != (a + b) & 0xFFFF or c != (a + b) >> 16
            )
            assert bad == 0, (
                f"{mode}: {bad}/{N_ADDS} additions wrong — raise the settle budget"
            )

        def report(mode, elapsed, baseline=None):
            vs = f"  ({baseline / elapsed:5.1f}x scalar)" if baseline else ""
            print(f"{mode:7s}: {elapsed * 1e3:7.1f} ms   "
                  f"{N_ADDS / elapsed:11,.0f} adds/sec   "
                  f"{elapsed / N_ADDS * 1e9:7.1f} ns/add{vs}")

        # --- mode 1: scalar poke/step/peek loop through ctypes ---------------
        # Raw handles: this measures the circuit + ABI, not Sim's wrappers.
        poke, peek, step = sim._lib.poke, sim._lib.peek, sim._lib.step
        A, B, SUM, COUT = b"A", b"B", b"Sum", b"Cout"
        got: list[tuple[int, int]] = []
        t0 = time.perf_counter()
        for a, b in pairs:
            poke(A, a)
            poke(B, b)
            step(settle)
            got.append((peek(SUM), peek(COUT)))
        t_scalar = time.perf_counter() - t0
        verify(got, "scalar")
        report("scalar", t_scalar)

        # --- modes 2 + 3: one run_batch call (exact / fixed-point exit) ------
        # Frames are (A, B, Cin) per add, input-port declaration order; the
        # buffer prep is untimed setup, the C call is the measured work.
        in_buf = (ctypes.c_uint64 * (N_ADDS * 3))(
            *(v for a, b in pairs for v in (a, b, 0))
        )
        out_buf = (ctypes.c_uint64 * (N_ADDS * 2))()
        for mode, early in (("batch", 0), ("settle", 1)):
            t0 = time.perf_counter()
            sim._lib.run_batch(in_buf, out_buf, N_ADDS, settle, early)
            elapsed = time.perf_counter() - t0
            verify(
                [(out_buf[2 * k], out_buf[2 * k + 1]) for k in range(N_ADDS)], mode
            )
            report(mode, elapsed, baseline=t_scalar)

        print(f"verify : {N_ADDS:,} / {N_ADDS:,} additions correct in all 3 modes")


if __name__ == "__main__":
    main()
