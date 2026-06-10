"""Command-line entry point for the Base SHDL -> C compiler.

    shdlc INPUT [-o LIB] [--emit-c FILE.c] [--no-build] [--cc CC]
          [--base|--shdl] [--top NAME] [-I DIR]...

Accepts a pre-flattened Base SHDL file, or a .shdl source (flattened
in-process via the flattener package); ``--base``/``--shdl`` override the
extension-based choice. ``--top``/``-I`` are flattener options and are
rejected for Base inputs. The default artifact path is the input stem plus
the platform library suffix, in the working directory. Exit status 0 on
success, 1 on any diagnosed failure, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .baseshdl import BaseParseError
from .cc import CCError, lib_suffix
from .compile import build_library, compile_text
from .model import ModelError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="shdlc",
        description="Compile Base SHDL (or .shdl via the flattener) to a "
        "shared library exporting reset/poke/peek/step.",
    )
    ap.add_argument("input", help="Base SHDL artifact, or .shdl source")
    ap.add_argument(
        "-o",
        "--output",
        metavar="LIB",
        help=f"shared-library path (default: input stem + {lib_suffix()!r} "
        "in the working directory)",
    )
    ap.add_argument(
        "--emit-c",
        metavar="FILE.c",
        help="also write the generated C here (default: input stem + '.c' "
        "when --no-build is given)",
    )
    ap.add_argument(
        "--no-build",
        action="store_true",
        help="stop after generating C; do not invoke the C compiler",
    )
    ap.add_argument(
        "--cc",
        metavar="CC",
        help="C compiler to use (default: $CC, then cc/clang/gcc)",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--base",
        action="store_true",
        help="treat INPUT as Base SHDL regardless of extension",
    )
    mode.add_argument(
        "--shdl",
        action="store_true",
        help="treat INPUT as SHDL source regardless of extension",
    )
    ap.add_argument(
        "--top",
        metavar="NAME",
        help="top component (SHDL inputs only; passed to the flattener)",
    )
    ap.add_argument(
        "-I",
        "--include",
        action="append",
        default=[],
        metavar="DIR",
        help="module search directory (SHDL inputs only; may be repeated)",
    )
    args = ap.parse_args(argv)

    in_path = Path(args.input)
    is_shdl = args.shdl or (not args.base and in_path.suffix == ".shdl")
    if not is_shdl and (args.top or args.include):
        ap.error("--top and -I apply only to .shdl inputs")

    try:
        if is_shdl:
            # Lazy import: Base-only usage must not require the flattener.
            from flattener.diagnostics import SHDLError
            from flattener.pipeline import flatten_program

            try:
                base_text = flatten_program(
                    str(in_path), include_dirs=args.include, top=args.top
                ).text
            except SHDLError as e:
                print(f"shdlc: error: {e.diagnostic}", file=sys.stderr)
                return 1
        else:
            base_text = in_path.read_text(encoding="utf-8")

        emit_c = args.emit_c
        if args.no_build:
            if emit_c is None:
                emit_c = f"{in_path.stem}.c"
            _, c_source = compile_text(base_text)
            Path(emit_c).write_text(c_source, encoding="utf-8")
            return 0

        out = args.output or f"{in_path.stem}{lib_suffix()}"
        build_library(base_text, out, cc=args.cc, emit_c=emit_c)
        return 0
    except (BaseParseError, ModelError, CCError, OSError) as e:
        print(f"shdlc: error: {e}", file=sys.stderr)
        return 1
