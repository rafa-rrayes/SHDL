"""Compile-time evaluation of arithmetic and boolean expressions.

The environment maps identifiers (component parameters and generator
variables) to integers. After monomorphization (phase 2) no parameter
identifiers remain, so any unbound name found later is a generator-scope
error (E0603). Division is integer division (shdl.md §7.2); division by zero
is E0605.
"""

from __future__ import annotations

from .ast_nodes import BinOp, BoolAnd, BoolExpr, BoolOr, Cmp, Expr, Name, Num
from .diagnostics import ErrorCode, err


def eval_arith(expr: Expr, env: dict[str, int]) -> int:
    match expr:
        case Num(value=v):
            return v
        case Name(ident=ident, pos=pos):
            if ident not in env:
                raise err(
                    ErrorCode.E0603,
                    f"'{ident}' is not a parameter or generator variable in scope",
                    pos,
                )
            return env[ident]
        case BinOp(op=op, left=left, right=right, pos=pos):
            lv = eval_arith(left, env)
            rv = eval_arith(right, env)
            match op:
                case "+":
                    return lv + rv
                case "-":
                    return lv - rv
                case "*":
                    return lv * rv
                case "/":
                    if rv == 0:
                        raise err(ErrorCode.E0605, "division by zero", pos)
                    # Truncating integer division, like C — not Python floor.
                    return abs(lv) // abs(rv) * (1 if (lv >= 0) == (rv >= 0) else -1)
                case _:  # pragma: no cover - parser only produces the four ops
                    raise AssertionError(op)
    raise AssertionError(expr)  # pragma: no cover


def eval_bool(expr: BoolExpr, env: dict[str, int]) -> bool:
    match expr:
        case Cmp(left=left, op=op, right=right):
            lv = eval_arith(left, env)
            rv = eval_arith(right, env)
            match op:
                case "==":
                    return lv == rv
                case "!=":
                    return lv != rv
                case "<":
                    return lv < rv
                case "<=":
                    return lv <= rv
                case ">":
                    return lv > rv
                case ">=":
                    return lv >= rv
        case BoolAnd(items=items):
            return all(eval_bool(item, env) for item in items)
        case BoolOr(items=items):
            return any(eval_bool(item, env) for item in items)
    raise AssertionError(expr)  # pragma: no cover


def expr_names(expr: Expr) -> set[str]:
    """All identifiers referenced by an arithmetic expression."""
    match expr:
        case Num():
            return set()
        case Name(ident=ident):
            return {ident}
        case BinOp(left=left, right=right):
            return expr_names(left) | expr_names(right)
    raise AssertionError(expr)  # pragma: no cover
