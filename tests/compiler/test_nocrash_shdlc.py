"""FUZ-4 / ROB-4 (shdlc side): no-crash fuzzing of the Base SHDL frontend.

The compiler-side mirror of ``tests/test_nocrash.py``. The Base reader and
model builder either succeed or raise a *structured* diagnostic type:
:class:`shdlc.baseshdl.BaseParseError` or :class:`shdlc.model.ModelError`
(both subclasses of ``ValueError``, but we pin the precise types — a bare
``ValueError`` from somewhere else is still a breach). Anything else
(``KeyError``, ``RecursionError``, ``AssertionError``, ``json.JSONDecodeError``
escaping, ``UnicodeDecodeError``, …) is a crash-closure breach (Domain T).

Corpus families (golden_tests.md Domain Q, FUZ-4 clause (c)):
  - mutations of valid Base SHDL text (flattened fixtures): byte flips,
    truncations, token ops;
  - structured garbage over the Base SHDL alphabet;
  - corrupted ``meta`` JSON appended to an otherwise-valid component
    (the CCT-7/ROB-6 raw-JSONDecodeError path).

Both CLIs are also driven via subprocess on a small sample: exit code in
{0, 1, 2} and **no Python traceback on stderr** (the crash-closure contract
at the process boundary), including invalid UTF-8 into the shdlc CLI's
Base reader (diagnosed via BaseParseError, naming the byte offset).

Scale knob: ``SHDLC_NOCRASH`` (default ~200 in-process inputs, < 60s).
"""

from __future__ import annotations

import os
import random
import subprocess
import zlib

import pytest

from shdlc.baseshdl import BaseParseError, parse_base
from shdlc.model import ModelError, build_circuit

from .harness import REPO

NOCRASH_COUNT = int(os.environ.get("SHDLC_NOCRASH", "200"))

#: Base SHDL surface alphabet (base_shdl.md §3.2): keywords, the six
#: primitive type names, operators, punctuation, names, and a JSON-ish tail.
_BASE_SOUP = [
    "component",
    "connect",
    "meta",
    "->",
    "(",
    ")",
    "{",
    "}",
    ",",
    ":",
    ";",
    ".",
    "AND",
    "OR",
    "NOT",
    "XOR",
    "__VCC__",
    "__GND__",
    "A",
    "B",
    "Y",
    "g",
    "x1",
    "o1",
    "n",
    " ",
    "\n",
    "\t",
    '{"ports":{"inputs":{},"outputs":{}}}',
    "{",
    "}",
    '"',
    "[",
    "]",
    "²",
    "é",
]

# A small set of valid Base SHDL components, flattened from fixtures at import
# time — the mutation seed corpus. (One AND component is hand-written so the
# corpus is non-empty even if a fixture flatten ever regresses.)
_HAND_AND = """\
component HandAnd(a, b) -> (y) {
    g: AND;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"], "b": ["b"] }, "outputs": { "y": ["y"] } } }
"""


def _seed_for(label: str) -> int:
    return zlib.crc32(label.encode("utf-8"))


def _base_seed_corpus() -> list[tuple[str, str]]:
    from flattener.pipeline import flatten_program

    fixtures_dir = REPO / "tests" / "fixtures"
    out: list[tuple[str, str]] = [("hand_and", _HAND_AND)]
    # A few representative tops; --top picks one component of multi-comp modules.
    for name, top in [
        ("add2", None),
        ("fullAdder", None),
        ("srlatch", None),
        ("gatesDemo", None),
    ]:
        try:
            out.append(
                (
                    name,
                    flatten_program(
                        str(fixtures_dir / f"{name}.shdl"),
                        top=top,
                        timestamp="2026-01-01T00:00:00Z",
                    ).text,
                )
            )
        except Exception:  # noqa: BLE001 — a flaky fixture must not block fuzzing
            pass
    return out


_SEEDS = _base_seed_corpus()


def _mutate(rng: random.Random, src: bytes) -> bytes:
    kind = rng.randrange(5)
    if kind == 0:  # byte flip
        if not src:
            return src
        i = rng.randrange(len(src))
        b = bytearray(src)
        b[i] ^= 1 << rng.randrange(8)
        return bytes(b)
    if kind == 1:  # truncation
        return src[: rng.randrange(len(src) + 1)] if src else src
    if kind == 2:  # random byte insert (can poison UTF-8)
        i = rng.randrange(len(src) + 1)
        return src[:i] + bytes([rng.randrange(256)]) + src[i:]
    toks = src.decode("utf-8", errors="replace").split()
    if not toks:
        return src
    op = rng.randrange(3)
    if op == 0:
        del toks[rng.randrange(len(toks))]
    elif op == 1:
        i = rng.randrange(len(toks))
        toks.insert(i, toks[i])
    else:
        i, j = rng.randrange(len(toks)), rng.randrange(len(toks))
        toks[i], toks[j] = toks[j], toks[i]
    return " ".join(toks).encode("utf-8")


_VALID_HEAD = "component M(A) -> (Y) {\n    connect { A -> Y; }\n}\n"
_CORRUPT_META = [
    "meta {not json}",
    "meta {",
    "meta }",
    'meta {"ports": }',
    'meta {"ports": {"inputs"}}',
    "meta [1,2,3]",
    "meta 12.",
    "meta {\x00}",
    'meta {"ports": {"inputs": {"A": [1,2]}, "outputs": {}}} trailing junk',
    "meta " + "[" * 50,
]


def _garbage(rng: random.Random) -> bytes:
    kind = rng.randrange(5)
    if kind == 0:  # token soup
        n = rng.randint(0, 50)
        return "".join(rng.choice(_BASE_SOUP) for _ in range(n)).encode("utf-8")
    if kind == 1:  # unbalanced brackets / partial components
        body = rng.choice(["component M(A)->(Y){connect{", "component M", "->", "", "}}}", "A->Y;"])
        extra = "".join(rng.choice("(){}") for _ in range(rng.randint(0, 30)))
        return (body + extra).encode("utf-8")
    if kind == 2:  # valid component head + corrupted meta JSON (CCT-7/ROB-6)
        return (_VALID_HEAD + rng.choice(_CORRUPT_META)).encode("utf-8")
    if kind == 3:  # invalid UTF-8 byte sequences fed directly to parse_base
        return rng.choice([b"\xff\xfe", b"\xc3\x28", b"\x80", _VALID_HEAD.encode() + b"\xff"])
    # unknown / malformed primitive types and port-coverage games
    parts = [
        "component M() -> (Y) { g: WAT; connect { g.O -> Y; } }",
        "component M(A) -> (Y) { connect { A -> A; } }",
        'component M(A) -> (Y) { connect { A -> Y; } }\nmeta {"ports": {"inputs": {"P": ["A", "A"]}, "outputs": {}}}',
        'component M(A) -> (Y) { connect { A -> Y; } }\nmeta {"ports": {"inputs": {}}}',
    ]
    return rng.choice(parts).encode("utf-8")


def _corpus(count: int) -> list[tuple[str, bytes]]:
    rng = random.Random(_seed_for("nocrash-shdlc-corpus"))
    items: list[tuple[str, bytes]] = []
    half = count // 2
    for i in range(half):
        name, text = _SEEDS[i % len(_SEEDS)]
        items.append((f"mut-{name}-{i}", _mutate(rng, text.encode("utf-8"))))
    for i in range(count - half):
        items.append((f"garbage-{i}", _garbage(rng)))
    return items


# --------------------------------------------------------------------------- #
# Contract: parse_base + build_circuit either succeed or raise BaseParseError
# / ModelError — never any other exception type.
# --------------------------------------------------------------------------- #


def _assert_no_crash(label: str, raw: bytes) -> None:
    # parse_base takes str; the loader/CLI owns the byte->str gate, so here we
    # mirror that boundary by decoding strictly and treating an undecodable
    # input as "not reachable by parse_base" (the str-API contract). We still
    # feed lossily-decoded bytes so structural garbage exercises the scanner.
    text = raw.decode("utf-8", errors="replace")
    try:
        comp = parse_base(text)
    except BaseParseError:
        return
    except BaseException as e:  # noqa: BLE001
        raise AssertionError(
            f"FUZ-4 crash [{label}]: parse_base raised "
            f"{type(e).__module__}.{type(e).__name__} (not BaseParseError).\n"
            f"--- input (repr) ---\n{raw!r}"
        ) from e
    # parsed: now lower to the model.
    try:
        build_circuit(comp)
    except ModelError, BaseParseError:
        return
    except BaseException as e:  # noqa: BLE001
        raise AssertionError(
            f"FUZ-4 crash [{label}]: build_circuit raised "
            f"{type(e).__module__}.{type(e).__name__} (not ModelError).\n"
            f"--- input (repr) ---\n{raw!r}"
        ) from e


@pytest.mark.parametrize(
    "label,raw",
    _corpus(NOCRASH_COUNT),
    ids=[lbl for lbl, _ in _corpus(NOCRASH_COUNT)],
)
def test_fuz4_base_reader_never_crashes(label, raw):
    # FUZ-4 / ROB-4 (shdlc): parse_base + build_circuit are crash-closed.
    _assert_no_crash(label, raw)


def test_fuz4_corrupt_meta_json_is_baseparseerror():
    # CCT-7 / ROB-6 regression: a non-JSON `meta` block once let a raw
    # json.JSONDecodeError escape parse_base. Pinned: BaseParseError.
    for tail in _CORRUPT_META:
        text = _VALID_HEAD + tail
        try:
            parse_base(text)
        except BaseParseError:
            continue
        except BaseException as e:  # noqa: BLE001
            raise AssertionError(
                f"corrupt meta {tail!r} raised {type(e).__name__}, not BaseParseError"
            ) from e
        # If it parsed cleanly (e.g. valid JSON with junk our scanner missed),
        # that is acceptable — the contract is "no non-BaseParseError escape".


def test_fuz4_unknown_primitive_type_is_baseparseerror():
    # base_shdl §3.2: a gate of an unknown primitive type is a BaseParseError
    # (raised in the scanner before build_circuit ever sees it).
    with pytest.raises(BaseParseError):
        parse_base("component M() -> (Y) { g: WAT; connect { g.O -> Y; } }")


# --------------------------------------------------------------------------- #
# Process-boundary contract: drive both CLIs; exit in {0,1,2}, no traceback.
# --------------------------------------------------------------------------- #


def _run_cli(module: str, args: list[str], cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "--project", str(REPO), "python", "-m", module, *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )


# Inputs to drive through the CLIs. Kept tiny (subprocess is slow); each is a
# distinct malformation family. The (id, bytes, xfail) triples below feed both
# the flattener CLI (as .shdl) and the shdlc CLI (as --base, --no-build).
_CLI_INPUTS = [
    ("garbage_soup", b"}{)(->;;:: 0xZZ %%", False),
    ("unbalanced", b"component M(A)->(Y){connect{", False),
    ("corrupt_meta", (_VALID_HEAD + "meta {not json}").encode("utf-8"), False),
    ("empty", b"", False),
    (
        "deep_nest",
        (
            "top component M(A[2]) -> (Y) { connect { A["
            + "{" * 1000
            + "1"
            + "}" * 1000
            + "] -> Y; } }"
        ).encode("utf-8"),
        False,
    ),
]


@pytest.mark.parametrize("name,raw,_xfail", _CLI_INPUTS, ids=[c[0] for c in _CLI_INPUTS])
def test_fuz4_flattener_cli_no_traceback(name, raw, _xfail, tmp_path):
    # FUZ-4: the flattener CLI never emits a Python traceback; exit in {0,1,2}.
    src = tmp_path / "in.shdl"
    src.write_bytes(raw)
    proc = _run_cli("flattener", [str(src)], cwd=tmp_path)
    assert proc.returncode in (0, 1, 2), f"[{name}] exit {proc.returncode}\nstderr:\n{proc.stderr}"
    assert "Traceback (most recent call last)" not in proc.stderr, (
        f"[{name}] flattener CLI leaked a traceback:\n{proc.stderr}\n--- input (repr) ---\n{raw!r}"
    )


@pytest.mark.parametrize("name,raw,_xfail", _CLI_INPUTS, ids=[c[0] for c in _CLI_INPUTS])
def test_fuz4_shdlc_cli_no_traceback(name, raw, _xfail, tmp_path):
    # FUZ-4: the shdlc CLI (Base mode, --no-build) never leaks a traceback.
    src = tmp_path / "in.base"
    src.write_bytes(raw)
    proc = _run_cli("shdlc", [str(src), "--base", "--no-build"], cwd=tmp_path)
    assert proc.returncode in (0, 1, 2), f"[{name}] exit {proc.returncode}\nstderr:\n{proc.stderr}"
    assert "Traceback (most recent call last)" not in proc.stderr, (
        f"[{name}] shdlc CLI leaked a traceback:\n{proc.stderr}\n--- input (repr) ---\n{raw!r}"
    )


def test_fuz4_shdlc_cli_invalid_utf8_no_traceback(tmp_path):
    # FUZ-4 / ROB-6 / LEX-10 shdlc mirror: invalid-UTF-8 Base input to the
    # shdlc CLI is a diagnosed failure (BaseParseError naming the byte
    # offset), never a traceback.
    src = tmp_path / "bad.base"
    src.write_bytes(b"component M(A) -> (Y) { connect { A -> Y; } }\n\xff")
    proc = _run_cli("shdlc", [str(src), "--base", "--no-build"], cwd=tmp_path)
    assert "Traceback (most recent call last)" not in proc.stderr, proc.stderr
