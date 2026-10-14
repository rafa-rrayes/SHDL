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
        # Unreachable from user input (ROB-1 route a): every caller passes a
        # (module, name) pair obtained from `resolve_type`, i.e. from a
        # module's `visible` table, which is populated only from components
        # that actually exist in that module. A miss here is an internal
        # invariant violation, not a user error.
        raise AssertionError(f"internal: no component '{name}' in module '{module}'")

    def resolve_type(self, module: str, name: str) -> tuple[str, str] | None:
        """Resolve a component type name as seen from ``module``.

        Returns ``(defining_module, component_name)`` or None if the name is
        not visible (primitives are handled by the caller).
        """
        return self.modules[module].visible.get(name)


def _read_source(path: str) -> SourceFile:
    name = os.path.basename(path)
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        # AMB-15: SHDL source is UTF-8; undecodable bytes die here, at the
        # read boundary, as a positioned diagnostic — never a raw
        # UnicodeDecodeError escaping to the CLI. We report a 1-based column
        # by counting bytes from the last newline (sufficient for ASCII text
        # up to the offending byte; the line is exact).
        line = raw.count(b"\n", 0, e.start) + 1
        col = e.start - raw.rfind(b"\n", 0, e.start)
        raise err(
            ErrorCode.E0101,
            f"source is not valid UTF-8: {e.reason} at byte {e.start}",
            Pos(name, line, col),
        ) from e
    return SourceFile(name=name, path=os.path.abspath(path), text=text)


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
            # AMB-27: module identity is program-global by bare name. If a
            # second `use` of the same name resolves to a *different* file,
            # that is an ambiguity, not a silent first-one-wins bind.
            loaded_path = program.modules[module_name].path
            if os.path.abspath(path) != loaded_path:
                assert import_pos is not None
                raise err(
                    ErrorCode.E0701,
                    f"module '{module_name}' resolves to two different files: "
                    f"already loaded {loaded_path}, now {os.path.abspath(path)}",
                    import_pos,
                )
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
            target_path, actual_name = _resolve_module(
                imp.module, base_dir, include_dirs
            )
            if target_path is None:
                raise err(
                    ErrorCode.E0701,
                    f"module '{imp.module}' not found "
                    f"(searched {base_dir} and {len(include_dirs)} include dir(s))",
                    imp.module_pos,
                )
            if actual_name != imp.module:
                # IMP-11/AMB-28: a case-insensitive filesystem (APFS, NTFS)
                # lets `use Add2` open add2.shdl; pin a platform-independent
                # contract by comparing the import name to the real on-disk
                # basename. The mismatch is rejected everywhere.
                raise err(
                    ErrorCode.E0701,
                    f"module '{imp.module}' not found: the file on disk is "
                    f"'{actual_name}.shdl' (case mismatch with '{imp.module}.shdl')",
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


def _resolve_module(
    name: str, base_dir: str, include_dirs: list[str]
) -> tuple[str | None, str | None]:
    """Resolve ``name`` to ``(abs_path, on_disk_name)`` over the ordered search
    path (importing file's dir, then ``-I`` dirs). ``on_disk_name`` is the
    real basename without the ``.shdl`` suffix, so a caller can detect a
    case-insensitive-filesystem mismatch (IMP-11). Returns ``(None, None)``
    when no file exists for ``name`` in any directory."""
    filename = f"{name}.shdl"
    for d in [base_dir, *include_dirs]:
        candidate = os.path.join(d, filename)
        if os.path.isfile(candidate):
            # Recover the real on-disk case from the directory listing so the
            # check is independent of the filesystem's case sensitivity.
            search_dir = d or os.curdir
            try:
                entries = os.listdir(search_dir)
            except OSError:
                entries = []
            actual = next(
                (e for e in entries if e.lower() == filename.lower()), filename
            )
            actual_name = actual[: -len(".shdl")] if actual.endswith(".shdl") else actual
            return os.path.abspath(candidate), actual_name
    return None, None
