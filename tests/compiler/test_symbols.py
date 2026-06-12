"""Exported-symbol hygiene: exactly the release ABI, nothing else.

shdlc_goals.md §8: only public API functions are visible symbols; everything
else is static, so multiple SHDL libraries can coexist in one process.
"""

from __future__ import annotations

import string
import subprocess
import sys

import pytest

ABI = {  # macOS C symbols carry a leading _
    "_reset",
    "_poke",
    "_peek",
    "_step",
    "_step_settle",
    "_run_batch",
}


@pytest.mark.skipif(sys.platform != "darwin", reason="nm -gU contract is macOS-specific")
def test_exported_symbols_are_exactly_the_abi(builds):
    lib = builds.fixture_lib("add2")
    out = subprocess.run(
        ["nm", "-gU", str(lib)],  # -g: external only; -U: drop undefined
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    exported = set()
    for line in out.splitlines():
        parts = line.split()
        # "0000000000003f50 T _reset" — keep any defined symbol type letter.
        if len(parts) == 3 and len(parts[1]) == 1 and parts[1] in string.ascii_letters:
            exported.add(parts[2])
    assert exported == ABI, f"unexpected export set: {sorted(exported)}"
