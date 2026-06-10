"""CLI diagnostics, in-process: clean errors, correct exit codes, no tracebacks.

Contract (shdlc/cli.py docstring): exit 0 on success, 1 on any diagnosed
failure, 2 on usage errors. Diagnostics are Python-level prints, so capsys
suffices here.
"""

from __future__ import annotations

import pytest

from shdlc.cli import main

PREFIX = "shdlc: error:"

# Parses, but g.B is floating (model invariant 5).
STRUCTURALLY_INVALID = """\
component Broken(a) -> (y) {
    g: AND;
    connect { a -> g.A; g.O -> y; }
}
"""


def run_cli(argv):
    """main() may return the code or raise SystemExit (argparse)."""
    try:
        return main(argv)
    except SystemExit as e:
        return 0 if e.code is None else e.code


def assert_clean_diag(err: str):
    assert err.startswith(PREFIX), f"diagnostic must start {PREFIX!r}: {err!r}"
    assert err.count(PREFIX) == 1, f"expected a single diagnostic: {err!r}"
    assert "Traceback" not in err, f"diagnostic must not include a traceback: {err!r}"


def test_syntax_error_in_base_file(tmp_path, capsys):
    bad = tmp_path / "bad.base"
    bad.write_text("component ( -> { this is not base shdl ;;;\n")
    assert run_cli([str(bad)]) == 1
    err = capsys.readouterr().err
    assert_clean_diag(err)


def test_structurally_invalid_base_file(tmp_path, capsys):
    bad = tmp_path / "floating.base"
    bad.write_text(STRUCTURALLY_INVALID)
    assert run_cli([str(bad)]) == 1
    assert_clean_diag(capsys.readouterr().err)


def test_nonexistent_input_path(tmp_path, capsys):
    missing = tmp_path / "no_such_file.base"
    assert run_cli([str(missing)]) == 1
    err = capsys.readouterr().err
    assert_clean_diag(err)
    assert "no_such_file" in err, f"diagnostic should name the path: {err!r}"


def test_unwritable_output_path(builds, tmp_path, capsys):
    src = tmp_path / "add2.base"
    src.write_text(builds.fixture_text("add2"))
    ro_dir = tmp_path / "readonly"
    ro_dir.mkdir()
    ro_dir.chmod(0o500)
    try:
        rc = run_cli([str(src), "-o", str(ro_dir / "out.dylib")])
        err = capsys.readouterr().err
        assert rc == 1
        assert_clean_diag(err)
    finally:
        ro_dir.chmod(0o700)


@pytest.mark.parametrize(
    "argv",
    [
        [],  # missing input
        ["--frobnicate", "x.base"],  # unknown option
        ["a.base", "b.base"],  # too many inputs
    ],
)
def test_usage_errors_exit_2(argv, capsys):
    assert run_cli(argv) == 2
    capsys.readouterr()  # drain argparse usage text
