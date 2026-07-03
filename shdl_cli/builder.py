"""Driving the toolchain for a project: flatten -> C -> shared library.

Everything here is a thin adapter over the in-process pipeline
(``flattener.pipeline.flatten_program`` + ``shdlc.compile.build_library`` —
the same path :class:`SHDL.Circuit` takes). Builds always run from scratch:
at this scale a full rebuild is seconds, and staleness bugs are worse.

Toolchain imports are function-local so ``shdl new`` / ``search`` / ``info``
work even if the C compiler or toolchain modules are unhappy.
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import CliError
from .project import Project

_COMPONENT_DEF = re.compile(
    r"^\s*(?:top\s+)?component\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)


def _defines(path: Path, top: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return top in _COMPONENT_DEF.findall(text)


def _entry_module(project: Project, top: str | None) -> Path:
    """The module to hand the toolchain: main, unless ``top`` names a
    component defined in another project module — the flattener resolves
    --top only against the entry module, and ``shdl test`` cases may target
    any project component."""
    main = project.main_path
    if top is None or _defines(main, top):
        return main
    skip = (project.modules_dir.resolve(), project.build_dir.resolve())
    roots = {main.parent.resolve()}
    src = project.root / "src"
    if src.is_dir():
        roots.add(src.resolve())
    hits: list[Path] = []
    for root in sorted(roots):
        for p in sorted(root.rglob("*.shdl")):
            rp = p.resolve()
            if rp == main.resolve() or any(rp.is_relative_to(s) for s in skip):
                continue
            if _defines(p, top):
                hits.append(p)
    if len(hits) > 1:
        raise CliError(
            f"component {top!r} is defined in more than one project module: "
            + ", ".join(str(p) for p in hits)
        )
    # no hit: let the flattener report the missing component verbatim
    return hits[0] if hits else main


def flatten(project: Project, include_dirs: list[str], top: str | None) -> str:
    """Flattened Base SHDL text for the project's main module."""
    from flattener.diagnostics import SHDLError
    from flattener.pipeline import flatten_program

    if not project.main_path.is_file():
        raise CliError(f"main module not found: {project.main_path}")
    entry = _entry_module(project, top or project.top)
    try:
        return flatten_program(
            str(entry), include_dirs or None, top or project.top
        ).text
    except SHDLError as e:
        # the flattener's diagnostics are the user-facing message, verbatim
        raise CliError(str(e.diagnostic)) from e


def build(
    project: Project,
    include_dirs: list[str],
    *,
    top: str | None = None,
    output: str | None = None,
    dev: bool = False,
    cc: str | None = None,
    emit_base: bool = False,
) -> Path:
    """Build the shared library into build/ and return its path."""
    from shdlc.baseshdl import BaseParseError
    from shdlc.cc import DEV_CFLAGS, CCError, lib_suffix
    from shdlc.compile import build_library
    from shdlc.model import ModelError

    base_text = flatten(project, include_dirs, top)
    project.build_dir.mkdir(parents=True, exist_ok=True)
    if emit_base:
        (project.build_dir / f"{project.name}.base.shdl").write_text(
            base_text, encoding="utf-8"
        )
    out = Path(output) if output else project.build_dir / f"{project.name}{lib_suffix()}"
    try:
        build_library(
            base_text, out, cc=cc, cflags=DEV_CFLAGS if dev else None
        )
    except (BaseParseError, ModelError, CCError, OSError) as e:
        raise CliError(str(e)) from e
    return out


def open_circuit(
    project: Project,
    include_dirs: list[str],
    top: str | None,
    *,
    dev: bool = False,
    cc: str | None = None,
):
    """A live :class:`SHDL.Circuit` over the project's main module."""
    from SHDL import Circuit
    from SHDL.errors import PySHDLError
    from shdlc.cc import DEV_CFLAGS

    if not project.main_path.is_file():
        raise CliError(f"main module not found: {project.main_path}")
    entry = _entry_module(project, top or project.top)
    try:
        return Circuit(
            str(entry),
            top=top or project.top,
            include_dirs=include_dirs,
            cc=cc,
            cflags=DEV_CFLAGS if dev else None,
        )
    except PySHDLError as e:
        raise CliError(str(e)) from e
