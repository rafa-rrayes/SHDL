"""End-to-end CLI runs via ``uv run shdlc`` in a subprocess.

Contract (shdlc/cli.py docstring):

    shdlc INPUT [-o LIB] [--emit-c FILE.c] [--no-build] [--cc CC]
          [--base|--shdl] [--top NAME] [-I DIR]...

Exit 0 on success, 1 on diagnosed failure, 2 on usage errors. The default
artifact path is the input stem plus the platform library suffix, in the
working directory (tests run with cwd=tmp_path).
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from shdlc.cc import lib_suffix

from .harness import FIXTURES, REPO, Sim, make_oracle

PREFIX = "shdlc: error:"


def run_shdlc(args, cwd):
    return subprocess.run(
        ["uv", "run", "--project", str(REPO), "shdlc", *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )


def check_add2_lib(builds, lib_path):
    """The built artifact must load via ctypes and simulate correctly."""
    sim = Sim(lib_path)  # unique path per test: fresh load
    oracle = make_oracle(builds.fixture_text("add2"))
    for port, v in [("A", 1), ("B", 2), ("Cin", 0)]:
        sim.poke(port, v)
        oracle.poke(port, v)
    sim.step(6)
    oracle.step(6)
    assert sim.peek("Sum") == oracle.peek("Sum") == 3
    assert sim.peek("Cout") == oracle.peek("Cout") == 0


def test_base_input_builds_to_default_path(builds, tmp_path):
    (tmp_path / "add2.base").write_text(builds.fixture_text("add2"))
    proc = run_shdlc(["add2.base"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / f"add2{lib_suffix()}"
    assert out.exists(), f"expected default artifact at {out}"
    check_add2_lib(builds, out)


def test_shdl_input_flattens_in_process(builds, tmp_path):
    # add2.shdl imports fullAdder: provide both as siblings.
    shutil.copy(FIXTURES / "add2.shdl", tmp_path / "add2.shdl")
    shutil.copy(FIXTURES / "fullAdder.shdl", tmp_path / "fullAdder.shdl")
    proc = run_shdlc(["add2.shdl"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / f"add2{lib_suffix()}"
    assert out.exists(), f"expected default artifact at {out}"
    check_add2_lib(builds, out)


def test_emit_c_writes_hot_path_clean_c(builds, tmp_path):
    (tmp_path / "add2.base").write_text(builds.fixture_text("add2"))
    proc = run_shdlc(["add2.base", "--emit-c", "add2.c"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    c = (tmp_path / "add2.c").read_text()
    assert c.strip(), "emitted C must be non-empty"
    # Hot-path rules (shdlc_goals.md §5.3): no allocation anywhere, no
    # string operations inside the evaluation function.
    assert "malloc" not in c
    m = re.search(r"void\s+tick\s*\(", c)
    assert m, "generated C must define the evaluation function 'void tick(...)'"
    body = c[m.start():]
    end = body.find("\n}")
    assert end != -1, "could not delimit tick() body"
    body = body[: end + 2]
    assert "strcmp" not in body, "no string ops inside tick()"


def test_no_build_emits_c_without_artifact(builds, tmp_path):
    (tmp_path / "add2.base").write_text(builds.fixture_text("add2"))
    proc = run_shdlc(["add2.base", "--emit-c", "only.c", "--no-build"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "only.c").exists()
    assert not (tmp_path / f"add2{lib_suffix()}").exists()


def test_output_option_custom_path(builds, tmp_path):
    (tmp_path / "add2.base").write_text(builds.fixture_text("add2"))
    custom = tmp_path / "out" / f"custom{lib_suffix()}"
    custom.parent.mkdir()
    proc = run_shdlc(["add2.base", "-o", custom], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert custom.exists()
    check_add2_lib(builds, custom)


def test_base_flag_forces_base_parsing_of_shdl_file(tmp_path):
    # Expanded SHDL is not valid Base SHDL: with --base this must fail
    # cleanly (rc 1, single diagnostic, no traceback).
    shutil.copy(FIXTURES / "add2.shdl", tmp_path / "add2.shdl")
    proc = run_shdlc(["--base", "add2.shdl"], cwd=tmp_path)
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    assert PREFIX in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr


@pytest.mark.parametrize("extra", [["--top", "Add2"], ["-I", "."]])
def test_top_and_include_rejected_for_base_inputs(builds, tmp_path, extra):
    # --top/-I only make sense for .shdl inputs (flattener options).
    (tmp_path / "add2.base").write_text(builds.fixture_text("add2"))
    proc = run_shdlc(["add2.base", *extra], cwd=tmp_path)
    assert proc.returncode in (1, 2), (proc.returncode, proc.stderr)
    assert proc.stderr.strip(), "rejection must be diagnosed on stderr"
    assert "Traceback" not in proc.stderr, proc.stderr


def test_unknown_input_path_is_diagnosed(tmp_path):
    proc = run_shdlc(["does_not_exist.base"], cwd=tmp_path)
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    assert PREFIX in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr
