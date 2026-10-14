"""Source files and positions.

Positions are 1-based (line and column), and identify a file by its display
name (the basename, e.g. ``add2.shdl``), which is also the name used in the
emitted ``source_map`` metadata.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pos:
    """A position in an SHDL source file (1-based line and column)."""

    file: str
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"


@dataclass(frozen=True, slots=True)
class SourceFile:
    """An SHDL source file: display name, absolute path, and full text."""

    name: str
    path: str
    text: str
