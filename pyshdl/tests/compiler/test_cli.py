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
    body = c[m.start() :]
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


# ---------------------------------------------------------------------------
# CCT-10 holes: --shdl flag, --no-build default .c path, SHDLError surfacing,
# --base/--shdl exclusion at exit 2 exactly, --cc at the CLI level.
# ---------------------------------------------------------------------------


def test_shdl_flag_forces_flattening_of_non_shdl_extension(tmp_path):
    # CCT-10: --shdl makes the CLI flatten regardless of extension. Give the
    # file a .base extension so only the flag selects the SHDL path.
    shutil.copy(FIXTURES / "add2.shdl", tmp_path / "add2.src")
    shutil.copy(FIXTURES / "fullAdder.shdl", tmp_path / "fullAdder.shdl")
    proc = run_shdlc(["--shdl", "add2.src"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / f"add2{lib_suffix()}").exists()


def test_no_build_uses_default_c_path(builds, tmp_path):
    # CCT-10: --no-build with no --emit-c writes "<stem>.c" in the CWD.
    (tmp_path / "add2.base").write_text(builds.fixture_text("add2"))
    proc = run_shdlc(["add2.base", "--no-build"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    default_c = tmp_path / "add2.c"
    assert default_c.exists(), "expected default C at <stem>.c"
    assert "void tick" in default_c.read_text()
    assert not (tmp_path / f"add2{lib_suffix()}").exists()


def test_shdl_flattener_error_surfaces_as_diagnostic(tmp_path):
    # CCT-10: the SHDLError-surfacing branch. A .shdl that fails to flatten
    # (here: imports a sibling that does not exist) -> rc 1, clean diagnostic.
    (tmp_path / "broken.shdl").write_text(
        "use missingmod::{Nope};\n"
        "component Broken(a) -> (y) { n: Nope; connect { a -> n.A; n.O -> y; } }\n"
    )
    proc = run_shdlc(["broken.shdl"], cwd=tmp_path)
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    assert PREFIX in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr


def test_base_and_shdl_are_mutually_exclusive_exit_2(tmp_path):
    # CCT-10: --base and --shdl together is a usage error -> exit 2 exactly.
    (tmp_path / "x.base").write_text("component X(a) -> (y) { connect { a -> y; } }\n")
    proc = run_shdlc(["--base", "--shdl", "x.base"], cwd=tmp_path)
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert proc.stderr.strip(), "argparse must explain the exclusion"
    assert "Traceback" not in proc.stderr


def test_cc_flag_plumbs_through_to_the_compiler(builds, tmp_path):
    # CCT-10 + CCT-3: --cc carries the compiler argv prefix (shlex-split), so
    # warning flags placed there make the CLI build a zero-warning proof under
    # -Werror -- closing the hole that plain CLI builds used DEFAULT_CFLAGS
    # with no warning flags. A real strict build that exits 0 IS the proof.
    (tmp_path / "add2.base").write_text(builds.fixture_text("add2"))
    proc = run_shdlc(["add2.base", "--cc", "cc -Wall -Wextra -Werror -pedantic"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr  # -Werror passed: warning-free
    out = tmp_path / f"add2{lib_suffix()}"
    assert out.exists()
    check_add2_lib(builds, out)


def test_cc_flag_bad_compiler_is_diagnosed(tmp_path):
    # CCT-10: a bogus --cc value surfaces as a clean CCError diagnostic, rc 1.
    (tmp_path / "x.base").write_text("component X(a) -> (y) { connect { a -> y; } }\n")
    proc = run_shdlc(["x.base", "--cc", "no-such-compiler-xyz"], cwd=tmp_path)
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    assert PREFIX in proc.stderr, proc.stderr
    assert "no-such-compiler-xyz" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_chunked_cli_build_is_warning_free_under_strict_cc(tmp_path):
    # CCT-3 + CCT-17 (CLI angle): a >1024-gate circuit goes through the
    # chunked tick() emission; building it via the CLI under -Werror proves
    # the chunk functions compile warning-free on the real CLI path too.
    n = 1100
    decls = [f"    g{i}: {'XOR' if i % 2 else 'NOT'};" for i in range(n)]
    conns = ["        a -> g0.A;"]
    for i in range(1, n):
        conns.append(f"        g{i - 1}.O -> g{i}.A;")
        if i % 2:
            conns.append(f"        b -> g{i}.B;")
    conns.append(f"        g{n - 1}.O -> y;")
    text = (
        "\n".join(
            ["component ChunkCli(a, b) -> (y) {", *decls, "    connect {", *conns, "    }", "}"]
        )
        + "\n"
    )
    (tmp_path / "chunk.base").write_text(text)
    proc = run_shdlc(["chunk.base", "--cc", "cc -Wall -Wextra -Werror -pedantic"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / f"chunk{lib_suffix()}").exists()
