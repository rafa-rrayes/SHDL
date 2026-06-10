from helpers import FIXTURES, TS, flatten_fixture

from flattener.baseshdl import parse_base
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
