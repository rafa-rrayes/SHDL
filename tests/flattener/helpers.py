"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from flattener.diagnostics import ErrorCode, SHDLError
from flattener.pipeline import flatten_program

# Fixtures live at tests/fixtures (shared with tests/compiler); this module
# now sits one level deeper under tests/flattener/.
FIXTURES = Path(__file__).parent.parent / "fixtures"
TS = "2026-01-01T00:00:00Z"


def flatten_fixture(name: str, **kw):
    kw.setdefault("timestamp", TS)
    return flatten_program(str(FIXTURES / f"{name}.shdl"), **kw)


def flatten_source(tmp_path, source: str, *, name: str = "main", aux: dict | None = None, **kw):
    for mod, text in (aux or {}).items():
        (tmp_path / f"{mod}.shdl").write_text(text)
    main = tmp_path / f"{name}.shdl"
    main.write_text(source)
    kw.setdefault("timestamp", TS)
    return flatten_program(str(main), **kw)


def expect_error(code: str, tmp_path, source: str, **kw):
    """Flatten ``source`` and assert it fails with the given code at a real position."""
    with pytest.raises(SHDLError) as ei:
        flatten_source(tmp_path, source, **kw)
    d = ei.value.diagnostic
    assert d.code is ErrorCode[code], f"expected {code}, got: {d}"
    assert d.pos.line >= 1 and d.pos.col >= 1, d
    return d
