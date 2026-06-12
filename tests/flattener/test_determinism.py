from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import FIXTURES, TS, flatten_fixture

from shdlc.baseshdl import parse_base
from shdlc.model import build_circuit

REPO = Path(__file__).resolve().parents[2]  # tests/flattener/ -> tests/ -> repo root

ALL_TOPS = sorted(p.stem for p in FIXTURES.glob("*.shdl") if p.stem != "stdgates")


def test_double_run_is_byte_identical():
    for name in ALL_TOPS:
        first = flatten_fixture(name)
        second = flatten_fixture(name)
        assert first.text == second.text, name
        assert first.meta == second.meta, name


def test_double_run_with_explicit_top():
    a = flatten_fixture("stdgates", top="XNOR")
    b = flatten_fixture("stdgates", top="XNOR")
    assert a.text == b.text


def test_source_date_epoch_pins_output(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")
    a = flatten_fixture("add2", timestamp=None)
    b = flatten_fixture("add2", timestamp=None)
    assert a.meta["doc"]["flattened_at"] == "2000-01-01T00:00:00Z"
    assert a.text == b.text


# ── DET-3: flattener byte-determinism across fresh child processes ──────────
# The compiler side (tests/compiler/test_determinism.py) proves generated C is
# hash-seed independent across subprocesses; the flattener emits meta from
# dicts whose order earlier phases fixed, so the same guarantee must hold for
# the Base SHDL text. Run the CLI in fresh interpreters under different
# PYTHONHASHSEED values and compare raw bytes. A timestamp is pinned so only
# the hash seed varies.


def _flatten_subprocess(fixture: str, seed: str) -> bytes:
    """Run `python -m flattener` in a child interpreter; return stdout bytes."""
    env = os.environ | {"PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "flattener",
            str(FIXTURES / f"{fixture}.shdl"),
            "--timestamp",
            TS,
        ],
        env=env,
        capture_output=True,  # bytes, compared exactly
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    return proc.stdout


@pytest.mark.parametrize("name", ["add2", "srlatch", "alu"])
def test_flattener_byte_identical_across_hash_seeds(name):
    # DET-3
    outputs = [_flatten_subprocess(name, seed) for seed in ("0", "424242")]
    assert outputs[0], "emitted Base SHDL must be non-empty"
    assert outputs[0] == outputs[1], (
        f"flattener output for {name} differs across PYTHONHASHSEED:\n"
        f"--- seed 0 ---\n{outputs[0].decode(errors='replace')}\n"
        f"--- seed 424242 ---\n{outputs[1].decode(errors='replace')}"
    )


# ── DET-6: non-ASCII emission under a non-UTF-8 locale ──────────────────────
# The round-trip half (emit -> parse_base) lives in test_emit.py. Here we pin
# the I/O boundary: the -o path writes UTF-8 explicitly, and the bare-stdout
# path writes UTF-8 through sys.stdout.buffer — both must succeed even under
# LC_ALL=C with PYTHONUTF8=0 (locale coercion off).

_NON_ASCII_SRC = '"""Café — ½ adder ²"""\ncomponent Main(A) -> (Y) {\n    connect { A -> Y; }\n}\n'
# Force the locale path: LC_ALL=C alone is overridden by PEP 540 UTF-8 mode, so
# PYTHONUTF8=0 is required to actually get an ASCII stdout codec.
_NON_UTF8_ENV = {"LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONIOENCODING": "ascii"}


def test_non_ascii_output_file_is_utf8_under_c_locale(tmp_path):
    # DET-6: the -o path writes UTF-8 regardless of locale.
    main = tmp_path / "main.shdl"
    main.write_text(_NON_ASCII_SRC, encoding="utf-8")
    out_path = tmp_path / "out.base"
    env = os.environ | {"PYTHONPATH": str(REPO), **_NON_UTF8_ENV}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "flattener",
            str(main),
            "--timestamp",
            TS,
            "-o",
            str(out_path),
        ],
        env=env,
        capture_output=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    # The file holds raw UTF-8 and re-parses; no mojibake, no escapes.
    text = out_path.read_text(encoding="utf-8")
    assert "Café — ½ adder ²" in text
    assert "\\u" not in text
    comp = parse_base(text)
    assert comp.meta["doc"]["description"] == "Café — ½ adder ²"


def test_non_ascii_stdout_never_raises_under_c_locale(tmp_path):
    # DET-6 / ROB-6: the bare-stdout path must not crash with a raw traceback.
    main = tmp_path / "main.shdl"
    main.write_text(_NON_ASCII_SRC, encoding="utf-8")
    env = os.environ | {"PYTHONPATH": str(REPO), **_NON_UTF8_ENV}
    proc = subprocess.run(
        [sys.executable, "-m", "flattener", str(main), "--timestamp", TS],
        env=env,
        capture_output=True,
        timeout=120,
    )
    # A raw UnicodeEncodeError traceback on stderr is the failure we forbid.
    assert b"UnicodeEncodeError" not in proc.stderr, proc.stderr.decode(errors="replace")
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")


# ── DET-7: every fixture crosses the flattener→shdlc seam ───────────────────
# Emitted Base SHDL must parse via shdlc.parse_base AND validate via
# build_circuit for every fixture — not just the 10 that ride the differential
# tier. stdgates carries several components, so it is flattened per top.


@pytest.mark.parametrize("name", ALL_TOPS)
def test_emitted_base_shdl_crosses_seam(name):
    # DET-7
    out = flatten_fixture(name)
    comp = parse_base(out.text)
    circ = build_circuit(comp)  # must not raise ModelError
    assert circ is not None
    # The parsed component matches the netlist the flattener produced.
    netlist = out.flat.netlist
    assert comp.name == netlist.name, name
    assert comp.inputs == netlist.inputs, name
    assert comp.outputs == netlist.outputs, name


@pytest.mark.parametrize("top", ["NAND", "NOR", "XNOR"])
def test_stdgates_components_cross_seam(top):
    # DET-7: the 16th fixture — flatten each of its components and cross.
    out = flatten_fixture("stdgates", top=top)
    comp = parse_base(out.text)
    circ = build_circuit(comp)
    assert circ is not None
    assert comp.name == top
