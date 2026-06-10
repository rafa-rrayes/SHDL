"""Command-line entry point for the Base SHDL -> C compiler.

    shdlc INPUT [-o LIB] [--emit-c FILE.c] [--no-build] [--cc CC]
          [--base|--shdl] [--top NAME] [-I DIR]...

Accepts a pre-flattened Base SHDL file, or a .shdl source (flattened
in-process via the flattener package). Exit status 0 on success, 1 on any
diagnosed failure, 2 on usage errors.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print("shdlc: error: not implemented yet", file=sys.stderr)
    return 1
