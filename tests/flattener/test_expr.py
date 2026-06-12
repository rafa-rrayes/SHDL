import pytest

from flattener.ast_nodes import BinOp, BoolAnd, BoolOr, Cmp, Name, Num
from flattener.diagnostics import ErrorCode, SHDLError
from flattener.expr import eval_arith, eval_bool, expr_names
from flattener.source import Pos

P = Pos("t.shdl", 1, 1)


def n(v):
    return Num(v, P)


def name(x):
    return Name(x, P)


def op(o, a, b):
    return BinOp(o, a, b, P)


def test_arithmetic():
    # 2 + 3 * 4 (tree built as the parser would: precedence in structure)
    assert eval_arith(op("+", n(2), op("*", n(3), n(4))), {}) == 14
    assert eval_arith(op("-", n(2), n(5)), {}) == -3
    assert eval_arith(op("*", name("i"), n(3)), {"i": 7}) == 21


def test_integer_division():
    assert eval_arith(op("/", n(7), n(2)), {}) == 3
    assert eval_arith(op("/", n(8), n(2)), {}) == 4
    # Truncation toward zero with a negative intermediate (C-style).
    assert eval_arith(op("/", op("-", n(0), n(7)), n(2)), {}) == -3


def test_division_by_zero():
    with pytest.raises(SHDLError) as ei:
        eval_arith(op("/", n(4), op("-", n(1), n(1))), {})
    assert ei.value.diagnostic.code is ErrorCode.E0605


def test_unbound_identifier():
    with pytest.raises(SHDLError) as ei:
        eval_arith(name("ghost"), {"i": 1})
    assert ei.value.diagnostic.code is ErrorCode.E0603


def test_bool_expressions():
    lt = Cmp(name("i"), "<", n(4), P)
    eq = Cmp(name("i"), "==", n(9), P)
    assert eval_bool(lt, {"i": 3}) is True
    assert eval_bool(lt, {"i": 4}) is False
    assert eval_bool(BoolOr((lt, eq), P), {"i": 9}) is True
    assert eval_bool(BoolAnd((lt, eq), P), {"i": 9}) is False
    for o, expected in [("!=", True), ("<=", True), (">", False), (">=", False)]:
        assert eval_bool(Cmp(n(3), o, n(4), P), {}) is expected


def test_expr_names():
    e = op("+", name("i"), op("*", name("N"), n(2)))
    assert expr_names(e) == {"i", "N"}
