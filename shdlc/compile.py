"""Orchestration: Base SHDL text -> validated Circuit -> C -> shared library."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .baseshdl import parse_base
from .cc import build_shared
from .codegen import generate_c
from .model import Circuit, build_circuit


def compile_text(base_text: str) -> tuple[Circuit, str]:
    """Parse + validate ``base_text`` and generate C for it.

    Returns ``(circuit, c_source)``. Raises BaseParseError on syntax errors
    and ModelError on structural violations.
    """
    circuit = build_circuit(parse_base(base_text))
    return circuit, generate_c(circuit)


def build_library(
    base_text: str,
    out_path: str | Path,
    *,
    cc: str | None = None,
    cflags: Sequence[str] | None = None,
    emit_c: str | Path | None = None,
) -> Path:
    """Compile ``base_text`` all the way to a shared library at ``out_path``.

    Writes the generated C to ``emit_c`` if given, otherwise to a temporary
    file next to ``out_path``. Returns ``out_path`` as a Path.
    """
    _, c_source = compile_text(base_text)
    out = Path(out_path)
    if emit_c is not None:
        c_file = Path(emit_c)
        c_file.write_text(c_source, encoding="utf-8")
        return build_shared(c_file, out, cc=cc, cflags=cflags)
    fd, tmp = tempfile.mkstemp(suffix=".c", prefix=out.stem + "-", dir=out.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(c_source)
        return build_shared(tmp, out, cc=cc, cflags=cflags)
    finally:
        os.unlink(tmp)
