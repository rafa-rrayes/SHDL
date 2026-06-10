"""Pre-monomorphization validation (shdl.md §14).

Checks everything that does not depend on parameter values: name rules
(reserved patterns, duplicates, primitive shadowing), component structure
(exactly one connect block, at most one init block, at most one `top` per
module), type-name visibility, and literal constant overflow. Validity that
depends on parameter values is checked after phase 2, per instantiation.
"""

from __future__ import annotations

import re

from .ast_nodes import (
    Component,
    Conditional,
    ConstantDecl,
    GenItem,
    Generator,
    InstanceDecl,
    Module,
    Num,
)
from .diagnostics import ErrorCode, err
from .loader import PRIMITIVES, Program
from .source import Pos

_BUS_PATTERN = re.compile(r".*_[0-9]+_$")


def check_user_name(name: str, what: str, pos: Pos) -> None:
    """Reject reserved identifier shapes (shdl.md §2.2)."""
    if name.startswith("__"):
        raise err(
            ErrorCode.E0303,
            f"{what} '{name}' uses the reserved '__' prefix",
            pos,
        )
    if _BUS_PATTERN.match(name):
        raise err(
            ErrorCode.E0304,
            f"{what} '{name}' matches the reserved bus-expansion pattern '..._<digits>_'",
            pos,
        )


def validate_program(program: Program) -> None:
    for module in program.modules.values():
        _validate_module(program, module)


def _validate_module(program: Program, module: Module) -> None:
    top_marked = [c for c in module.components if c.is_top]
    if len(top_marked) > 1:
        raise err(
            ErrorCode.E0310,
            f"module '{module.name}' marks more than one component as 'top'",
            top_marked[1].pos,
        )
    for comp in module.components:
        _validate_component(program, module, comp)


def _validate_component(program: Program, module: Module, comp: Component) -> None:
    if comp.name in PRIMITIVES:
        raise err(
            ErrorCode.E0305,
            f"component '{comp.name}' redefines a primitive type",
            comp.pos,
        )
    check_user_name(comp.name, "component name", comp.pos)

    if len(comp.connect_blocks) != 1:
        raise err(
            ErrorCode.E0309,
            f"component '{comp.name}' must contain exactly one connect block "
            f"(found {len(comp.connect_blocks)})",
            comp.connect_blocks[1][0] if len(comp.connect_blocks) > 1 else comp.pos,
        )
    if len(comp.init_blocks) > 1:
        raise err(
            ErrorCode.E0309,
            f"component '{comp.name}' may contain at most one init block",
            comp.init_blocks[1][0],
        )

    if comp.is_top and comp.params and any(p.default is None for p in comp.params):
        raise err(
            ErrorCode.E0902,
            f"'top' component '{comp.name}' has parameters without defaults",
            comp.pos,
        )

    seen: dict[str, Pos] = {}

    def declare(name: str, what: str, pos: Pos) -> None:
        check_user_name(name, what, pos)
        if name in seen:
            raise err(
                ErrorCode.E0301,
                f"duplicate name '{name}' in component '{comp.name}' "
                f"(first declared at {seen[name]})",
                pos,
            )
        seen[name] = pos

    for param in comp.params:
        declare(param.name, "parameter name", param.pos)
    for port in [*comp.inputs, *comp.outputs]:
        declare(port.name, "port name", port.pos)

    # Walk declarations (including generator/conditional bodies). Names that
    # carry substitutions are only checkable after expansion; plain names are
    # checked here for early, well-positioned errors.
    def walk(items: tuple[GenItem, ...]) -> None:
        for item in items:
            match item:
                case InstanceDecl():
                    if item.name.is_plain:
                        declare(item.name.plain, "instance name", item.name.pos)
                    _check_type_ref(program, module, item)
                case ConstantDecl():
                    declare(item.name, "constant name", item.pos)
                    _check_constant(item)
                case Generator():
                    check_user_name(item.var, "generator variable", item.var_pos)
                    walk(item.body)
                case Conditional():
                    walk(item.then_body)
                    walk(item.else_body)
                case _:
                    pass

    walk(comp.decls)
    for _, items in comp.connect_blocks:
        _walk_connect_types(program, module, items)


def _walk_connect_types(program: Program, module: Module, items: tuple[GenItem, ...]) -> None:
    for item in items:
        match item:
            case Generator():
                _walk_connect_types(program, module, item.body)
            case Conditional():
                _walk_connect_types(program, module, item.then_body)
                _walk_connect_types(program, module, item.else_body)
            case _:
                pass


def _check_type_ref(program: Program, module: Module, decl: InstanceDecl) -> None:
    if decl.type_name in PRIMITIVES:
        if decl.args:
            raise err(
                ErrorCode.E0901,
                f"primitive type '{decl.type_name}' takes no parameters",
                decl.type_pos,
            )
        return
    if program.resolve_type(module.name, decl.type_name) is None:
        raise err(
            ErrorCode.E0306,
            f"unknown component type '{decl.type_name}'",
            decl.type_pos,
        )


def _check_constant(decl: ConstantDecl) -> None:
    # Value overflow against a *literal* declared width (shdl.md §8.1).
    # Parameter-dependent widths are re-checked after monomorphization.
    if decl.width is not None and isinstance(decl.width, Num):
        width = decl.width.value
        if width <= 0:
            raise err(
                ErrorCode.E0403,
                f"constant '{decl.name}' has non-positive width {width}",
                decl.pos,
            )
        if decl.value >= (1 << width):
            raise err(
                ErrorCode.E0801,
                f"constant '{decl.name}' value {decl.value} does not fit in {width} bits",
                decl.pos,
            )
