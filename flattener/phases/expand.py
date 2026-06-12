"""Phase 3 — generator & conditional expansion (shdl.md §7, §12).

Unrolls every generator (evaluating ``{expr}`` substitutions), resolves every
`when` guard, and evaluates all name templates, indices, slice bounds, and
replication counts to concrete values. After this phase a component is a flat
list of instances, constants, connections, and init seeds — multi-bit and
hierarchical, but free of repetition constructs.

The item walker (:func:`walk_items`) is shared with phase 2's discovery walk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from ..ast_nodes import (
    Concat,
    Conditional,
    Connection,
    ConstantDecl,
    GenItem,
    Generator,
    IndexBit,
    IndexSlice,
    InstanceDecl,
    NameTemplate,
    Primary,
    RangeAB,
    RangeN,
    RangeOpen,
    RangeTo,
    Replication,
    Signal,
)
from ..diagnostics import ErrorCode, SHDLError, err
from ..expr import eval_arith, eval_bool, expr_names
from ..loader import PRIMITIVES
from ..source import Pos
from ..validate import check_user_name

if TYPE_CHECKING:  # pragma: no cover
    from .monomorphize import MonoProgram, SpecComponent

# --------------------------------------------------------------------------- #
# Shared item walker
# --------------------------------------------------------------------------- #

OpenResolver = Callable[[Generator, RangeOpen, dict[str, int]], int]

#: Upper bound on the number of values a single generator range may iterate.
#: Without it a pathological span (`>i[1:10**9]`) materializes a billion-entry
#: Python list and hangs/OOMs before any structural check fires. The cap turns
#: that into a fast, positioned diagnostic — the flattener-side mirror of the
#: compiler's wire-index ceiling (shdlc.model._MAX_INPUT_WIRES). Reuses E0601
#: (the range-error code): a range too large to materialize is, like an empty
#: or negative one, a range whose value domain cannot be realized.
MAX_RANGE_VALUES = 1_000_000


def _guard_span(count: int, pos: Pos, descr: str) -> None:
    """Reject a range that would materialize more than ``MAX_RANGE_VALUES``
    values before the list is built (so the guard is O(1), never an OOM)."""
    if count > MAX_RANGE_VALUES:
        raise err(
            ErrorCode.E0601,
            f"{descr} would iterate {count} times, exceeding the "
            f"{MAX_RANGE_VALUES} instance-count cap; narrow the range",
            pos,
        )


def walk_items(
    items: tuple[GenItem, ...],
    env: dict[str, int],
    *,
    on_instance: Callable[[InstanceDecl, dict[str, int]], None],
    on_constant: Callable[[ConstantDecl, dict[str, int]], None],
    on_connection: Callable[[Connection, dict[str, int]], None] | None,
    resolve_open: OpenResolver,
) -> None:
    """Walk generator/conditional items, expanding loops and resolving guards.

    The parser guarantees context legality (declarations never appear in
    connection context and vice versa), so the callbacks fire only where
    their item kind is legal.
    """
    for item in items:
        match item:
            case InstanceDecl():
                on_instance(item, env)
            case ConstantDecl():
                on_constant(item, env)
            case Connection():
                assert on_connection is not None
                on_connection(item, env)
            case Conditional():
                body = item.then_body if eval_bool(item.cond, env) else item.else_body
                walk_items(
                    body,
                    env,
                    on_instance=on_instance,
                    on_constant=on_constant,
                    on_connection=on_connection,
                    resolve_open=resolve_open,
                )
            case Generator():
                for value in range_values(item, env, resolve_open):
                    walk_items(
                        item.body,
                        {**env, item.var: value},
                        on_instance=on_instance,
                        on_constant=on_constant,
                        on_connection=on_connection,
                        resolve_open=resolve_open,
                    )
            case _:  # pragma: no cover
                raise AssertionError(item)


def range_values(gen: Generator, env: dict[str, int], resolve_open: OpenResolver) -> list[int]:
    values: list[int] = []
    for item in gen.ranges:
        match item:
            case RangeN(expr=expr, pos=pos):
                n = eval_arith(expr, env)
                if len(gen.ranges) > 1:
                    # In a multi-range list a bare expression is a single
                    # value (§7.1: [1:4, 8, 12:16] includes just 8), not a
                    # count; the count form applies to a sole bare range.
                    if n < 0:
                        raise err(
                            ErrorCode.E0601, f"range value {n} is negative", pos
                        )
                    values.append(n)
                    continue
                if n < 1:
                    raise err(
                        ErrorCode.E0601,
                        f"range [{n}] is empty; a count range needs N >= 1",
                        pos,
                    )
                _guard_span(n, pos, f"count range [{n}]")
                values.extend(range(1, n + 1))
            case RangeAB(lo=lo, hi=hi, pos=pos):
                a = eval_arith(lo, env)
                b = eval_arith(hi, env)
                if a < 0:
                    raise err(ErrorCode.E0601, f"range bound {a} is negative", pos)
                if a > b:
                    raise err(
                        ErrorCode.E0601,
                        f"range [{a}:{b}] is empty or ill-ordered",
                        pos,
                    )
                _guard_span(b - a + 1, pos, f"range [{a}:{b}]")
                values.extend(range(a, b + 1))
            case RangeTo(hi=hi, pos=pos):
                b = eval_arith(hi, env)
                if b < 1:
                    raise err(
                        ErrorCode.E0601,
                        f"range [:{b}] is empty; the bound must be >= 1",
                        pos,
                    )
                _guard_span(b, pos, f"range [:{b}]")
                values.extend(range(1, b + 1))
            case RangeOpen(lo=lo, pos=pos):
                a = eval_arith(lo, env)
                if a < 0:
                    raise err(ErrorCode.E0601, f"range bound {a} is negative", pos)
                b = resolve_open(gen, item, env)
                if a > b:
                    raise err(
                        ErrorCode.E0601,
                        f"open-ended range resolves to [{a}:{b}], which is empty",
                        pos,
                    )
                _guard_span(b - a + 1, pos, f"open-ended range [{a}:{b}]")
                values.extend(range(a, b + 1))
            case _:  # pragma: no cover
                raise AssertionError(item)
    return values


def subst_template(template: NameTemplate, env: dict[str, int]) -> str:
    parts: list[str] = []
    for part in template.parts:
        if isinstance(part, str):
            parts.append(part)
        else:
            parts.append(str(eval_arith(part, env)))
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Expanded (resolved) model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RPrimary:
    """A fully resolved signal reference.

    ``index`` is None (whole signal), ``("bit", k)``, or ``("slice", a, b)``
    with concrete 1-based bounds (open ends already resolved).
    """

    base: str
    port: str | None
    index: tuple | None
    pos: Pos


@dataclass(frozen=True, slots=True)
class RRepl:
    count: int
    items: tuple
    pos: Pos


@dataclass(frozen=True, slots=True)
class RConcat:
    items: tuple
    pos: Pos


type RSignal = RPrimary | RConcat


@dataclass(frozen=True, slots=True)
class RConn:
    src: RSignal
    dst: RSignal
    pos: Pos


@dataclass(frozen=True, slots=True)
class InstInfo:
    name: str
    kind: str  # "prim" | "comp"
    type_ref: str  # primitive name, or spec key for user components
    display_type: str  # original component type name as written
    bindings: dict[str, int] | None  # bound parameters (user components)
    pos: Pos  # the instance declaration site (= instantiation site)


@dataclass(frozen=True, slots=True)
class ConstInfo:
    name: str
    declared_width: int | None
    value: int
    pos: Pos

    @property
    def effective_width(self) -> int:
        """Declared width, else the value's significant bits (min 1) — the
        width used for whole-vector references and the metadata block."""
        if self.declared_width is not None:
            return self.declared_width
        return max(1, self.value.bit_length())


@dataclass(slots=True)
class ExpandedComponent:
    key: str
    name: str
    module: str
    file: str
    def_pos: Pos
    bindings: dict[str, int]
    inputs: list[tuple[str, int]]
    outputs: list[tuple[str, int]]
    instances: dict[str, InstInfo] = field(default_factory=dict)
    constants: dict[str, ConstInfo] = field(default_factory=dict)
    connections: list[RConn] = field(default_factory=list)
    init: list[tuple[RPrimary, int, Pos]] = field(default_factory=list)
    doc_comment: str | None = None

    # -- signal tables -------------------------------------------------------

    def port_dir(self, name: str) -> str | None:
        for n, _ in self.inputs:
            if n == name:
                return "in"
        for n, _ in self.outputs:
            if n == name:
                return "out"
        return None

    def port_width(self, name: str) -> int | None:
        for n, w in [*self.inputs, *self.outputs]:
            if n == name:
                return w
        return None


# --------------------------------------------------------------------------- #
# Signal tables
# --------------------------------------------------------------------------- #


def signal_width(
    ec: ExpandedComponent, mono: MonoProgram, base: str, port: str | None, pos: Pos
) -> int:
    """Width of the whole (unindexed) signal ``base`` / ``base.port``."""
    if port is None:
        w = ec.port_width(base)
        if w is not None:
            return w
        if base in ec.constants:
            return ec.constants[base].effective_width
        if base in ec.instances:
            raise err(
                ErrorCode.E0307,
                f"instance '{base}' used as a signal; reference one of its "
                f"ports (e.g. '{base}.O')",
                pos,
            )
        raise err(ErrorCode.E0307, f"unknown signal '{base}'", pos)
    info = ec.instances.get(base)
    if info is None:
        raise err(ErrorCode.E0307, f"unknown instance '{base}'", pos)
    if info.kind == "prim":
        ins, outs = PRIMITIVES[info.type_ref]
        if port in ins or port in outs:
            return 1
        raise err(
            ErrorCode.E0307,
            f"primitive '{info.type_ref}' has no port '{port}'",
            pos,
        )
    child = mono.specs[info.type_ref]
    w = child.port_width(port)
    if w is None:
        raise err(
            ErrorCode.E0307,
            f"component '{child.name}' has no port '{port}'",
            pos,
        )
    return w


def instance_port_dir(
    ec: ExpandedComponent, mono: MonoProgram, inst: str, port: str, pos: Pos
) -> str:
    """Direction ('in'/'out') of ``inst.port``; raises E0307 if unknown."""
    info = ec.instances.get(inst)
    if info is None:
        raise err(ErrorCode.E0307, f"unknown instance '{inst}'", pos)
    if info.kind == "prim":
        ins, outs = PRIMITIVES[info.type_ref]
        if port in ins:
            return "in"
        if port in outs:
            return "out"
        raise err(
            ErrorCode.E0307,
            f"primitive '{info.type_ref}' has no port '{port}'",
            pos,
        )
    child = mono.specs[info.type_ref]
    d = child.port_dir(port)
    if d is None:
        raise err(
            ErrorCode.E0307,
            f"component '{child.name}' has no port '{port}'",
            pos,
        )
    return d


# --------------------------------------------------------------------------- #
# Component expansion
# --------------------------------------------------------------------------- #


def expand_component(spec: SpecComponent, mono: MonoProgram) -> ExpandedComponent:
    comp = spec.comp
    ec = ExpandedComponent(
        key=spec.key,
        name=spec.name,
        module=spec.module,
        file=comp.file,
        def_pos=comp.pos,
        bindings=spec.bindings,
        inputs=list(spec.inputs),
        outputs=list(spec.outputs),
    )

    def declare_name(name: str, what: str, pos: Pos) -> None:
        check_user_name(name, what, pos)
        if ec.port_dir(name) is not None:
            raise err(
                ErrorCode.E0301,
                f"{what} '{name}' collides with a port of '{comp.name}'",
                pos,
            )
        if name in ec.instances or name in ec.constants:
            raise err(
                ErrorCode.E0301,
                f"duplicate name '{name}' in component '{comp.name}'",
                pos,
            )

    def on_instance(decl: InstanceDecl, env: dict[str, int]) -> None:
        name = subst_template(decl.name, env)
        declare_name(name, "instance name", decl.name.pos)
        if decl.type_name in PRIMITIVES:
            ec.instances[name] = InstInfo(
                name, "prim", decl.type_name, decl.type_name, None, decl.pos
            )
        else:
            key, bindings = mono.spec_for_instance(spec.module, decl, env)
            ec.instances[name] = InstInfo(
                name, "comp", key, decl.type_name, bindings, decl.pos
            )

    def on_constant(decl: ConstantDecl, env: dict[str, int]) -> None:
        declare_name(decl.name, "constant name", decl.pos)
        width: int | None = None
        if decl.width is not None:
            width = eval_arith(decl.width, env)
            if width <= 0:
                raise err(
                    ErrorCode.E0403,
                    f"constant '{decl.name}' has non-positive width {width}",
                    decl.pos,
                )
            if decl.value >= (1 << width):
                raise err(
                    ErrorCode.E0801,
                    f"constant '{decl.name}' value {decl.value} does not fit "
                    f"in {width} bits",
                    decl.pos,
                )
        ec.constants[decl.name] = ConstInfo(decl.name, width, decl.value, decl.pos)

    walk_items(
        comp.decls,
        {},
        on_instance=on_instance,
        on_constant=on_constant,
        on_connection=None,
        resolve_open=_reject_open_decl,
    )

    # -- connect block ---------------------------------------------------- #

    def lenient_width(base: str, port: str | None) -> int | None:
        try:
            return signal_width(ec, mono, base, port, Pos("", 0, 0))
        except SHDLError:
            return None

    def resolve_open_conn(gen: Generator, item: RangeOpen, env: dict[str, int]) -> int:
        widths = _governing_widths(gen, env, lenient_width)
        if not widths:
            raise err(
                ErrorCode.E0602,
                f"cannot resolve open-ended range bound: no signal in the "
                f"generator body is indexed by '{gen.var}'",
                item.pos,
            )
        if len(widths) > 1:
            raise err(
                ErrorCode.E0602,
                f"ambiguous open-ended range bound: signals of widths "
                f"{sorted(widths)} are indexed by '{gen.var}'; give an "
                "explicit bound",
                item.pos,
            )
        return next(iter(widths))

    def resolve_primary(p: Primary, env: dict[str, int]) -> RPrimary:
        base = subst_template(p.base, env)
        port = None if p.port is None else subst_template(p.port, env)
        index: tuple | None = None
        match p.index:
            case None:
                index = None
            case IndexBit(expr=expr):
                index = ("bit", eval_arith(expr, env))
            case IndexSlice(lo=lo, hi=hi):
                a = 1 if lo is None else eval_arith(lo, env)
                if hi is None:
                    b = signal_width(ec, mono, base, port, p.pos)
                else:
                    b = eval_arith(hi, env)
                index = ("slice", a, b)
        return RPrimary(base, port, index, p.pos)

    def resolve_concat_item(item, env: dict[str, int]):
        match item:
            case Primary():
                return resolve_primary(item, env)
            case Replication(count=count, items=items, pos=pos):
                n = eval_arith(count, env)
                if n < 1:
                    raise err(
                        ErrorCode.E0601,
                        f"replication count must be >= 1, got {n}",
                        pos,
                    )
                _guard_span(n, pos, "replication")
                return RRepl(n, tuple(resolve_concat_item(i, env) for i in items), pos)
        raise AssertionError(item)  # pragma: no cover

    def resolve_signal(s: Signal, env: dict[str, int]) -> RSignal:
        match s:
            case Primary():
                return resolve_primary(s, env)
            case Concat(items=items, pos=pos):
                return RConcat(tuple(resolve_concat_item(i, env) for i in items), pos)
        raise AssertionError(s)  # pragma: no cover

    def on_connection(conn: Connection, env: dict[str, int]) -> None:
        ec.connections.append(
            RConn(resolve_signal(conn.src, env), resolve_signal(conn.dst, env), conn.pos)
        )

    for _, items in comp.connect_blocks:
        walk_items(
            items,
            {},
            on_instance=on_instance,
            on_constant=on_constant,
            on_connection=on_connection,
            resolve_open=resolve_open_conn,
        )

    # -- init block --------------------------------------------------------- #

    for _, assigns in comp.init_blocks:
        for assign in assigns:
            target = resolve_primary(assign.target, {})
            ec.init.append((target, assign.value, assign.pos))

    return ec


def _reject_open_decl(gen: Generator, item: RangeOpen, env: dict[str, int]) -> int:
    raise err(
        ErrorCode.E0602,
        "open-ended range '[a:]' has no governing signal in declaration "
        "context; give an explicit bound",
        item.pos,
    )


def _governing_widths(
    gen: Generator,
    env: dict[str, int],
    lenient_width: Callable[[str, str | None], int | None],
) -> set[int]:
    """Widths of all signals whose index expressions reference ``gen.var``
    (shdl.md §7.1: the governing signal of an open-ended range)."""
    var = gen.var
    widths: set[int] = set()

    def scan_primary(p: Primary, shadow: set[str]) -> None:
        if var in shadow:
            return
        refs: set[str] = set()
        match p.index:
            case IndexBit(expr=expr):
                refs = expr_names(expr)
            case IndexSlice(lo=lo, hi=hi):
                if lo is not None:
                    refs |= expr_names(lo)
                if hi is not None:
                    refs |= expr_names(hi)
            case None:
                return
        if var not in refs:
            return
        # The base/port templates may themselves carry substitutions; they
        # must not depend on the open range being resolved, so evaluate with
        # the current (outer) environment only.
        try:
            base = subst_template(p.base, env)
            port = None if p.port is None else subst_template(p.port, env)
        except Exception:
            return
        w = lenient_width(base, port)
        if w is not None:
            widths.add(w)

    def scan_signal(s, shadow: set[str]) -> None:
        match s:
            case Primary():
                scan_primary(s, shadow)
            case Concat(items=items):
                for item in items:
                    scan_concat_item(item, shadow)

    def scan_concat_item(item, shadow: set[str]) -> None:
        match item:
            case Primary():
                scan_primary(item, shadow)
            case Replication(items=items):
                for sub in items:
                    scan_concat_item(sub, shadow)

    def scan_items(items: tuple[GenItem, ...], shadow: set[str]) -> None:
        for item in items:
            match item:
                case Connection(src=src, dst=dst):
                    scan_signal(src, shadow)
                    scan_signal(dst, shadow)
                case Generator(var=inner_var, body=body):
                    scan_items(body, shadow | {inner_var})
                case Conditional(then_body=tb, else_body=eb):
                    scan_items(tb, shadow)
                    scan_items(eb, shadow)
                case _:
                    pass

    scan_items(gen.body, set())
    return widths


def expand_all(mono: MonoProgram) -> dict[str, ExpandedComponent]:
    """Expand every specialization, top first (insertion order of discovery)."""
    return {key: expand_component(spec, mono) for key, spec in mono.specs.items()}
