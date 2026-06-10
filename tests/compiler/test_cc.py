"""Tests for the C-compiler driver (shdlc.cc).

Self-contained: uses only built-in pytest fixtures (monkeypatch, tmp_path),
no conftest dependencies.
"""

from __future__ import annotations

import ctypes
import re
import shutil
import sys
from pathlib import Path

import pytest

from shdlc import cc as cc_mod
from shdlc.cc import DEFAULT_CFLAGS, CCError, build_shared, find_cc, lib_suffix

# ---------------------------------------------------------------------------
# find_cc: discovery order
# ---------------------------------------------------------------------------


def _which_accepting(*names: str):
    """A shutil.which stand-in that resolves only the given names."""

    def fake_which(cmd: str, *args, **kwargs):
        if cmd in names:
            return f"/fake/bin/{cmd}"
        return None

    return fake_which


def test_explicit_arg_beats_env_and_path(monkeypatch):
    monkeypatch.setenv("CC", "envcc")
    monkeypatch.setattr(shutil, "which", _which_accepting("mycc", "envcc", "cc"))
    assert find_cc("mycc") == ["mycc"]


def test_env_beats_path_search(monkeypatch):
    monkeypatch.setenv("CC", "envclang")
    monkeypatch.setattr(shutil, "which", _which_accepting("envclang", "cc", "clang"))
    assert find_cc() == ["envclang"]


def test_path_search_prefers_cc(monkeypatch):
    monkeypatch.delenv("CC", raising=False)
    monkeypatch.setattr(shutil, "which", _which_accepting("cc", "clang", "gcc"))
    assert find_cc() == ["cc"]


def test_path_search_falls_through_in_order(monkeypatch):
    monkeypatch.delenv("CC", raising=False)
    monkeypatch.setattr(shutil, "which", _which_accepting("clang", "gcc"))
    assert find_cc() == ["clang"]
    monkeypatch.setattr(shutil, "which", _which_accepting("gcc"))
    assert find_cc() == ["gcc"]


def test_empty_env_cc_treated_as_unset(monkeypatch):
    monkeypatch.setenv("CC", "")
    monkeypatch.setattr(shutil, "which", _which_accepting("cc"))
    assert find_cc() == ["cc"]


def test_env_wrapper_is_shlex_split(monkeypatch):
    monkeypatch.setenv("CC", "ccache clang")
    monkeypatch.setattr(shutil, "which", _which_accepting("ccache", "clang"))
    assert find_cc() == ["ccache", "clang"]


def test_explicit_wrapper_is_shlex_split(monkeypatch):
    monkeypatch.setattr(shutil, "which", _which_accepting("ccache", "clang"))
    assert find_cc("ccache clang") == ["ccache", "clang"]


def test_nothing_found_raises_ccerror(monkeypatch):
    monkeypatch.delenv("CC", raising=False)
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(CCError) as excinfo:
        find_cc()
    msg = str(excinfo.value)
    # The message names everything that was tried.
    assert "'cc'" in msg and "'clang'" in msg and "'gcc'" in msg
    assert "$CC" in msg


def test_explicit_unresolvable_raises_no_fallback(monkeypatch):
    # Even with a perfectly good $CC and PATH compilers available, a bogus
    # explicit argument must raise — never silently fall back.
    monkeypatch.setenv("CC", "cc")
    monkeypatch.setattr(shutil, "which", _which_accepting("cc"))
    with pytest.raises(CCError) as excinfo:
        find_cc("no-such-compiler")
    assert "no-such-compiler" in str(excinfo.value)


def test_env_unresolvable_raises_no_fallback(monkeypatch):
    monkeypatch.setenv("CC", "no-such-compiler")
    monkeypatch.setattr(shutil, "which", _which_accepting("cc"))
    with pytest.raises(CCError) as excinfo:
        find_cc()
    msg = str(excinfo.value)
    assert "no-such-compiler" in msg and "$CC" in msg


def test_explicit_absolute_path_that_exists_is_accepted(monkeypatch, tmp_path):
    # An absolute path that exists is accepted even if which() rejects it.
    fake = tmp_path / "weird-cc"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    assert find_cc(str(fake)) == [str(fake)]


# ---------------------------------------------------------------------------
# lib_suffix
# ---------------------------------------------------------------------------


def test_lib_suffix_current_platform():
    expected = {
        "darwin": ".dylib",
        "win32": ".dll",
        "cygwin": ".dll",
    }.get(sys.platform, ".so")
    assert lib_suffix() == expected


@pytest.mark.parametrize(
    ("platform", "suffix"),
    [
        ("darwin", ".dylib"),
        ("win32", ".dll"),
        ("cygwin", ".dll"),
        ("linux", ".so"),
        ("freebsd14", ".so"),
    ],
)
def test_lib_suffix_reads_platform_at_call_time(monkeypatch, platform, suffix):
    monkeypatch.setattr(sys, "platform", platform)
    assert lib_suffix() == suffix


# ---------------------------------------------------------------------------
# build_shared: error surfacing
# ---------------------------------------------------------------------------


def test_build_shared_surfaces_compiler_errors(tmp_path):
    src = tmp_path / "broken.c"
    src.write_text("int broken( { this is not C\n")
    out = tmp_path / f"broken{lib_suffix()}"

    with pytest.raises(CCError) as excinfo:
        build_shared(src, out)
    exc = excinfo.value

    # .argv is the exact command line attempted.
    expected_argv = find_cc() + list(DEFAULT_CFLAGS) + ["-o", str(out), str(src)]
    assert exc.argv == expected_argv

    # .stderr carries the compiler's actual diagnostics verbatim.
    assert "error" in exc.stderr.lower()

    # str() mentions the (nonzero) exit code and includes stderr for pytest.
    msg = str(exc)
    assert re.search(r"exit code [1-9]\d*", msg)
    assert exc.stderr in msg


# ---------------------------------------------------------------------------
# build_shared: success path
# ---------------------------------------------------------------------------

SMOKE_C = """
__attribute__((visibility("default")))
int shdlc_cc_smoke(void) { return 42; }
"""

PLAIN_C = "int shdlc_cc_plain(void) { return 7; }\n"


def test_build_shared_default_cflags_and_load(tmp_path):
    src = tmp_path / "smoke.c"
    src.write_text(SMOKE_C)
    out = tmp_path / f"smoke{lib_suffix()}"

    result = build_shared(src, out)
    assert result == Path(out)
    assert result.exists()

    lib = ctypes.CDLL(str(result))
    lib.shdlc_cc_smoke.restype = ctypes.c_int
    assert lib.shdlc_cc_smoke() == 42


def test_build_shared_cflags_replace_defaults(tmp_path, monkeypatch):
    """Explicit cflags replace DEFAULT_CFLAGS rather than appending to them."""
    src = tmp_path / "plain.c"
    src.write_text(PLAIN_C)
    override = ["-std=c11", "-O0", "-shared", "-fPIC"]  # no -fvisibility=hidden

    # Record the exact argv handed to subprocess.run while still compiling.
    recorded: list[list[str]] = []
    real_run = cc_mod.subprocess.run

    def spying_run(argv, *args, **kwargs):
        recorded.append(list(argv))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(cc_mod.subprocess, "run", spying_run)

    out = tmp_path / f"plain{lib_suffix()}"
    result = build_shared(src, out, cflags=override)

    assert recorded == [find_cc() + override + ["-o", str(out), str(src)]]
    assert "-fvisibility=hidden" not in recorded[0]
    assert "-O2" not in recorded[0]

    # Behavioral proof: without -fvisibility=hidden the unattributed symbol
    # is exported and callable.
    lib = ctypes.CDLL(str(result))
    lib.shdlc_cc_plain.restype = ctypes.c_int
    assert lib.shdlc_cc_plain() == 7


def test_build_shared_default_cflags_hide_unattributed_symbols(tmp_path):
    """Counterpart: under DEFAULT_CFLAGS the same unattributed symbol is hidden,
    proving the override above genuinely changed the flag set."""
    src = tmp_path / "plain.c"
    src.write_text(PLAIN_C)
    out = tmp_path / f"plain_hidden{lib_suffix()}"

    result = build_shared(src, out)
    lib = ctypes.CDLL(str(result))
    with pytest.raises(AttributeError):
        lib.shdlc_cc_plain  # noqa: B018 — attribute access triggers dlsym
