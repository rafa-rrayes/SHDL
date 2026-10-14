"""Toolchain contracts: build_library temp hygiene, find_cc edges, end-to-end.

- CCT-11: the mkstemp'd .c is unlinked on success AND on CCError; with
  ``emit_c`` the C file persists; no stray temp files after a failed build.
- CCT-12: find_cc with a whitespace-only / empty value (explicit arg or $CC
  that shlex-splits to nothing) raises CCError -- no silent fallback.
- CCT-13: a meta-less Base SHDL artifact builds to a working library and
  simulates in parity with the oracle (identity ports synthesized).
- CCT-19: the built library's undefined-symbol set is a subset of libc
  (platform-gated; macOS nm -u).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from shdlc.cc import CCError, find_cc, lib_suffix
from shdlc.compile import build_library

from .harness import STRICT_CFLAGS, load_fresh_copy, make_oracle


def _list_c_temps(directory: Path) -> list[Path]:
    """mkstemp .c files build_library leaves in ``directory`` (prefix stem-)."""
    return [p for p in directory.iterdir() if p.suffix == ".c"]


# ---------------------------------------------------------------------------
# CCT-11: temp-file hygiene.
# ---------------------------------------------------------------------------

GOOD_BASE = """\
component Good(a, b) -> (y) {
    g: AND;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"], "b": ["b"] }, "outputs": { "y": ["y"] } } }
"""


def test_temp_c_unlinked_on_success(tmp_path):
    # CCT-11: a successful build leaves no .c temp next to the artifact.
    out = tmp_path / f"good{lib_suffix()}"
    build_library(GOOD_BASE, out, cflags=STRICT_CFLAGS)
    assert out.exists()
    assert _list_c_temps(tmp_path) == [], "mkstemp .c not cleaned up on success"


def test_temp_c_unlinked_on_ccerror(tmp_path, monkeypatch):
    # CCT-11: a build that fails in the C compiler must still unlink the temp.
    # Force a CCError by pointing the compiler at a bogus flag value.
    from shdlc import cc as cc_mod

    real_run = cc_mod.subprocess.run

    def failing_run(argv, *args, **kwargs):
        # Inject a guaranteed-bad flag so the compiler errors out.
        return real_run([argv[0], "--nonsense-flag-zzz", *argv[1:]], *args, **kwargs)

    monkeypatch.setattr(cc_mod.subprocess, "run", failing_run)
    out = tmp_path / f"bad{lib_suffix()}"
    with pytest.raises(CCError):
        build_library(GOOD_BASE, out, cflags=STRICT_CFLAGS)
    assert _list_c_temps(tmp_path) == [], "mkstemp .c leaked after a failed build"
    assert not out.exists()


def test_emit_c_persists_and_no_stray_temp(tmp_path):
    # CCT-11: with emit_c the named C file persists; the mkstemp path is not
    # used at all, so there is exactly one .c on disk (the requested one).
    out = tmp_path / f"good{lib_suffix()}"
    c_file = tmp_path / "kept.c"
    build_library(GOOD_BASE, out, cflags=STRICT_CFLAGS, emit_c=c_file)
    assert out.exists()
    assert c_file.exists() and "void tick" in c_file.read_text()
    assert _list_c_temps(tmp_path) == [c_file], "unexpected stray temp .c files"


# ---------------------------------------------------------------------------
# CCT-12: find_cc whitespace-only / empty values raise, no fallback.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", "\t", " \n "])
def test_find_cc_whitespace_explicit_arg_raises(value, monkeypatch):
    # CCT-12: even with good $CC and PATH compilers, a blank explicit arg must
    # raise -- it shlex-splits to nothing, so there is no compiler to run.
    import shutil

    monkeypatch.setenv("CC", "cc")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: "/usr/bin/cc")
    with pytest.raises(CCError) as ei:
        find_cc(value)
    assert "empty" in str(ei.value)


@pytest.mark.parametrize("value", ["   ", "\t\t"])
def test_find_cc_whitespace_env_cc_falls_back_to_path(value, monkeypatch):
    # A whitespace-only $CC is treated as unset (.strip() is falsy), so the
    # PATH search proceeds -- this is the documented $CC-empty behavior.
    import shutil

    monkeypatch.setenv("CC", value)
    monkeypatch.setattr(
        shutil, "which", lambda cmd, *a, **k: f"/usr/bin/{cmd}" if cmd == "cc" else None
    )
    assert find_cc() == ["cc"]


def test_find_cc_env_cc_quoted_empty_string_raises(monkeypatch):
    # CCT-12: $CC == '""' is non-blank after .strip() but shlex-splits to a
    # single empty token -- which is not a real compiler. It must raise (the
    # head '' is not on PATH), never silently fall back to cc/clang/gcc.
    import shutil

    monkeypatch.setenv("CC", '""')
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: f"/usr/bin/{cmd}" if cmd else None)
    with pytest.raises(CCError) as ei:
        find_cc()
    assert "$CC" in str(ei.value)


# ---------------------------------------------------------------------------
# CCT-13: meta-less Base SHDL builds and simulates end-to-end.
# ---------------------------------------------------------------------------

META_LESS = """\
component MetaLess(a, b) -> (y) {
    g: AND;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
"""


def test_meta_less_artifact_builds_runs_and_matches_oracle(tmp_path):
    # CCT-13: identity single-bit ports synthesized from the header; the built
    # library simulates bit-for-bit with BaseEval over the same text.
    out = tmp_path / f"metaless{lib_suffix()}"
    build_library(META_LESS, out, cflags=STRICT_CFLAGS)
    inst_dir = tmp_path / "inst"
    inst_dir.mkdir()
    sim = load_fresh_copy(out, inst_dir)
    oracle = make_oracle(META_LESS)  # defaults identity ports for the oracle
    for a in (0, 1):
        for b in (0, 1):
            sim.reset()
            oracle.reset()
            sim.poke("a", a)
            sim.poke("b", b)
            oracle.poke("a", a)
            oracle.poke("b", b)
            sim.step(1)
            oracle.step(1)
            assert sim.peek("y") == oracle.peek("y") == (a & b), (a, b)


# ---------------------------------------------------------------------------
# CCT-19: self-containedness -- undefined symbols are a subset of libc.
# ---------------------------------------------------------------------------

# Symbols a conforming generated library may import: the three libc entry
# points it actually calls, plus the dynamic-loader stub binder. Anything
# else would be an unexpected runtime dependency.
_ALLOWED_UNDEFINED = {
    "_fprintf",
    "_strcmp",
    "_memcmp",
    "_memset",
    "___stderrp",
    "dyld_stub_binder",
}


@pytest.mark.skipif(sys.platform != "darwin", reason="nm -u symbol contract checked on macOS")
def test_built_library_undefined_symbols_subset_of_libc(tmp_path):
    out = tmp_path / f"selfcontained{lib_suffix()}"
    build_library(GOOD_BASE, out, cflags=STRICT_CFLAGS)
    nm = subprocess.run(["nm", "-u", str(out)], capture_output=True, text=True, check=True)
    undefined = {line.strip() for line in nm.stdout.splitlines() if line.strip()}
    unexpected = undefined - _ALLOWED_UNDEFINED
    assert not unexpected, (
        f"library imports non-libc symbols: {sorted(unexpected)}\n"
        f"(allowed: {sorted(_ALLOWED_UNDEFINED)})"
    )
