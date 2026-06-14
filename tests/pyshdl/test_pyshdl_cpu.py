"""SR16 CPU smoke test through the public PySHDL API.

Builds examples/CPU/sr16.shdl with the front-door constructor and runs a
small program using only Circuit methods (poke/peek/step_settle). The
clocking protocol mirrors sr16tools.driver (ISA.md §5); waits go through
``step_settle``, whose fixed-point early exit is observably identical to
``step`` with the same budget.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from SHDL import Circuit

REPO = Path(__file__).resolve().parents[2]
CPU_DIR = REPO / "examples" / "CPU"
EXAMPLES = REPO / "examples"

if str(CPU_DIR) not in sys.path:  # sr16tools (the assembler) lives in-tree
    sys.path.insert(0, str(CPU_DIR))

T_SETTLE, T_CAP, T_GAP = 200, 16, 4

PROGRAM = """
        LI   r1, 7
        LI   r2, 35
        ADD  r3, r1, r2
        HALT
"""


def clock(c: Circuit, n: int = 1) -> None:
    for _ in range(n):
        c.step_settle(T_SETTLE)
        c["Phi1"] = 1
        c.step_settle(T_CAP)
        c["Phi1"] = 0
        c.step_settle(T_GAP)
        c["Phi2"] = 1
        c.step_settle(T_CAP)
        c["Phi2"] = 0
        c.step_settle(T_GAP)


def load_program(c: Circuit, words: list[int]) -> None:
    c["LdEn"], c["LdWe"] = 1, 1
    for addr, word in enumerate(words):
        c["LdAddr"], c["LdData"] = addr, word
        c.step_settle(T_SETTLE)
        c["Phi1"] = 1
        c.step_settle(T_CAP)
        c["Phi1"] = 0
        c.step_settle(T_GAP)
    c["LdWe"], c["LdEn"] = 0, 0
    c.step_settle(T_SETTLE)


@pytest.fixture(scope="module")
def sr16(tmp_path_factory):
    with Circuit(
        CPU_DIR / "sr16.shdl",
        include_dirs=[EXAMPLES],
        build_dir=tmp_path_factory.mktemp("pyshdl-sr16"),
    ) as cpu:
        yield cpu


def test_sr16_runs_a_program(sr16):
    from sr16tools.asm import assemble

    assert sr16.timing.has_feedback  # a CPU is nothing but feedback
    load_program(sr16, assemble(PROGRAM))
    for _ in range(64):  # 4 instructions, at most 8 clocks each
        clock(sr16)
        if sr16["Halted"]:
            break
    assert sr16["Halted"] == 1
    assert sr16["R3out"] == 42
    assert sr16["R1out"] == 7
    assert sr16["R2out"] == 35
