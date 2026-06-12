"""``shdl-conformance``: command-line entry point for the conformance suite.

Subcommands:

- ``run`` — check every golden against the current toolchain (Tier A
  re-flattens and byte-compares; Tiers B/C compile the frozen base and
  replay traces). Nonzero exit on any failure.
- ``verify-oracle`` — re-derive every trace golden from the BaseEval-backed
  oracle and run the C library in lockstep against it.
- ``regen`` — explicit, single-case golden regeneration; dry-run diff by
  default, writes only with ``--write``. There is no bulk mode.
- ``list`` — enumerate cases.
"""

from __future__ import annotations

import argparse

from .gen import regen_case
from .schema import ConformanceError
from .suite import list_cases, run, verify_oracle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="shdl-conformance",
        description="Run the SHDL conformance suite against the current toolchain.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="check all goldens (tiers A, B, C)")
    p_run.add_argument("--filter", help="only cases whose name contains this substring")
    p_run.add_argument("--tier", choices=["A", "B", "C"], help="restrict to one tier")

    p_verify = sub.add_parser(
        "verify-oracle",
        help="re-derive trace goldens from BaseEval and lockstep-check the C library",
    )
    p_verify.add_argument("--filter", help="only cases whose name contains this substring")

    p_regen = sub.add_parser(
        "regen", help="regenerate goldens for ONE case (dry run unless --write)"
    )
    p_regen.add_argument("--case", required=True, help="case name (exactly one; no bulk regen)")
    p_regen.add_argument(
        "--write", action="store_true", help="apply the changes (default: diff only)"
    )

    sub.add_parser("list", help="list all cases")

    args = parser.parse_args(argv)
    try:
        match args.command:
            case "run":
                lines, failures = run(args.filter, args.tier)
                code = 1 if failures else 0
            case "verify-oracle":
                lines, failures = verify_oracle(args.filter)
                code = 1 if failures else 0
            case "regen":
                lines, code = regen_case(args.case, args.write)
            case "list":
                lines, code = list_cases(), 0
    except ConformanceError as exc:
        lines, code = str(exc).splitlines(), 1
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
