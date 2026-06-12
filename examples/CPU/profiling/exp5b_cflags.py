"""Exp 5b: tick-cost vs compiler flags — rebuild sr16 with flag variants, measure ns/tick."""

import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from flattener.pipeline import flatten_program
from shdlc.compile import build_library
from shdlc.harness import Sim

BASE = ["-std=c11", "-fPIC", "-shared", "-fvisibility=hidden"]
VARIANTS = {
    "O2 (stock)": BASE + ["-O2"],
    "O3": BASE + ["-O3"],
    "O2 +mcpu=native": BASE + ["-O2", "-mcpu=native"],
    "O3 +mcpu=native": BASE + ["-O3", "-mcpu=native"],
    "O1": BASE + ["-O1"],
}

N_GATES = 42530


def ns_per_tick(sim: Sim, n=8000, reps=5) -> float:
    sim.step(2000)  # warmup
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        sim.step(n)
        samples.append((time.perf_counter() - t0) / n)
    return statistics.median(samples) * 1e9


def main():
    out_dir = Path("/tmp/sr16_flags")
    out_dir.mkdir(exist_ok=True)

    print("flattening sr16 ...")
    text = flatten_program(
        str(REPO / "examples/CPU/sr16.shdl"),
        include_dirs=[str(REPO / "examples")],
        timestamp="2026-01-01T00:00:00Z",
    ).text

    print(f"{'variant':<18} {'build':>7} {'us/tick':>8} {'ns/gate':>8} {'vs stock':>8}")
    base_tick = None
    for name, flags in VARIANTS.items():
        lib = out_dir / (
            name.replace(" ", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("+", "")
            .replace("=", "-")
            + ".dylib"
        )
        t0 = time.perf_counter()
        if not lib.exists():
            build_library(text, lib, cflags=tuple(flags))
        t_build = time.perf_counter() - t0
        tick_ns = ns_per_tick(Sim(lib))
        if base_tick is None:
            base_tick = tick_ns
        print(
            f"{name:<18} {t_build:6.1f}s {tick_ns / 1e3:8.2f} "
            f"{tick_ns / N_GATES:8.3f} {base_tick / tick_ns:7.2f}x"
        )


if __name__ == "__main__":
    main()
