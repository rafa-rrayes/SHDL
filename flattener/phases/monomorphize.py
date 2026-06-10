"""Phase 2 — monomorphization (shdl.md §12, §4.4, §5.3).

Binds parameters and specializes each parameterized component per distinct
argument tuple, substituting parameter identifiers with literals throughout
the cloned definition. After this phase no parameter identifiers remain.

Because instance arguments may depend on enclosing generator variables
(``stage{i}: Pipe<WIDTH = W, ID = i>``), specializations cannot be enumerated
from the raw text alone: a lightweight *discovery walk* evaluates generator
ranges and `when` conditions (concrete after substitution) over declaration
items only — instances are declarations, so the connect block never creates
specializations — and records every concrete argument tuple. Phase 3 later
re-evaluates the same expressions when fully unrolling and binds each
instance to its (already created) specialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..ast_nodes import (
    Arg,
    BinOp,
    BoolAnd,
    BoolExpr,
    BoolOr,
    Cmp,
    Component,
    Concat,
    Conditional,
    Connection,
    ConstantDecl,
    Expr,
    GenItem,
    Generator,
    IndexBit,
    IndexSlice,
    InitAssign,
    InstanceDecl,
    Name,
    NameTemplate,
    Num,
    Primary,
    RangeAB,
    RangeItem,
    RangeN,
    RangeOpen,
    RangeTo,
    Replication,
    Signal,
)
from ..diagnostics import ErrorCode, err
from ..expr import eval_arith
from ..loader import PRIMITIVES, Program
from ..source import Pos
from .expand import walk_items

# --------------------------------------------------------------------------- #
# Result model
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class SpecComponent:
    """A parameter-free specialization of a component definition."""

    key: str
    module: str
    name: str  # original component name (e.g. "Adder", not "Adder<N=8>")
    comp: Component  # cloned AST with parameters substituted
    bindings: dict[str, int]  # parameter values, in declaration order
    inputs: list[tuple[str, int]] = field(default_factory=list)  # (name, width)
    outputs: list[tuple[str, int]] = field(default_factory=list)

    def port_width(self, name: str) -> int | None:
        for n, w in [*self.inputs, *self.outputs]:
            if n == name:
                return w
        return None

    def port_dir(self, name: str) -> str | None:
        for n, _ in self.inputs:
            if n == name:
                return "in"
        for n, _ in self.outputs:
            if n == name:
                return "out"
        return None


class MonoProgram:
    def __init__(self, program: Program, top_key: str):
        self.program = program
        self.top_key = top_key
        self.specs: dict[str, SpecComponent] = {}
        # (defining_module, component_name, bindings_tuple) -> spec key
        self.inst_map: dict[tuple[str, str, tuple[tuple[str, int], ...]], str] = {}

    def spec_for_instance(
        self, enclosing_module: str, decl: InstanceDecl, env: dict[str, int]
    ) -> tuple[str, dict[str, int]]:
        """Resolve an instance declaration to its specialization key.

        Used by phase 3; the specialization must already exist (created by
        the discovery walk).
        """
        resolved = self.program.resolve_type(enclosing_module, decl.type_name)
        assert resolved is not None, decl.type_name
        def_module, comp_name = resolved
        comp = self.program.component(def_module, comp_name)
        bindings = bind_args(comp, decl, env)
        key = self.inst_map[(def_module, comp_name, tuple(bindings.items()))]
        return key, bindings


# --------------------------------------------------------------------------- #
# Argument binding (shdl.md §5.3)
# --------------------------------------------------------------------------- #


def bind_args(comp: Component, decl: InstanceDecl, env: dict[str, int]) -> dict[str, int]:
    params = comp.params
    bindings: dict[str, int] = {}
    seen_named = False
    positional_count = 0

    for arg in decl.args:
        if arg.name is None:
            if seen_named:
                raise err(
                    ErrorCode.E0903,
                    "positional argument after named argument",
                    arg.pos,
                )
            if positional_count >= len(params):
                raise err(
                    ErrorCode.E0903,
                    f"too many positional arguments for '{comp.name}' "
                    f"({len(params)} parameter(s))",
                    arg.pos,
                )
            target = params[positional_count].name
            positional_count += 1
        else:
            seen_named = True
            if arg.name not in [p.name for p in params]:
                raise err(
                    ErrorCode.E0901,
                    f"'{comp.name}' has no parameter named '{arg.name}'",
                    arg.pos,
                )
            target = arg.name
        if target in bindings:
            raise err(
                ErrorCode.E0904,
                f"parameter '{target}' of '{comp.name}' bound twice",
                arg.pos,
            )
        value = eval_arith(arg.expr, env)
        if value < 0:
            raise err(
                ErrorCode.E0905,
                f"argument for parameter '{target}' of '{comp.name}' "
                f"evaluates to {value}; parameters must be non-negative",
                arg.pos,
            )
        bindings[target] = value

    for param in params:
        if param.name not in bindings:
            if param.default is None:
                raise err(
                    ErrorCode.E0902,
                    f"parameter '{param.name}' of '{comp.name}' is not bound "
                    "and has no default",
                    decl.pos,
                )
            bindings[param.name] = param.default

    # Normalize to declaration order so binding tuples are canonical.
    return {p.name: bindings[p.name] for p in params}


# --------------------------------------------------------------------------- #
# Parameter substitution
# --------------------------------------------------------------------------- #


def _subst_expr(e: Expr, b: dict[str, int]) -> Expr:
    match e:
        case Num():
            return e
        case Name(ident=ident, pos=pos):
            if ident in b:
                return Num(b[ident], pos)
            return e
        case BinOp(op=op, left=left, right=right, pos=pos):
            return BinOp(op, _subst_expr(left, b), _subst_expr(right, b), pos)
    raise AssertionError(e)  # pragma: no cover


def _subst_bool(e: BoolExpr, b: dict[str, int]) -> BoolExpr:
    match e:
        case Cmp(left=left, op=op, right=right, pos=pos):
            return Cmp(_subst_expr(left, b), op, _subst_expr(right, b), pos)
        case BoolAnd(items=items, pos=pos):
            return BoolAnd(tuple(_subst_bool(i, b) for i in items), pos)
        case BoolOr(items=items, pos=pos):
            return BoolOr(tuple(_subst_bool(i, b) for i in items), pos)
    raise AssertionError(e)  # pragma: no cover


def _subst_template(t: NameTemplate, b: dict[str, int]) -> NameTemplate:
    parts = tuple(p if isinstance(p, str) else _subst_expr(p, b) for p in t.parts)
    return NameTemplate(parts, t.pos)


def _subst_index(index, b: dict[str, int]):
    match index:
        case None:
            return None
        case IndexBit(expr=expr):
            return IndexBit(_subst_expr(expr, b))
        case IndexSlice(lo=lo, hi=hi):
            return IndexSlice(
                None if lo is None else _subst_expr(lo, b),
                None if hi is None else _subst_expr(hi, b),
            )
    raise AssertionError(index)  # pragma: no cover


def _subst_primary(p: Primary, b: dict[str, int]) -> Primary:
    return Primary(
        _subst_template(p.base, b),
        None if p.port is None else _subst_template(p.port, b),
        _subst_index(p.index, b),
        p.pos,
    )


def _subst_signal(s: Signal, b: dict[str, int]) -> Signal:
    match s:
        case Primary():
            return _subst_primary(s, b)
        case Concat(items=items, pos=pos):
            return Concat(tuple(_subst_concat_item(i, b) for i in items), pos)
    raise AssertionError(s)  # pragma: no cover


def _subst_concat_item(item, b: dict[str, int]):
    match item:
        case Primary():
            return _subst_primary(item, b)
        case Replication(count=count, items=items, pos=pos):
            return Replication(
                _subst_expr(count, b),
                tuple(_subst_concat_item(i, b) for i in items),
                pos,
            )
    raise AssertionError(item)  # pragma: no cover


def _subst_range(r: RangeItem, b: dict[str, int]) -> RangeItem:
    match r:
        case RangeN(expr=expr, pos=pos):
            return RangeN(_subst_expr(expr, b), pos)
        case RangeAB(lo=lo, hi=hi, pos=pos):
            return RangeAB(_subst_expr(lo, b), _subst_expr(hi, b), pos)
        case RangeOpen(lo=lo, pos=pos):
            return RangeOpen(_subst_expr(lo, b), pos)
        case RangeTo(hi=hi, pos=pos):
            return RangeTo(_subst_expr(hi, b), pos)
    raise AssertionError(r)  # pragma: no cover


def _subst_items(items: tuple[GenItem, ...], b: dict[str, int]) -> tuple[GenItem, ...]:
    out: list[GenItem] = []
    for item in items:
        match item:
            case InstanceDecl(name=name, type_name=tn, type_pos=tp, args=args, pos=pos):
                out.append(
                    InstanceDecl(
                        _subst_template(name, b),
                        tn,
                        tp,
                        tuple(Arg(a.name, _subst_expr(a.expr, b), a.pos) for a in args),
                        pos,
                    )
                )
            case ConstantDecl(name=name, width=width, value=value, pos=pos):
                out.append(
                    ConstantDecl(
                        name,
                        None if width is None else _subst_expr(width, b),
                        value,
                        pos,
                    )
                )
            case Connection(src=src, dst=dst, pos=pos):
                out.append(Connection(_subst_signal(src, b), _subst_signal(dst, b), pos))
            case Generator(var=var, var_pos=vp, ranges=ranges, body=body, pos=pos):
                # A generator variable shadows a like-named parameter inside
                # its body (both are compile-time integers in the same scope
                # family); ranges are evaluated outside the shadow.
                inner = {k: v for k, v in b.items() if k != var}
                out.append(
                    Generator(
                        var,
                        vp,
                        tuple(_subst_range(r, b) for r in ranges),
                        _subst_items(body, inner),
                        pos,
                    )
                )
            case Conditional(cond=cond, then_body=tb, else_body=eb, pos=pos):
                out.append(
                    Conditional(
                        _subst_bool(cond, b),
                        _subst_items(tb, b),
                        _subst_items(eb, b),
                        pos,
                    )
                )
            case _:  # pragma: no cover
                raise AssertionError(item)
    return tuple(out)


def substitute_component(comp: Component, bindings: dict[str, int]) -> Component:
    """Clone ``comp`` with every parameter identifier replaced by its value."""
    b = dict(bindings)
    inputs = tuple(
        type(p)(p.name, None if p.width is None else _subst_expr(p.width, b), p.pos)
        for p in comp.inputs
    )
    outputs = tuple(
        type(p)(p.name, None if p.width is None else _subst_expr(p.width, b), p.pos)
        for p in comp.outputs
    )
    init_blocks = tuple(
        (pos, tuple(InitAssign(_subst_primary(a.target, b), a.value, a.pos) for a in assigns))
        for pos, assigns in comp.init_blocks
    )
    connect_blocks = tuple(
        (pos, _subst_items(items, b)) for pos, items in comp.connect_blocks
    )
    clone = Component(
        name=comp.name,
        params=(),
        inputs=inputs,
        outputs=outputs,
        decls=_subst_items(comp.decls, b),
        init_blocks=init_blocks,
        connect_blocks=connect_blocks,
        is_top=comp.is_top,
        pos=comp.pos,
        file=comp.file,
    )
    clone.module = comp.module
    return clone


# --------------------------------------------------------------------------- #
# Specialization driver
# --------------------------------------------------------------------------- #


def _spec_key(module: str, comp: Component, bindings: dict[str, int]) -> str:
    if not bindings:
        return f"{module}::{comp.name}"
    args = ", ".join(f"{k}={v}" for k, v in bindings.items())
    return f"{module}::{comp.name}<{args}>"


def monomorphize(program: Program, top_module: str, top_name: str) -> MonoProgram:
    top_comp = program.component(top_module, top_name)
    top_bindings: dict[str, int] = {}
    for param in top_comp.params:
        if param.default is None:
            raise err(
                ErrorCode.E0902,
                f"top component '{top_name}' parameter '{param.name}' has no "
                "default; a parameterized top requires defaults for all parameters",
                param.pos,
            )
        top_bindings[param.name] = param.default

    mono: MonoProgram | None = None
    stack: list[tuple[str, str]] = []  # (module, comp name) instantiation chain

    def specialize(module: str, comp: Component, bindings: dict[str, int], at: Pos) -> str:
        nonlocal mono
        key = _spec_key(module, comp, bindings)
        # The cycle check must precede the memo check: a spec is registered
        # in mono.specs before its body walk finishes, so a recursive
        # instance would hit the memo and return silently.
        if (module, comp.name) in stack:
            chain = " -> ".join(f"{m}::{n}" for m, n in stack)
            raise err(
                ErrorCode.E0311,
                f"recursive instantiation: {chain} -> {module}::{comp.name}",
                at,
            )
        if mono is not None and key in mono.specs:
            return key
        stack.append((module, comp.name))

        clone = substitute_component(comp, bindings)
        spec = SpecComponent(key=key, module=module, name=comp.name, comp=clone, bindings=bindings)
        _resolve_port_widths(spec, had_params=bool(comp.params))
        if mono is None:
            mono = MonoProgram(program, key)
        mono.specs[key] = spec
        mono.inst_map[(module, comp.name, tuple(bindings.items()))] = key

        # Discovery walk: find every instance declaration (and its concrete
        # argument tuple) so all needed specializations exist before phase 3.
        def on_instance(decl: InstanceDecl, env: dict[str, int]) -> None:
            if decl.type_name in PRIMITIVES:
                if decl.args:
                    raise err(
                        ErrorCode.E0901,
                        f"primitive type '{decl.type_name}' takes no parameters",
                        decl.type_pos,
                    )
                return
            resolved = program.resolve_type(module, decl.type_name)
            if resolved is None:
                raise err(
                    ErrorCode.E0306,
                    f"unknown component type '{decl.type_name}'",
                    decl.type_pos,
                )
            def_module, comp_name = resolved
            child = program.component(def_module, comp_name)
            child_bindings = bind_args(child, decl, env)
            specialize(def_module, child, child_bindings, decl.pos)

        walk_items(
            clone.decls,
            {},
            on_instance=on_instance,
            on_constant=lambda decl, env: None,
            on_connection=None,
            resolve_open=_reject_open_decl_range,
        )

        stack.pop()
        return key

    top_key = specialize(top_module, top_comp, top_bindings, top_comp.pos)
    assert mono is not None
    mono.top_key = top_key
    return mono


def _reject_open_decl_range(gen: Generator, item: RangeOpen, env: dict[str, int]) -> int:
    raise err(
        ErrorCode.E0602,
        "open-ended range '[a:]' has no governing signal in declaration context; "
        "give an explicit bound",
        item.pos,
    )


def _resolve_port_widths(spec: SpecComponent, had_params: bool) -> None:
    for port_list, target in ((spec.comp.inputs, spec.inputs), (spec.comp.outputs, spec.outputs)):
        for port in port_list:
            if port.width is None:
                width = 1
            else:
                width = eval_arith(port.width, {})
                if width <= 0:
                    code = ErrorCode.E0906 if had_params else ErrorCode.E0403
                    raise err(
                        code,
                        f"port '{port.name}' of '{spec.key}' has non-positive "
                        f"width {width}",
                        port.pos,
                    )
            target.append((port.name, width))
