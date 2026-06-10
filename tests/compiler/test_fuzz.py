"""Differential fuzzing: random valid netlists from fuzz_gen vs BaseEval.

SHDLC_FUZZ (default 20) circuits, SHDLC_FUZZ_CYCLES (default 100) compared
cycles each. Seeds are stable (base + index); failures carry the seed, the
action log tail, and the full netlist text.
"""

from __future__ import annotations

import os
import random
import zlib

import pytest

from .fuzz_gen import gen_circuit
from .harness import random_drive

FUZZ_COUNT = int(os.environ.get("SHDLC_FUZZ", "20"))
FUZZ_CYCLES = int(os.environ.get("SHDLC_FUZZ_CYCLES", "100"))
FUZZ_SEED_BASE = 0x5_8D1C  # arbitrary, stable


@pytest.mark.parametrize("index", range(FUZZ_COUNT))
def test_fuzz_random_circuit(builds, index):
    seed = FUZZ_SEED_BASE + index
    rng = random.Random(seed)
    text = gen_circuit(rng)  # self-checked against BaseEval inside
    key = f"fuzz-{index}-{zlib.crc32(text.encode()):08x}"
    try:
        dual = builds.dual_from_text(key, text, seed=seed)
        dual.compare_all()
        random_drive(dual, rng, FUZZ_CYCLES)
    except AssertionError as e:
        raise AssertionError(
            f"{e}\n--- fuzz netlist (seed {seed}) ---\n{text}"
        ) from e
    except Exception as e:
        raise AssertionError(
            f"fuzz circuit failed to build/run (seed {seed}): {e!r}\n"
            f"--- fuzz netlist ---\n{text}"
        ) from e
