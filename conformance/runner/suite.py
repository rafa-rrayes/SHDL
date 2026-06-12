"""Tier execution and deterministic reporting for the conformance suite.

Three checks, mapped to the suite's tiers:

- Tier A — flattening: re-flatten ``circuit.shdl`` with the manifest's pinned
  timestamp and compare byte-for-byte against the frozen
  ``expected.base.shdl``.
- Tier B/C — simulation: compile the *frozen* ``expected.base.shdl`` (never a
  fresh flatten — Tier A already pins that equivalence separately) into a
  shared library and replay each trace against it, comparing every ``expect``
  to the stored golden value.
- verify-oracle — provenance closure: replay each trace against a fresh
  :class:`~conformance.runner.oracle.OracleSim` (goldens must be re-derivable
  from the oracle) and against oracle + C library in lockstep (the two
  implementations must agree at every observation, independent of the stored
  values).

Reports are deterministic: cases in manifest order, traces in listed order,
no wall-clock timestamps, no temporary paths. Running the suite twice yields
byte-identical output.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path

from flattener.pipeline import flatten_program
from shdlc import build_library
from shdlc.cc import lib_suffix
from shdlc.harness import STRICT_CFLAGS, Sim, load_fresh_copy, parse_with_ports

from . import executor
from .oracle import OracleSim
from .schema import Case, Suite, load_suite, rel

DIFF_LINE_LIMIT = 40


def flatten_case(case: Case, timestamp: str) -> str:
    """Flatten the case's circuit exactly as the goldens were produced."""
    return flatten_program(str(case.circuit), top=case.top, timestamp=timestamp).text


def tier_a_failures(case: Case, timestamp: str) -> list[str]:
    """Empty if the current flattener reproduces the frozen base byte-for-byte."""
    golden = case.expected_base.read_text(encoding="utf-8")
    try:
        current = flatten_case(case, timestamp)
    except Exception as exc:  # report, don't abort the suite
        return [f"flattening {rel(case.circuit)} failed: {exc}"]
    if current == golden:
        return []
    diff = list(
        difflib.unified_diff(
            golden.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=f"{rel(case.expected_base)} (golden)",
            tofile="current flattener output",
        )
    )
    shown = [line.rstrip("\n") for line in diff[:DIFF_LINE_LIMIT]]
    if len(diff) > DIFF_LINE_LIMIT:
        shown.append(f"... diff truncated ({len(diff)} lines total)")
    return ["flattened output differs from frozen golden:"] + shown


def check_trace_signals(case: Case, base_text: str) -> dict[str, list[str]]:
    """Validate every trace's signals against the frozen base's ports.

    Returns trace-path -> problem lines. Catching this up front keeps signal
    typos from masquerading as value mismatches (the C ABI reads unknown
    signals as 0 instead of failing).
    """
    ports = parse_with_ports(base_text).meta["ports"]
    inputs, outputs = set(ports["inputs"]), set(ports["outputs"])
    problems: dict[str, list[str]] = {}
    for trace in case.traces:
        lines = []
        for index, op in enumerate(trace.ops):
            if op["op"] == "poke" and op["signal"] not in inputs:
                lines.append(f"op[{index}] pokes unknown input {op['signal']!r}")
            if op["op"] == "expect" and op["signal"] not in inputs | outputs:
                lines.append(f"op[{index}] expects unknown signal {op['signal']!r}")
        if lines:
            problems[rel(trace.path)] = lines
    return problems


class CaseBuild:
    """Compiled library for one case, with fresh-instance loading per trace."""

    def __init__(self, case: Case, work_dir: Path):
        self.case = case
        self.work_dir = work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        self.base_text = case.expected_base.read_text(encoding="utf-8")
        self.lib_path = build_library(
            self.base_text,
            work_dir / f"{case.name}{lib_suffix()}",
            cflags=STRICT_CFLAGS,
        )

    def fresh_sim(self) -> Sim:
        return load_fresh_copy(self.lib_path, self.work_dir)


class Report:
    """Accumulates deterministic result lines plus pass/fail counts."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.checks = 0
        self.failures = 0

    def result(self, tier: str, case_name: str, artifact: str, problems: list[str]) -> None:
        self.checks += 1
        status = "PASS" if not problems else "FAIL"
        self.lines.append(f"{status}  {tier}  {case_name:<24} {artifact}")
        if problems:
            self.failures += 1
            self.lines.extend(f"      {line}" for line in problems)

    def skip(self, tier: str, case_name: str, artifact: str, reason: str) -> None:
        # A skip is a failure: a golden that cannot be checked is not passing.
        self.checks += 1
        self.failures += 1
        self.lines.append(f"FAIL  {tier}  {case_name:<24} {artifact}")
        self.lines.append(f"      {reason}")


def _selected(suite: Suite, name_filter: str | None) -> list[Case]:
    return [c for c in suite.cases if name_filter is None or name_filter in c.name]


def _header(suite: Suite, mode: str, selected: int) -> list[str]:
    m = suite.manifest
    return [
        f"SHDL conformance suite v{m.suite_version} — {mode}",
        f"flatten timestamp: {m.flatten_timestamp}",
        f"cases: {selected} selected of {len(suite.cases)}",
        "",
    ]


def run(name_filter: str | None = None, tier: str | None = None) -> tuple[list[str], int]:
    """``shdl-conformance run``: check goldens against the current toolchain."""
    suite = load_suite()
    cases = _selected(suite, name_filter)
    report = Report()
    work_root = Path(tempfile.mkdtemp(prefix="shdl-conformance-"))
    try:
        for case in cases:
            if "A" in case.tiers and tier in (None, "A"):
                report.result(
                    "A", case.name, "expected.base.shdl",
                    tier_a_failures(case, suite.manifest.flatten_timestamp),
                )
            trace_tiers = {t.tier for t in case.traces}
            if not (trace_tiers if tier is None else trace_tiers & {tier}):
                continue
            try:
                build = CaseBuild(case, work_root / case.name)
            except Exception as exc:
                for trace in case.traces:
                    if tier in (None, trace.tier):
                        report.skip(
                            trace.tier, case.name,
                            trace.path.relative_to(case.dir).as_posix(),
                            f"compiling {rel(case.expected_base)} failed: {exc}",
                        )
                continue
            signal_problems = check_trace_signals(case, build.base_text)
            for trace in case.traces:
                if tier not in (None, trace.tier):
                    continue
                artifact = trace.path.relative_to(case.dir).as_posix()
                bad_signals = signal_problems.get(rel(trace.path))
                if bad_signals:
                    report.result(trace.tier, case.name, artifact, bad_signals)
                    continue
                sim = build.fresh_sim()
                observations = executor.replay(trace.ops, {"lib": sim})
                report.result(
                    trace.tier, case.name, artifact,
                    executor.mismatches(observations, "lib"),
                )
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    lines = _header(suite, "run" + (f" --tier {tier}" if tier else ""), len(cases))
    lines += report.lines
    lines += [
        "",
        f"summary: {report.checks} checks, {report.failures} failure(s)",
    ]
    return lines, report.failures


def verify_oracle(name_filter: str | None = None) -> tuple[list[str], int]:
    """``shdl-conformance verify-oracle``: close the provenance triangle.

    Per trace: (1) the stored expect values must be re-derivable from a fresh
    OracleSim (goldens come from the oracle, by construction); (2) the C
    library must agree with the oracle at every observation, in lockstep,
    independent of the stored values.
    """
    suite = load_suite()
    cases = [c for c in _selected(suite, name_filter) if c.traces]
    report = Report()
    work_root = Path(tempfile.mkdtemp(prefix="shdl-conformance-"))
    try:
        for case in cases:
            try:
                build = CaseBuild(case, work_root / case.name)
            except Exception as exc:
                for trace in case.traces:
                    report.skip(
                        trace.tier, case.name,
                        trace.path.relative_to(case.dir).as_posix(),
                        f"compiling {rel(case.expected_base)} failed: {exc}",
                    )
                continue
            signal_problems = check_trace_signals(case, build.base_text)
            for trace in case.traces:
                artifact = trace.path.relative_to(case.dir).as_posix()
                bad_signals = signal_problems.get(rel(trace.path))
                if bad_signals:
                    report.result(trace.tier, case.name, artifact, bad_signals)
                    continue
                sims = {"oracle": OracleSim(build.base_text), "lib": build.fresh_sim()}
                observations = executor.replay(trace.ops, sims)
                problems = [
                    f"golden not re-derivable from oracle: {line}"
                    for line in executor.mismatches(observations, "oracle")
                ] + [
                    f"lockstep divergence: {line}"
                    for line in executor.disagreements(observations, "oracle", "lib")
                ]
                report.result(trace.tier, case.name, artifact, problems)
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    lines = _header(suite, "verify-oracle", len(cases))
    lines += report.lines
    lines += [
        "",
        f"summary: {report.checks} checks, {report.failures} failure(s)",
    ]
    return lines, report.failures


def list_cases() -> list[str]:
    """``shdl-conformance list``: one line per case."""
    suite = load_suite()
    lines = _header(suite, "list", len(suite.cases))
    for case in suite.cases:
        tiers = "".join(case.tiers)
        lines.append(
            f"{case.name:<24} tiers={tiers:<3} traces={len(case.traces):<2} {case.title}"
        )
    return lines
