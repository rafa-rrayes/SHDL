"""Phase 1 — lexical stripping and import resolution (shdl.md §9, §12).

Comments are stripped by the lexer; this module resolves `use` imports into a
program-wide component table and rejects circular imports.

Module resolution searches the directory of the *importing* file first, then
the `-I`/`--include` directories in order. (The spec says "the current
directory first"; for a file-based import system the importing file's
directory is the deterministic reading of that, and it is what makes a module
tree relocatable.)
"""

from __future__ import annotations

import os

from .ast_nodes import Component, Module
from .diagnostics import ErrorCode, err
from .parser import parse_source
from .source import Pos, SourceFile

PRIMITIVES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "AND": (("A", "B"), ("O",)),
    "OR": (("A", "B"), ("O",)),
    "NOT": (("A",), ("O",)),
    "XOR": (("A", "B"), ("O",)),
    "__VCC__": ((), ("O",)),
    "__GND__": ((), ("O",)),
}


class Program:
    """All loaded modules plus name-visibility tables.

    ``visible[module_name]`` maps a component name usable inside that module
    (its own components plus imported ones) to ``(defining_module, name)``.
    """

    def __init__(self, main_module: str):
        self.main_module = main_module
        self.modules: dict[str, Module] = {}

    @property
    def main(self) -> Module:
        return self.modules[self.main_module]

    def component(self, module: str, name: str) -> Component:
        for comp in self.modules[module].components:
            if comp.name == name:
                return comp
        raise KeyError((module, name))

    def resolve_type(self, module: str, name: str) -> tuple[str, str] | None:
        """Resolve a component type name as seen from ``module``.

        Returns ``(defining_module, component_name)`` or None if the name is
        not visible (primitives are handled by the caller).
        """
        return self.modules[module].visible.get(name)


def _read_source(path: str) -> SourceFile:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return SourceFile(name=os.path.basename(path), path=os.path.abspath(path), text=text)


def load_program(main_path: str, include_dirs: list[str] | None = None) -> Program:
    include_dirs = include_dirs or []
    main_abs = os.path.abspath(main_path)
    if not os.path.isfile(main_abs):
        raise err(
            ErrorCode.E0701,
            f"file not found: {main_path}",
            Pos(os.path.basename(main_path), 1, 1),
        )
    main_name = os.path.splitext(os.path.basename(main_abs))[0]
    program = Program(main_name)
    loading: list[str] = []  # module names currently on the import stack

    def load(path: str, module_name: str, import_pos: Pos | None) -> None:
        if module_name in program.modules:
            return
        if module_name in loading:
            cycle = " -> ".join([*loading[loading.index(module_name) :], module_name])
            assert import_pos is not None
            raise err(ErrorCode.E0702, f"circular import: {cycle}", import_pos)
        loading.append(module_name)
        src = _read_source(path)
        module = parse_source(src, module_name)
        for comp in module.components:
            comp.module = module_name

        # Register the module's own components; duplicates are an error here
        # so that import resolution below sees a consistent table.
        for comp in module.components:
            if comp.name in module.visible:
                raise err(
                    ErrorCode.E0301,
                    f"duplicate component '{comp.name}' in module '{module_name}'",
                    comp.pos,
                )
            module.visible[comp.name] = (module_name, comp.name)

        base_dir = os.path.dirname(src.path)
        for imp in module.imports:
            target_path = _resolve_module(imp.module, base_dir, include_dirs)
            if target_path is None:
                raise err(
                    ErrorCode.E0701,
                    f"module '{imp.module}' not found "
                    f"(searched {base_dir} and {len(include_dirs)} include dir(s))",
                    imp.module_pos,
                )
            load(target_path, imp.module, imp.module_pos)
            target = program.modules[imp.module]
            for name, name_pos in imp.names:
                if name not in target.visible or target.visible[name][0] != imp.module:
                    raise err(
                        ErrorCode.E0703,
                        f"module '{imp.module}' does not define component '{name}'",
                        name_pos,
                    )
                if name in module.visible:
                    raise err(
                        ErrorCode.E0301,
                        f"imported name '{name}' collides with an existing "
                        f"component or import in module '{module_name}'",
                        name_pos,
                    )
                module.visible[name] = (imp.module, name)

        program.modules[module_name] = module
        loading.pop()

    load(main_abs, main_name, None)
    return program


def _resolve_module(name: str, base_dir: str, include_dirs: list[str]) -> str | None:
    for d in [base_dir, *include_dirs]:
        candidate = os.path.join(d, f"{name}.shdl")
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None
