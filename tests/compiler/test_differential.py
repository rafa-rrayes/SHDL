"""Long random differential runs: every fixture and handwritten constant,
lockstep against BaseEval, all ports compared every cycle.

SHDLC_DIFF_CYCLES overrides the per-circuit cycle budget (default 150).
"""

from __future__ import annotations

import os
import random
import zlib

import pytest

from .harness import HANDWRITTEN, random_drive

CYCLES = int(os.environ.get("SHDLC_DIFF_CYCLES", "150"))

FIXTURE_NAMES = [
    "add2",
    "adder8",
    "alu",
    "add100",
    "srlatch",
    "clock",
    "passthru",
    "splitByte",
    "gatesDemo",
    "fullAdder",
]


def _seed(name: str) -> int:
    return zlib.crc32(name.encode("utf-8"))  # stable per-fixture seed


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_differential_fixture(builds, name):
    seed = _seed(name)
    dual = builds.dual_fixture(name, seed=seed)
    dual.compare_all()  # power-on state (init seeds) must already agree
    random_drive(dual, random.Random(seed), CYCLES)


@pytest.mark.parametrize("name", sorted(HANDWRITTEN))
def test_differential_handwritten(builds, name):
    seed = _seed(name)
    dual = builds.dual_from_text(name, HANDWRITTEN[name], seed=seed)
    dual.compare_all()
    random_drive(dual, random.Random(seed), CYCLES)
