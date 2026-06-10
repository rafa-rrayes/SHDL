"""AST for the full SHDL grammar (shdl.md §13).

Every node carries the position of its first token. Arithmetic and boolean
expressions are kept as trees and evaluated by :mod:`shdlc.expr` against an
environment of parameters and generator variables.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .source import Pos

# --------------------------------------------------------------------------- #
# Expressions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Num:
    value: int
    pos: Pos


@dataclass(frozen=True, slots=True)
class Name:
    ident: str
    pos: Pos


@dataclass(frozen=True, slots=True)
class BinOp:
    op: str  # "+", "-", "*", "/"
    left: Expr
    right: Expr
    pos: Pos


type Expr = Num | Name | BinOp


@dataclass(frozen=True, slots=True)
class Cmp:
    left: Expr
    op: str  # "==", "!=", "<", "<=", ">", ">="
    right: Expr
    pos: Pos


@dataclass(frozen=True, slots=True)
class BoolAnd:
    items: tuple[BoolExpr, ...]
    pos: Pos


@dataclass(frozen=True, slots=True)
class BoolOr:
    items: tuple[BoolExpr, ...]
    pos: Pos


type BoolExpr = Cmp | BoolAnd | BoolOr

# --------------------------------------------------------------------------- #
# Names and signals
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class NameTemplate:
    """An identifier possibly interleaved with `{expr}` substitutions.

    ``parts`` alternates literal strings and expressions, starting with a
    (possibly empty is impossible — grammar requires a leading IDENTIFIER)
    literal string: ``cell{i}_{j}`` -> ("cell", <i>, "_", <j>).
    """

    parts: tuple[str | Expr, ...]
    pos: Pos

    @property
    def is_plain(self) -> bool:
        return len(self.parts) == 1 and isinstance(self.parts[0], str)

    @property
    def plain(self) -> str:
        assert isinstance(self.parts[0], str)
        return self.parts[0]


@dataclass(frozen=True, slots=True)
class IndexBit:
    """``[k]`` — a single-bit index."""

    expr: Expr


@dataclass(frozen=True, slots=True)
class IndexSlice:
    """``[a:b]`` / ``[:b]`` (lo omitted -> 1) / ``[a:]`` (hi omitted -> open)."""

    lo: Expr | None
    hi: Expr | None


type Index = IndexBit | IndexSlice


@dataclass(frozen=True, slots=True)
class Primary:
    """A port, instance port, or constant reference, optionally indexed."""

    base: NameTemplate
    port: NameTemplate | None
    index: Index | None
    pos: Pos


@dataclass(frozen=True, slots=True)
class Replication:
    """``N{ ... }`` — N adjacent copies of the braced group (§6.5.1)."""

    count: Expr
    items: tuple[ConcatItem, ...]
    pos: Pos


type ConcatItem = Replication | Primary


@dataclass(frozen=True, slots=True)
class Concat:
    """``{ item, item, ... }`` — MSB-first within the braces (§6.5)."""

    items: tuple[ConcatItem, ...]
    pos: Pos


type Signal = Concat | Primary

# --------------------------------------------------------------------------- #
# Statements and declarations
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Connection:
    src: Signal
    dst: Signal
    pos: Pos


@dataclass(frozen=True, slots=True)
class RangeN:
    """``[N]`` -> 1, 2, ..., N."""

    expr: Expr
    pos: Pos


@dataclass(frozen=True, slots=True)
class RangeAB:
    """``[a:b]`` -> a ... b inclusive."""

    lo: Expr
    hi: Expr
    pos: Pos


@dataclass(frozen=True, slots=True)
class RangeOpen:
    """``[a:]`` -> a ... governing signal's width (§7.1)."""

    lo: Expr
    pos: Pos


@dataclass(frozen=True, slots=True)
class RangeTo:
    """``[:b]`` -> 1 ... b."""

    hi: Expr
    pos: Pos


type RangeItem = RangeN | RangeAB | RangeOpen | RangeTo


@dataclass(frozen=True, slots=True)
class Arg:
    name: str | None  # named argument (`SEL = 2`) or None for positional
    expr: Expr
    pos: Pos


@dataclass(frozen=True, slots=True)
class InstanceDecl:
    name: NameTemplate
    type_name: str
    type_pos: Pos
    args: tuple[Arg, ...]
    pos: Pos


@dataclass(frozen=True, slots=True)
class ConstantDecl:
    name: str
    width: Expr | None
    value: int
    pos: Pos


@dataclass(frozen=True, slots=True)
class Generator:
    var: str
    var_pos: Pos
    ranges: tuple[RangeItem, ...]
    body: tuple[GenItem, ...]
    pos: Pos


@dataclass(frozen=True, slots=True)
class Conditional:
    cond: BoolExpr
    then_body: tuple[GenItem, ...]
    else_body: tuple[GenItem, ...]
    pos: Pos


type GenItem = Connection | InstanceDecl | ConstantDecl | Generator | Conditional


@dataclass(frozen=True, slots=True)
class InitAssign:
    target: Primary
    value: int
    pos: Pos


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    default: int | None
    pos: Pos


@dataclass(frozen=True, slots=True)
class PortDecl:
    name: str
    width: Expr | None  # None -> single-bit
    pos: Pos


@dataclass(slots=True)
class Component:
    name: str
    params: tuple[Param, ...]
    inputs: tuple[PortDecl, ...]
    outputs: tuple[PortDecl, ...]
    decls: tuple[GenItem, ...]  # instance/constant decls, generators, conditionals
    init_blocks: tuple[tuple[Pos, tuple[InitAssign, ...]], ...]
    connect_blocks: tuple[tuple[Pos, tuple[GenItem, ...]], ...]
    is_top: bool
    pos: Pos
    file: str
    module: str = ""  # filled by the loader


@dataclass(frozen=True, slots=True)
class Import:
    module: str
    module_pos: Pos
    names: tuple[tuple[str, Pos], ...]
    pos: Pos


@dataclass(slots=True)
class Module:
    name: str
    file: str
    imports: tuple[Import, ...]
    components: tuple[Component, ...]
    doc_comment: str | None = None
    path: str = ""
    visible: dict[str, tuple[str, str]] = field(default_factory=dict)
