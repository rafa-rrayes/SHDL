"""Positioned diagnostics.

The spec (shdl.md §14) fixes only the error *categories* (E03xx names, E04xx
widths, ...); the concrete codes within each category are defined here and are
part of this implementation's contract with its test suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .source import Pos


class ErrorCode(Enum):
    # E00xx — toolchain usage (top selection, I/O)
    E0001 = "E0001"  # cannot determine top component / usage error
    # E01xx — lexical
    E0101 = "E0101"  # lexical error (bad character, unterminated comment, bad number)
    # E02xx — parse
    E0201 = "E0201"  # syntax error
    # E03xx — names and references
    E0301 = "E0301"  # duplicate name
    E0303 = "E0303"  # reserved "__" identifier
    E0304 = "E0304"  # reserved "..._<digits>_" identifier (bus-expansion pattern)
    E0305 = "E0305"  # redefinition of a primitive type
    E0306 = "E0306"  # unknown component type
    E0307 = "E0307"  # unknown reference (signal / instance / port)
    E0308 = "E0308"  # collision with a flattener-generated name
    E0309 = "E0309"  # component structure (exactly one connect, at most one init)
    E0310 = "E0310"  # more than one `top`-marked component in a module
    E0311 = "E0311"  # recursive instantiation
    # E04xx — widths and indices
    E0401 = "E0401"  # connection width mismatch
    E0402 = "E0402"  # bit index out of range
    E0403 = "E0403"  # non-positive width
    E0404 = "E0404"  # invalid (empty / ill-ordered) slice
    # E05xx — connection rules
    E0501 = "E0501"  # multiple drivers
    E0502 = "E0502"  # floating input
    E0503 = "E0503"  # floating output
    E0504 = "E0504"  # self-connection
    E0505 = "E0505"  # invalid connection role (e.g. constant as destination)
    E0506 = "E0506"  # connection cycle with no gate (pure alias loop)
    # E06xx — generators and conditionals
    E0601 = "E0601"  # empty or ill-ordered range
    E0602 = "E0602"  # ambiguous / unresolvable open-ended range bound
    E0603 = "E0603"  # unbound identifier (loop variable / parameter scope)
    E0604 = "E0604"  # item illegal for its context (decl vs. connection)
    E0605 = "E0605"  # division by zero in a compile-time expression
    # E07xx — imports
    E0701 = "E0701"  # module not found
    E0702 = "E0702"  # circular import
    E0703 = "E0703"  # name not found in module
    # E08xx — constants
    E0801 = "E0801"  # constant value overflows its declared width
    # E09xx — parameters
    E0901 = "E0901"  # named argument does not match any parameter
    E0902 = "E0902"  # parameter not bound (no argument, no default)
    E0903 = "E0903"  # positional argument after named / too many positional
    E0904 = "E0904"  # parameter bound twice
    E0905 = "E0905"  # argument does not evaluate to a non-negative integer
    E0906 = "E0906"  # width derived from parameters is not positive
    # E0Axx — initial state
    E0A01 = "E0A01"  # init target is not drivable (input port or constant)
    E0A02 = "E0A02"  # net seeded more than once
    E0A03 = "E0A03"  # init value does not fit the target width


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: ErrorCode
    message: str
    pos: Pos

    def __str__(self) -> str:
        return f"{self.pos}: error[{self.code.value}]: {self.message}"


class SHDLError(Exception):
    """A fatal, positioned flattening error. The flattener stops at the first one."""

    def __init__(self, code: ErrorCode, message: str, pos: Pos):
        self.diagnostic = Diagnostic(code, message, pos)
        super().__init__(str(self.diagnostic))


def err(code: ErrorCode, message: str, pos: Pos) -> SHDLError:
    return SHDLError(code, message, pos)
