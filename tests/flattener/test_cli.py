import os
import subprocess
import sys

from helpers import FIXTURES, TS, flatten_fixture

from shdlc.baseshdl import parse_base
from flattener.cli import main

ADD2 = str(FIXTURES / "add2.shdl")
STDGATES = str(FIXTURES / "stdgates.shdl")


def test_writes_to_stdout(capsys):
    assert main([ADD2, "--timestamp", TS]) == 0
    captured = capsys.readouterr()
    assert captured.out == flatten_fixture("add2").text
    assert captured.err == ""


def test_writes_to_output_file(tmp_path, capsys):
    dest = tmp_path / "out.bshdl"
    assert main([ADD2, "--timestamp", TS, "-o", str(dest)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert dest.read_text() == flatten_fixture("add2").text


def test_top_required_when_ambiguous(capsys):
    assert main([STDGATES, "--timestamp", TS]) == 1
    captured = capsys.readouterr()
    assert "E0001" in captured.err
    assert captured.out == ""


def test_explicit_top(capsys):
    assert main([STDGATES, "--top", "NAND", "--timestamp", TS]) == 0
    comp = parse_base(capsys.readouterr().out)
    assert comp.name == "NAND"
    assert comp.gates == {"a1": "AND", "n1": "NOT"}


def test_unknown_top_is_a_diagnostic(capsys):
    assert main([ADD2, "--top", "Nope", "--timestamp", TS]) == 1
    assert "E0001" in capsys.readouterr().err


def test_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "nope.shdl")]) == 1
    assert capsys.readouterr().err != ""


def test_diagnostic_format_on_stderr(tmp_path, capsys):
    bad = tmp_path / "bad.shdl"
    bad.write_text("top component M(A) -> (Y) { connect { Ghost -> Y; } }")
    assert main([str(bad)]) == 1
    err = capsys.readouterr().err
    # file:line:col: error[CODE]: message (shdl.md §14)
    assert "bad.shdl:1:" in err
    assert "error[E0307]" in err


def test_dia3_full_diagnostic_format(tmp_path, capsys):
    # DIA-3: pin the complete five-field diagnostic line exactly —
    # `file:line:col: error[CODE]: message\n` — including the column, both
    # `: ` joins, the `error[…]` bracketing, and the message body. `Ghost` is
    # an unknown signal at column 39 of a single-line source, so the position
    # is fully determined (shdl.md §14.1 diagnostics-reporting contract).
    bad = tmp_path / "bad.shdl"
    bad.write_text("top component M(A) -> (Y) { connect { Ghost -> Y; } }")
    assert main([str(bad)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    # The diagnostic is exactly one line, terminated by a single newline.
    assert captured.err == "bad.shdl:1:39: error[E0307]: unknown signal 'Ghost'\n"
    # Field-by-field, so a regression names the broken field rather than the
    # whole string.
    line = captured.err.rstrip("\n")
    location, _, rest = line.partition(": ")
    assert location == "bad.shdl:1:39"  # file:line:col
    severity, _, message = rest.partition(": ")
    assert severity == "error[E0307]"  # error[CODE]
    assert message == "unknown signal 'Ghost'"  # message body (DIA-7: name present)


def test_source_date_epoch(monkeypatch, capsys):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")
    assert main([ADD2]) == 0
    comp = parse_base(capsys.readouterr().out)
    assert comp.meta["doc"]["flattened_at"] == "2000-01-01T00:00:00Z"


def test_timestamp_flag_beats_source_date_epoch(monkeypatch, capsys):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")
    assert main([ADD2, "--timestamp", TS]) == 0
    comp = parse_base(capsys.readouterr().out)
    assert comp.meta["doc"]["flattened_at"] == TS


def test_unwritable_output(tmp_path, capsys):
    assert main([ADD2, "-o", str(tmp_path / "no" / "dir" / "out.bshdl")]) == 1
    assert "error" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# DIA-9: argparse usage-error contract + the `python -m flattener` entry point
# --------------------------------------------------------------------------- #


def _run_module(args, env=None):
    """Invoke the CLI as `python -m flattener …` (exercises __main__)."""
    return subprocess.run(
        [sys.executable, "-m", "flattener", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_dia9_missing_file_exits_2_with_usage():
    # DIA-9: argparse usage failures exit 2 with a usage line on stderr —
    # distinct from the exit-1 diagnostic path. Also exercises `__main__`.
    r = _run_module([])
    assert r.returncode == 2
    assert r.stderr.startswith("usage:")
    assert "required: file" in r.stderr
    assert r.stdout == ""


def test_dia9_unknown_flag_exits_2_with_usage():
    # DIA-9
    r = _run_module([ADD2, "--bogus"])
    assert r.returncode == 2
    assert r.stderr.startswith("usage:")
    assert "unrecognized arguments" in r.stderr


def test_dia9_entry_point_succeeds_on_valid_input():
    # DIA-9: the same `python -m flattener` entry point produces Base SHDL and
    # exits 0 on a good file (distinguishing exit 0 / 1 / 2).
    r = _run_module([ADD2, "--timestamp", TS])
    assert r.returncode == 0
    assert r.stdout.startswith("component Add2(")
    assert r.stderr == ""


def test_dia9_diagnostic_path_exits_1():
    # DIA-9: a real positioned diagnostic (a missing file) exits 1, not 2.
    r = _run_module([str(FIXTURES / "does_not_exist.shdl")])
    assert r.returncode == 1
    assert r.stderr != ""


# --------------------------------------------------------------------------- #
# ROB-6: garbage SOURCE_DATE_EPOCH → structured CLI diagnostic, not a crash
# --------------------------------------------------------------------------- #


def test_rob6_non_numeric_source_date_epoch_is_a_diagnostic(monkeypatch, capsys):
    # ROB-6: a non-numeric SOURCE_DATE_EPOCH must not escape as a raw
    # ValueError; the CLI reports it and exits 1.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "notanumber")
    assert main([ADD2]) == 1
    err = capsys.readouterr().err
    assert "SOURCE_DATE_EPOCH" in err
    assert "notanumber" in err


def test_rob6_overflow_source_date_epoch_is_a_diagnostic(monkeypatch, capsys):
    # ROB-6: an out-of-range SOURCE_DATE_EPOCH must not escape as a raw
    # OverflowError.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "9" * 30)
    assert main([ADD2]) == 1
    assert "SOURCE_DATE_EPOCH" in capsys.readouterr().err


def test_rob6_source_date_epoch_crashes_via_subprocess():
    # ROB-6 (regression, both shapes): prove no raw traceback escapes the real
    # process for either a non-numeric or an overflowing value.
    for value in ("notanumber", "9" * 30):
        env = {**os.environ, "SOURCE_DATE_EPOCH": value}
        r = _run_module([ADD2], env=env)
        assert r.returncode == 1, (value, r.stderr)
        assert "Traceback" not in r.stderr, (value, r.stderr)
        assert "SOURCE_DATE_EPOCH" in r.stderr


# --------------------------------------------------------------------------- #
# LEX-10 / ROB-6: invalid-UTF-8 source surfaces cleanly through the CLI
# --------------------------------------------------------------------------- #


def test_lex10_invalid_utf8_source_is_a_clean_diagnostic(tmp_path, capsys):
    # LEX-10 + AMB-15: undecodable source bytes → positioned E0101 at the read
    # boundary, exit 1 — never a raw UnicodeDecodeError.
    bad = tmp_path / "bad.shdl"
    bad.write_bytes(b"component M(A) -> (Y) { connect { A -> Y; } }\n\xff\xfe")
    assert main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "bad.shdl:" in err
    assert "error[E0101]" in err
    assert "UTF-8" in err


def test_lex10_invalid_utf8_via_subprocess(tmp_path):
    # LEX-10 (regression): no raw traceback escapes the real process.
    bad = tmp_path / "bad.shdl"
    bad.write_bytes(b"\xff\xfe garbage")
    r = _run_module([str(bad)])
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "error[E0101]" in r.stderr
