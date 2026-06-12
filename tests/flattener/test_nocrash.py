"""FUZ-4 / ROB-4: no-crash fuzzing of the SHDL frontend (the flattener).

Crash closure (golden_tests.md §0 condition 4, Domain T): no user input,
however malformed, may produce an *uncaught* Python exception. The flatten
pipeline either succeeds or raises the one structured diagnostic type
:class:`flattener.diagnostics.SHDLError`. Anything else — ``ValueError``,
``RecursionError``, ``UnicodeDecodeError``, ``KeyError``, ``AssertionError``,
``OverflowError``, a bare ``Exception`` — is a crash-closure breach and fails
the test with the offending input embedded verbatim (``repr`` for binary).

This is the enforcement mechanism named by ROB-4: it drives the 22 bare
``assert``s, the raw builtin-exception raise sites, and the 25
``raise AssertionError`` invariant guards (ROB-5) from the input side, plus
the implicit decode/env crash paths (ROB-6).

Corpus families (all seed-stable, derived from the test name via zlib.crc32):
  (a) mutations of valid .shdl fixtures: byte flips, truncations at every
      region, token deletion / duplication / swap;
  (b) structured garbage: random token soup from the SHDL alphabet,
      unbalanced brackets, deep-ish nesting under the parser cap, random
      unicode (incl. the `²` superscript class that once crashed int()),
      invalid UTF-8 byte sequences.

Scale knob: ``SHDLC_NOCRASH`` (default ~200 inputs, < 60s). A big campaign
(``SHDLC_NOCRASH=2000``) was run before this landed; any crash found is
minimized into a deterministic regression test below.
"""

from __future__ import annotations

import os
import random
import zlib
from pathlib import Path

import pytest

from flattener.diagnostics import SHDLError
from flattener.lexer import lex
from flattener.parser import parse_source
from flattener.pipeline import flatten_program
from flattener.source import SourceFile

REPO = Path(__file__).resolve().parents[2]  # tests/flattener/ -> tests/ -> repo root
FIXTURES = REPO / "tests" / "fixtures"
TS = "2026-01-01T00:00:00Z"

#: Total inputs across all corpus families for the property test.
NOCRASH_COUNT = int(os.environ.get("SHDLC_NOCRASH", "200"))

#: The SHDL surface alphabet: keywords, operators, punctuation, literals,
#: identifiers — the raw material for "structured garbage" token soup.
_TOKEN_SOUP = [
    "component", "top", "connect", "when", "else", "init", "use", "meta",
    "->", "==", "!=", "<=", ">=", "&&", "||", "<", ">", "=",
    "(", ")", "{", "}", "[", "]", ",", ";", ":", ".", "+", "-", "*", "/",
    "0", "1", "255", "0xFF", "0b101", "10", "A", "B", "Y", "g", "i", "N",
    "AND", "OR", "NOT", "XOR", "__VCC__", "__GND__",
    " ", "\n", "\t", "#c\n", '"s"', "²", "é", "٣",
]

#: Unicode oddities that have bitten the lexer/loader before (AMB-14/15).
_UNICODE_GREMLINS = ["²", "é", "٣", "﻿", "λ", "→", "​", "🦀", "Ω"]


def _seed_for(label: str) -> int:
    """Seed derived from a stable label (golden_tests.md §1.3)."""
    return zlib.crc32(label.encode("utf-8"))


def _fixture_sources() -> list[tuple[str, str]]:
    """(name, text) for every valid .shdl fixture — the mutation seed corpus."""
    out = []
    for p in sorted(FIXTURES.glob("*.shdl")):
        out.append((p.stem, p.read_text(encoding="utf-8")))
    return out


_FIXTURES = _fixture_sources()


# --------------------------------------------------------------------------- #
# Corpus generators (each yields `bytes`, the most general input shape).
# --------------------------------------------------------------------------- #


def _mutate_bytes(rng: random.Random, src: bytes) -> bytes:
    """One mutation of a valid source: byte flip, truncation, or token op."""
    kind = rng.randrange(5)
    if kind == 0:  # byte flip
        if not src:
            return src
        i = rng.randrange(len(src))
        b = bytearray(src)
        b[i] ^= 1 << rng.randrange(8)
        return bytes(b)
    if kind == 1:  # truncation at an arbitrary region boundary
        if not src:
            return src
        return src[: rng.randrange(len(src) + 1)]
    if kind == 2:  # insert a random byte (incl. high bytes -> invalid UTF-8)
        i = rng.randrange(len(src) + 1)
        return src[:i] + bytes([rng.randrange(256)]) + src[i:]
    # token-level ops on the decoded text
    text = src.decode("utf-8", errors="replace")
    toks = text.split()
    if not toks:
        return src
    op = rng.randrange(3)
    if op == 0:  # delete a token
        del toks[rng.randrange(len(toks))]
    elif op == 1:  # duplicate a token
        i = rng.randrange(len(toks))
        toks.insert(i, toks[i])
    else:  # swap two tokens
        i, j = rng.randrange(len(toks)), rng.randrange(len(toks))
        toks[i], toks[j] = toks[j], toks[i]
    return " ".join(toks).encode("utf-8")


def _garbage_bytes(rng: random.Random) -> bytes:
    """Structured garbage from the SHDL alphabet, sometimes binary-poisoned."""
    kind = rng.randrange(6)
    if kind == 0:  # token soup
        n = rng.randint(0, 60)
        return "".join(rng.choice(_TOKEN_SOUP) for _ in range(n)).encode("utf-8")
    if kind == 1:  # unbalanced brackets
        opens = "".join(rng.choice("({[") for _ in range(rng.randint(0, 40)))
        closes = "".join(rng.choice(")}]") for _ in range(rng.randint(0, 40)))
        body = rng.choice(["component M(A)->(Y){connect{", "->", "", "A"])
        return (opens + body + closes).encode("utf-8")
    if kind == 2:  # deep-ish nesting (well under MAX_NESTING_DEPTH=200)
        depth = rng.randint(1, 60)
        expr = "{" * depth + "1" + "}" * depth
        src = f"top component M(A[2]) -> (Y) {{ connect {{ A[{expr}] -> Y; }} }}"
        return src.encode("utf-8")
    if kind == 3:  # a valid-ish shell with unicode gremlins sprinkled in
        g = "".join(rng.choice(_UNICODE_GREMLINS) for _ in range(rng.randint(1, 5)))
        src = f"component M{g}(A) -> (Y) {{ connect {{ A {g}-> Y; }} }}"
        return src.encode("utf-8")
    if kind == 4:  # invalid UTF-8 byte sequences
        choices = [
            b"\xff\xfe",
            b"\xc3\x28",  # invalid continuation
            b"\xe2\x82",  # truncated 3-byte
            b"\x80\x80",  # lone continuations
            b"component M(A)->(Y){connect{A->Y;}}\n\xff",
        ]
        return rng.choice(choices)
    # numeric/literal edge soup
    parts = ["0x", "0b", "0xG", "0b2", "99" * rng.randint(1, 5), "0x" + "F" * 30,
             "1_000", "12ab", "²", ""]
    return (" ".join(rng.sample(parts, k=rng.randint(1, len(parts))))).encode("utf-8")


def _corpus(count: int) -> list[tuple[str, bytes]]:
    """A deterministic list of (label, raw bytes) inputs of size ``count``."""
    rng = random.Random(_seed_for("nocrash-corpus"))
    items: list[tuple[str, bytes]] = []
    half = count // 2
    for i in range(half):  # mutation family
        name, text = _FIXTURES[i % len(_FIXTURES)]
        raw = _mutate_bytes(rng, text.encode("utf-8"))
        items.append((f"mut-{name}-{i}", raw))
    for i in range(count - half):  # garbage family
        items.append((f"garbage-{i}", _garbage_bytes(rng)))
    return items


# --------------------------------------------------------------------------- #
# The contract: flatten() either succeeds or raises exactly SHDLError.
# --------------------------------------------------------------------------- #


def _assert_flatten_no_crash(label: str, raw: bytes, tmp_path: Path) -> None:
    """Feed ``raw`` (as a file) to the full pipeline; only SHDLError or success."""
    path = tmp_path / "in.shdl"
    path.write_bytes(raw)
    try:
        flatten_program(str(path), timestamp=TS)
    except SHDLError:
        return  # the one sanctioned outcome for bad input
    except BaseException as e:  # noqa: BLE001 — crash closure is total
        raise AssertionError(
            f"FUZ-4 crash closure breach [{label}]: flatten raised "
            f"{type(e).__module__}.{type(e).__name__} instead of SHDLError "
            f"(or success).\n--- offending input (repr) ---\n{raw!r}"
        ) from e


@pytest.mark.parametrize(
    "label,raw",
    _corpus(NOCRASH_COUNT),
    ids=[lbl for lbl, _ in _corpus(NOCRASH_COUNT)],
)
def test_fuz4_flatten_never_crashes(label, raw, tmp_path):
    # FUZ-4 / ROB-4: the whole pipeline (load -> lex -> parse -> validate ->
    # monomorphize -> expand -> flatten -> emit) is crash-closed over malformed
    # input. Any non-SHDLError escape names the input verbatim.
    _assert_flatten_no_crash(label, raw, tmp_path)


def test_fuz4_lex_and_parse_layers_never_crash(tmp_path):
    # FUZ-4: also exercise the lexer and parser directly with decodable text
    # (the in-memory layers, bypassing the loader's UTF-8 gate), so token-level
    # and grammar-level guards are hit even on inputs the loader would reject.
    rng = random.Random(_seed_for("nocrash-layers"))
    for i in range(NOCRASH_COUNT):
        if i % 3 == 0 and _FIXTURES:
            name, text = _FIXTURES[i % len(_FIXTURES)]
            raw = _mutate_bytes(rng, text.encode("utf-8"))
        else:
            raw = _garbage_bytes(rng)
        # decode lossily: lexer/parser take str, the loader owns the byte gate
        text = raw.decode("utf-8", errors="replace")
        src = SourceFile("t.shdl", "/t.shdl", text)
        for layer in ("lex", "parse"):
            try:
                if layer == "lex":
                    lex(src)
                else:
                    parse_source(src, "t")
            except SHDLError:
                pass
            except BaseException as e:  # noqa: BLE001
                raise AssertionError(
                    f"FUZ-4 {layer} crash [{i}]: {type(e).__name__}\n"
                    f"--- input (repr) ---\n{text!r}"
                ) from e


# --------------------------------------------------------------------------- #
# Regression pins: every reproduced raw-exception path, minimized.
# (These mirror the focused tests in test_robustness.py; kept here so the
# no-crash file is self-contained and a crash found by the campaign lands as
# a named, deterministic case rather than a flaky parametrization.)
# --------------------------------------------------------------------------- #


def test_fuz4_superscript_two_is_e0101_not_valueerror():
    # ROB-5/LEX-9: `²`.isdigit() is True, so it once reached int() with a raw
    # ValueError. Pinned: it is an unexpected-character diagnostic.
    with pytest.raises(SHDLError):
        lex(SourceFile("t.shdl", "/t.shdl", "component M(A²) -> (Y) {}"))


def test_fuz4_invalid_utf8_is_diagnostic_not_unicodeerror(tmp_path):
    # ROB-6/LEX-10: undecodable bytes once escaped loader._read_source as a raw
    # UnicodeDecodeError; pinned as a positioned SHDLError.
    bad = tmp_path / "bad.shdl"
    bad.write_bytes(b"component M(A) -> (Y) { connect { A -> Y; } }\n\xff\xfe")
    with pytest.raises(SHDLError):
        flatten_program(str(bad), timestamp=TS)


def test_fuz4_deep_nesting_is_diagnostic_not_recursionerror(tmp_path):
    # ROB/PAR-8: 1000-deep braces once raised RecursionError; pinned as a capped
    # SHDLError through the full pipeline (not just parse_source).
    depth = 1000
    expr = "{" * depth + "1" + "}" * depth
    src = f"top component M(A[2]) -> (Y) {{ connect {{ A[{expr}] -> Y; }} }}"
    bad = tmp_path / "deep.shdl"
    bad.write_text(src)
    with pytest.raises(SHDLError):
        flatten_program(str(bad), timestamp=TS)
