"""Codegen determinism: byte-identical C, in-process and across hash seeds.

Always compare C SOURCE bytes, never dylib bytes — Mach-O embeds LC_UUID,
which differs per link.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from .harness import REPO

# Runs in a child interpreter; argv[1] is a Base SHDL file. Writes the
# generated C to stdout as raw bytes.
_CHILD = (
    "import sys\n"
    "from shdlc.compile import compile_text\n"
    "with open(sys.argv[1], encoding='utf-8') as f:\n"
    "    text = f.read()\n"
    "sys.stdout.write(compile_text(text)[1])\n"
)


@pytest.mark.parametrize("name", ["add2", "srlatch"])
def test_compile_text_byte_identical_in_process(builds, name):
    from shdlc.compile import compile_text

    text = builds.fixture_text(name)
    c1 = compile_text(text)[1]
    c2 = compile_text(text)[1]
    assert c1, "generated C must be non-empty"
    assert c1 == c2


@pytest.mark.parametrize("name", ["add2", "srlatch"])
def test_compile_text_independent_of_hash_seed(builds, tmp_path, name):
    base = tmp_path / f"{name}.base"
    base.write_text(builds.fixture_text(name), encoding="utf-8")
    outputs = []
    for seed in ("0", "424242"):
        env = os.environ | {
            "PYTHONHASHSEED": seed,
            "PYTHONPATH": str(REPO),
        }
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD, str(base)],
            env=env,
            capture_output=True,  # bytes, not text: compare exactly
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr.decode(errors="replace")
        outputs.append(proc.stdout)
    assert outputs[0], "generated C must be non-empty"
    assert outputs[0] == outputs[1], "C source differs across PYTHONHASHSEED"
