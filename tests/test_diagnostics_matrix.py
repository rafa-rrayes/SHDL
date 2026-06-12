"""One positioned trigger for every diagnostic code.

Each case is a minimal program that must fail with exactly its code (the
helper also asserts a real line/column). The completeness test pins the
matrix to the ErrorCode enum so a new code cannot land untested.
"""

import pytest
from helpers import expect_error, flatten_source

from flattener.diagnostics import ErrorCode, SHDLError

WIRE = "component W(In) -> (Out) { connect { In -> Out; } }"
PARAM1 = "component P<N = 1>(A) -> (Y) { connect { A -> Y; } }"

CASES: dict[str, dict] = {
    # E00xx — toolchain usage
    "E0001": dict(
        source="component A1(X) -> (Y) { connect { X -> Y; } }\n"
        "component B1(X) -> (Y) { connect { X -> Y; } }",
    ),
    # E01xx — lexical
    "E0101": dict(source="top component M(A) -> (Y) { connect { A -> Y; } }\n$"),
    # E02xx — parse
    "E0201": dict(source="component M(A) -> Y) { connect { A -> Y; } }"),
    # E03xx — names and references
    "E0301": dict(
        source="top component M(A) -> (Y) { n: NOT; n: NOT; "
        "connect { A -> n.A; n.O -> Y; } }",
    ),
    "E0303": dict(
        source="top component M(A) -> (Y) { __g: NOT; "
        "connect { A -> __g.A; __g.O -> Y; } }",
    ),
    "E0304": dict(source="top component M(A_1_) -> (Y) { connect { A_1_ -> Y; } }"),
    "E0305": dict(
        source="component AND(A, B) -> (O) { o1: OR; "
        "connect { A -> o1.A; B -> o1.B; o1.O -> O; } }",
    ),
    "E0306": dict(
        source="top component M(A) -> (Y) { u: Mystery; "
        "connect { A -> u.A; u.O -> Y; } }",
    ),
    "E0307": dict(source="top component M(A) -> (Y) { connect { Ghost -> Y; } }"),
    "E0308": dict(
        source="component FA(A) -> (Y) { x1: NOT; connect { A -> x1.A; x1.O -> Y; } }\n"
        "top component M(A) -> (Y, Z) { fa: FA; fa_x1: NOT; "
        "connect { A -> fa.A; fa.Y -> Y; A -> fa_x1.A; fa_x1.O -> Z; } }",
    ),
    "E0309": dict(source="top component M(A) -> (Y) { n: NOT; }"),
    "E0310": dict(
        source="top component A1(X) -> (Y) { connect { X -> Y; } }\n"
        "top component B1(X) -> (Y) { connect { X -> Y; } }",
    ),
    "E0311": dict(
        source="top component R(A) -> (Y) { r: R; "
        "connect { A -> r.A; r.Y -> Y; } }",
    ),
    # E04xx — widths and indices
    "E0401": dict(source="top component M(A[2]) -> (Y[3]) { connect { A -> Y; } }"),
    "E0402": dict(source="top component M(A[2]) -> (Y) { connect { A[5] -> Y; } }"),
    "E0403": dict(source="top component M(A[0]) -> (Y) { connect { A -> Y; } }"),
    "E0404": dict(
        source="top component M(A[4]) -> (Y[2]) { connect { A[3:2] -> Y; } }",
    ),
    # E05xx — connection rules
    "E0501": dict(
        source="top component M(A, B) -> (Y) { connect { A -> Y; B -> Y; } }",
    ),
    "E0502": dict(
        source="top component M(A) -> (Y) { g: AND; "
        "connect { A -> g.A; g.O -> Y; } }",
    ),
    "E0503": dict(source="top component M(A) -> (Y, Z) { connect { A -> Y; } }"),
    "E0505": dict(source="top component M(A, B) -> (Y) { connect { A -> B; A -> Y; } }"),
    "E0506": dict(
        source=f"{WIRE}\n"
        "top component M(X) -> (Y) { w1: W; w2: W; "
        "connect { w1.Out -> w2.In; w2.Out -> w1.In; w1.Out -> Y; } }",
    ),
    # E06xx — generators and conditionals
    "E0601": dict(
        source="top component M(A) -> (Y) { >i[2:1]{ b{i}: OR; } "
        "connect { A -> Y; } }",
    ),
    "E0602": dict(
        source="top component M(A) -> (Y) { >i[2:]{ b{i}: OR; } "
        "connect { A -> Y; } }",
    ),
    "E0603": dict(source="top component M(A[2]) -> (Y) { connect { A[{j}] -> Y; } }"),
    "E0604": dict(
        source="top component M(A) -> (Y) { >i[2]{ {x} -> Y; } "
        "connect { A -> Y; } }",
    ),
    "E0605": dict(
        source="top component M(A) -> (Y) { >i[4/0]{ b{i}: OR; } "
        "connect { A -> Y; } }",
    ),
    # E07xx — imports
    "E0701": dict(
        source="use missing::{X};\ntop component M(A) -> (Y) { connect { A -> Y; } }",
    ),
    "E0702": dict(
        source="use other::{B1};\ntop component M(A) -> (Y) { b: B1; "
        "connect { A -> b.X; b.Y -> Y; } }",
        aux={"other": "use main::{M};\ncomponent B1(X) -> (Y) { connect { X -> Y; } }"},
    ),
    "E0703": dict(
        source="use lib::{Bar};\ntop component M(A) -> (Y) { connect { A -> Y; } }",
        aux={"lib": "component Foo(A) -> (Y) { connect { A -> Y; } }"},
    ),
    # E08xx — constants
    "E0801": dict(
        source="top component M(A) -> (Y) { K[2] = 9; connect { A -> Y; } }",
    ),
    # E09xx — parameters
    "E0901": dict(
        source=f"{PARAM1}\ntop component M(A) -> (Y) {{ p: P<Q = 3>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    ),
    "E0902": dict(
        source="component P<N>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P; connect { A -> p.A; p.Y -> Y; } }",
    ),
    "E0903": dict(
        source=f"{PARAM1}\ntop component M(A) -> (Y) {{ p: P<N = 1, 2>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    ),
    "E0904": dict(
        source=f"{PARAM1}\ntop component M(A) -> (Y) {{ p: P<1, N = 2>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    ),
    "E0905": dict(
        source=f"{PARAM1}\ntop component M(A) -> (Y) {{ p: P<0 - 3>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    ),
    "E0906": dict(
        source="component P<N = 0>(A[N]) -> (Y[N]) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P; connect { A -> p.A; p.Y -> Y; } }",
    ),
    # E0Axx — initial state
    "E0A01": dict(
        source="top component M(A) -> (Y) { init { A = 1; } connect { A -> Y; } }",
    ),
    "E0A02": dict(
        source="top component M(A) -> (Y) { n: NOT; init { n.O = 1; Y = 0; } "
        "connect { A -> n.A; n.O -> Y; } }",
    ),
    "E0A03": dict(
        source="top component M(A) -> (Y) { n: NOT; init { n.O = 2; } "
        "connect { A -> n.A; n.O -> Y; } }",
    ),
}


@pytest.mark.parametrize("code", sorted(CASES))
def test_trigger(code, tmp_path):
    case = dict(CASES[code])
    source = case.pop("source")
    expect_error(code, tmp_path, source, **case)


def test_self_connection_guard(tmp_path, monkeypatch):
    # E0504 is structurally unreachable through the public pipeline: the role
    # checks partition sources from destinations before bit pairing. Disable
    # them to prove the guard itself works.
    import flattener.phases.expander as expander

    monkeypatch.setattr(expander, "_check_role", lambda *a, **k: None)
    expect_error(
        "E0504",
        tmp_path,
        "top component M(A) -> (Y) { n: NOT; "
        "connect { A -> n.A; n.O -> n.O; n.O -> Y; } }",
    )


def test_matrix_is_complete():
    covered = set(CASES) | {"E0504"}
    assert covered == {c.name for c in ErrorCode}


# --------------------------------------------------------------------------- #
# DIA-7 — message quality: the offending name/value appears in the message.
# --------------------------------------------------------------------------- #
#
# For every code whose error implicates a concrete user-facing name or value
# (an identifier, type, module, port, index, width, or literal), that token
# must appear verbatim in the rendered message so the diagnostic is actionable
# without re-reading the source. The map below names the substring(s) each
# matrix trigger must surface. Codes deliberately *absent* are listed in
# ``_NAME_FREE_CODES`` with the reason — keeping this partition exhaustive is
# the standing enforcement (test_dia7_partition_is_exhaustive), so a new code
# cannot dodge the message-quality check.
_NAME_IN_MESSAGE: dict[str, list[str]] = {
    "E0001": ["main", "A1", "B1"],  # module + the ambiguous component names
    "E0101": ["$"],  # the offending character
    "E0301": ["n", "M"],  # duplicate name + component
    "E0303": ["__g"],  # the reserved-prefix instance name
    "E0304": ["A_1_"],  # the reserved-pattern port name
    "E0305": ["AND"],  # the redefined primitive
    "E0306": ["Mystery"],  # the unknown type
    "E0307": ["Ghost"],  # the unknown signal
    "E0308": ["fa_x1"],  # the colliding flattened gate name
    "E0309": ["M"],  # the offending component
    "E0310": ["main"],  # the module with two tops
    "E0311": ["R"],  # the recursive component
    "E0401": ["2", "3"],  # the mismatched bit widths
    "E0402": ["5", "A", "2"],  # bad index, signal, width
    "E0403": ["A", "0"],  # the port and its non-positive width
    "E0404": ["3", "2", "A"],  # the ill-ordered slice and its signal
    "E0501": ["Y"],  # the multiply-driven net
    "E0502": ["B", "g"],  # the floating input and its instance
    "E0503": ["Z", "M"],  # the undriven output and its component
    "E0505": ["B"],  # the misused input port
    "E0506": ["w1.Out"],  # the net in the gateless cycle
    "E0601": ["2", "1"],  # the ill-ordered range bounds
    "E0603": ["j"],  # the out-of-scope variable
    "E0701": ["missing"],  # the unresolved module
    "E0702": ["main", "other"],  # the import cycle members
    "E0703": ["lib", "Bar"],  # the module + the missing component
    "E0801": ["K", "9", "2"],  # constant, value, width
    "E0901": ["P", "Q"],  # the component + the bad parameter name
    "E0902": ["N", "P"],  # the unbound parameter + its component
    "E0904": ["N", "P"],  # the twice-bound parameter + its component
    "E0905": ["N", "P", "-3"],  # parameter, component, the negative value
    "E0906": ["A", "P", "0"],  # the parameterized port, component, width
    "E0A01": ["A"],  # the bad init target
    "E0A02": ["Y"],  # the doubly-seeded net
    "E0A03": ["2", "n.O"],  # the overflowing value + its target
}

# Codes whose messages are syntactic/positional and implicate no reusable
# user name (the position carries the locality; the text is a category).
_NAME_FREE_CODES: dict[str, str] = {
    "E0201": "parser 'expected X, found <token>' — the token is rendered but "
    "varies by site; position is the locator (DIA-8 covers it).",
    "E0604": "generator/connection context 'expected …, found <token>' — same "
    "as E0201; no reusable name.",
    "E0602": "open-ended-range messages quote the literal template '[a:]' (a "
    "category) rather than the user's range/var — the matrix trigger hits the "
    "declaration-context form; position is the locator (DIA-8).",
    "E0605": "'division by zero' — an arithmetic category, no name/value.",
    "E0903": "'positional argument after named argument' — a structural rule, "
    "no specific name.",
    "E0504": "'a signal may not drive itself' — structural; the backstop is "
    "exercised by test_self_connection_guard, position carries the net.",
}


@pytest.mark.parametrize("code", sorted(_NAME_IN_MESSAGE))
def test_dia7_offending_name_in_message(code, tmp_path):
    # DIA-7: the implicated name(s)/value(s) appear verbatim in the message.
    case = dict(CASES[code])
    source = case.pop("source")
    try:
        flatten_source(tmp_path, source, **case)
    except SHDLError as e:
        msg = e.diagnostic.message
        assert e.diagnostic.code is ErrorCode[code], (code, msg)
        for token in _NAME_IN_MESSAGE[code]:
            assert token in msg, (
                f"{code}: expected {token!r} in message {msg!r}\nsource: {source!r}"
            )
    else:  # pragma: no cover
        raise AssertionError(f"{code}: source did not raise\nsource: {source!r}")


def test_dia7_partition_is_exhaustive():
    # Every matrix code (plus the monkeypatched E0504) is classified as either
    # name-bearing or name-free — extend this partition when a code is added,
    # never bypass it. This keeps DIA-7 from silently skipping a new code.
    classified = set(_NAME_IN_MESSAGE) | set(_NAME_FREE_CODES)
    assert classified == {c.name for c in ErrorCode}
