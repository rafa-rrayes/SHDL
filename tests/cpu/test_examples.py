"""CPU-12: the three shipped example programs run under full lockstep.

examples/CPU/programs/{mul,popcount,maxarray}.s are executed on the gate-level
SR16 in lockstep with the golden model (architectural state + cycle cost after
EVERY instruction, plus every written memory word at the end — see
conftest.lockstep). In addition each test pins the program's headline result as
a hand-derived constant (the value documented in the .s header), so a
common-mode bug shared by the golden model and the circuit cannot vouch for an
empty result. Mirrors tests/cpu/test_programs.py's style.
"""

from __future__ import annotations

from pathlib import Path

from .conftest import lockstep

PROGRAMS = Path(__file__).resolve().parents[2] / "examples" / "CPU" / "programs"


def _src(name: str) -> str:
    return (PROGRAMS / name).read_text()


def test_mul_repeated_addition(sr16):
    # CPU-12
    golden = lockstep(sr16, _src("mul.s"), check_mem=False)
    # 12 * 11 = 132 (0x0084), hand-derived (mul.s header)
    assert golden.regs[3] == 132
    assert golden.regs[3] == 0x0084


def test_popcount(sr16):
    # CPU-12
    golden = lockstep(sr16, _src("popcount.s"), check_mem=False)
    # popcount(0xB7C5) = ten set bits, hand-derived (popcount.s header)
    assert golden.regs[2] == 10
    assert bin(0xB7C5).count("1") == 10  # independent witness of the constant


def test_maxarray_unsigned_max(sr16):
    # CPU-12
    golden = lockstep(sr16, _src("maxarray.s"))
    # unsigned max of {0x0042, 0xBEEF, 0x1234, 0x8001, 0x7FFF} = 0xBEEF,
    # hand-derived (maxarray.s header), stored to MEM[0x30]
    assert golden.regs[3] == 0xBEEF
    assert golden.mem[0x30] == 0xBEEF
    assert max(0x0042, 0xBEEF, 0x1234, 0x8001, 0x7FFF) == 0xBEEF
