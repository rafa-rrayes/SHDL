"""Command-line entry point.

    shdlc FILE [--top NAME] [-I DIR]... [-o FILE] [--timestamp TS]

Exit status 0 on success, 1 on any positioned diagnostic or I/O failure.
Diagnostics go to stderr in the ``file:line:col: error[CODE]: message``
format (shdl.md §14); the Base SHDL text goes to ``-o`` or stdout.
"""

from __future__ import annotations

import argparse
import sys

from .diagnostics import SHDLError
from .pipeline import flatten_program


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="shdlc",
        description="Flatten SHDL to Base SHDL (a single-bit primitive netlist).",
    )
    ap.add_argument("file", help="main .shdl source file")
    ap.add_argument(
        "--top",
        metavar="NAME",
        help="top component (default: the unique 'top'-marked component, "
        "or the sole component of the main module)",
    )
    ap.add_argument(
        "-I",
        "--include",
        action="append",
        default=[],
        metavar="DIR",
        help="additional directory to search for imported modules "
        "(may be repeated)",
    )
    ap.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write the Base SHDL here instead of stdout",
    )
    ap.add_argument(
        "--timestamp",
        metavar="TS",
        help="pin doc.flattened_at to this string (SOURCE_DATE_EPOCH is "
        "also honored); default is the current UTC time",
    )
    args = ap.parse_args(argv)

    try:
        out = flatten_program(
            args.file,
            include_dirs=args.include,
            top=args.top,
            timestamp=args.timestamp,
        )
    except SHDLError as e:
        print(e.diagnostic, file=sys.stderr)
        return 1
    except OSError as e:
        print(f"shdlc: error: {e}", file=sys.stderr)
        return 1

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(out.text)
        except OSError as e:
            print(f"shdlc: error: {e}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(out.text)
    return 0
