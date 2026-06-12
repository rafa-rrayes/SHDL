"""Crash closure and the DET-4 flatten-idempotence property.

This file is the home of the frontend's robustness obligations that span more
than one module: the structural-core idempotence property (DET-4, enabled by
the AMB-29 `meta` production) and a focused crash-closure smoke proving that
the four reproduced raw-exception paths now surface as structured diagnostics
(LEX-9/LEX-10, PAR-8, ROB-6) rather than tracebacks.
"""

from __future__ import annotations

import pytest
from helpers import FIXTURES, TS

from flattener.diagnostics import ErrorCode, SHDLError
from flattener.lexer import lex
from flattener.parser import MAX_NESTING_DEPTH, parse_source
from flattener.pipeline import flatten_program
from flattener.source import SourceFile

# Fixtures whose emitted ports and gate names are plain identifiers — i.e. they
# do NOT contain the reserved `..._<digits>_` bus pattern (E0304) or `__`
# prefix (E0303), so the emitted Base SHDL is itself legal flattener input.
# (Bus-port fixtures like add2 emit `A_1_`, which re-flattening rightly
# rejects; the structural core they would round-trip to is identical, but the
# reserved-name guard makes a full round-trip impossible by design.)
IDEMPOTENT_FIXTURES = ["fullAdder", "gatesDemo", "constDemo", "srlatch"]


def _structural_core(text: str) -> str:
    """The component block — everything before the trailing `meta { … }`."""
    return text.split("\nmeta ", 1)[0]


# --------------------------------------------------------------------------- #
# DET-4: re-flattening emitted output yields a byte-identical structural core
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", IDEMPOTENT_FIXTURES)
def test_det4_reflatten_is_structurally_idempotent(name, tmp_path):
    # DET-4: flatten F, write its Base SHDL, flatten that again. The structural
    # core (the `component … { gates; connect { … } }` block) must be
    # byte-identical — the `meta` timestamp/source differ and are excluded.
    first = flatten_program(str(FIXTURES / f"{name}.shdl"), timestamp=TS)
    emitted = tmp_path / f"{name}.emitted.shdl"
    emitted.write_text(first.text)

    second = flatten_program(str(emitted), timestamp=TS)

    core1 = _structural_core(first.text)
    core2 = _structural_core(second.text)
    assert core1 == core2, (
        f"{name} is not idempotent.\n--- first ---\n{core1}\n"
        f"--- second ---\n{core2}"
    )
    # The netlist itself round-trips: same gates and same connections.
    assert first.flat.netlist.name == second.flat.netlist.name
    assert list(first.flat.netlist.gates) == list(second.flat.netlist.gates)
    assert len(first.flat.netlist.connections) == len(
        second.flat.netlist.connections
    )


def test_det4_third_pass_is_a_fixed_point(tmp_path):
    # DET-4: idempotence is a true fixed point — a third pass changes nothing.
    p1 = flatten_program(str(FIXTURES / "fullAdder.shdl"), timestamp=TS)
    f2 = tmp_path / "p2.shdl"
    f2.write_text(p1.text)
    p2 = flatten_program(str(f2), timestamp=TS)
    f3 = tmp_path / "p3.shdl"
    f3.write_text(p2.text)
    p3 = flatten_program(str(f3), timestamp=TS)
    assert _structural_core(p2.text) == _structural_core(p3.text)


# --------------------------------------------------------------------------- #
# Crash closure smoke: every reproduced raw exception is now a diagnostic.
# (Detailed per-site coverage lives in test_lexer/test_parser/test_cli; this
# is the consolidated "never a traceback" guard for the frontend.)
# --------------------------------------------------------------------------- #


def test_lex9_superscript_two_no_longer_crashes():
    # LEX-9 (regression): `²` reached int() with a raw ValueError; now E0101.
    with pytest.raises(SHDLError) as ei:
        lex(SourceFile("t.shdl", "/t.shdl", "x ²"))
    assert ei.value.diagnostic.code is ErrorCode.E0101


def test_lex10_invalid_utf8_no_longer_crashes(tmp_path):
    # LEX-10 (regression): undecodable bytes raised a raw UnicodeDecodeError
    # out of loader._read_source; now a positioned E0101.
    bad = tmp_path / "bad.shdl"
    bad.write_bytes(b"component M(A) -> (Y) { connect { A -> Y; } }\n\xff")
    with pytest.raises(SHDLError) as ei:
        flatten_program(str(bad), timestamp=TS)
    assert ei.value.diagnostic.code is ErrorCode.E0101


def test_par8_deep_nesting_no_longer_recurses(tmp_path):
    # PAR-8 (regression): 400-deep nesting raised RecursionError; now a capped
    # E0201 diagnostic. Verified at the cap boundary and well beyond it.
    for depth in (MAX_NESTING_DEPTH + 1, 1000):
        expr = "{" * depth + "1" + "}" * depth
        src = f"top component M(A[2]) -> (Y) {{ connect {{ A[{expr}] -> Y; }} }}"
        with pytest.raises(SHDLError) as ei:
            parse_source(SourceFile("t.shdl", "/t.shdl", src), "t")
        assert ei.value.diagnostic.code is ErrorCode.E0201, depth


def test_rob6_garbage_source_date_epoch_no_longer_crashes(monkeypatch):
    # ROB-6 (regression): a garbage SOURCE_DATE_EPOCH raised ValueError /
    # OverflowError out of resolve_timestamp; now a structured diagnostic.
    for value in ("notanumber", "9" * 30, "-" + "9" * 30):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", value)
        with pytest.raises(SHDLError) as ei:
            flatten_program(str(FIXTURES / "add2.shdl"), timestamp=None)
        assert ei.value.diagnostic.code is ErrorCode.E0001, value
        assert "SOURCE_DATE_EPOCH" in ei.value.diagnostic.message


def test_rob6_valid_source_date_epoch_still_works(monkeypatch):
    # ROB-6: the happy path is unchanged — a valid epoch still pins the time.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")
    out = flatten_program(str(FIXTURES / "add2.shdl"), timestamp=None)
    assert out.meta["doc"]["flattened_at"] == "2000-01-01T00:00:00Z"
