"""Explicit golden (re)generation — the only writer of golden artifacts.

Goldens are frozen, not regenerated casually. This module is invoked solely
through ``shdl-conformance regen --case NAME``, which:

- targets exactly ONE case (there is deliberately no bulk mode);
- is a dry run by default: it prints a reviewable diff of every change the
  current toolchain would make (full unified diff for the base, per-expect
  value changes for traces) and writes nothing;
- writes only with an explicit ``--write``, after printing the same diff.

Regeneration changes *values only*: ``expected.base.shdl`` bytes and the
``expect`` values inside traces (recomputed by
:class:`~conformance.runner.oracle.OracleSim`, never by the C library).
Stimulus shape — the op sequence — and all case metadata stay frozen.

A regen that changes any golden is a semantic change to the suite: bump the
major version and add a changelog entry in MANIFEST.json (see
conformance.md, "Versioning").
"""

from __future__ import annotations

import difflib
import json

from .oracle import OracleSim
from .schema import (
    MANIFEST_PATH,
    Case,
    ConformanceError,
    content_hash,
    load_suite,
    rel,
)
from .suite import flatten_case

_OP_KEY_ORDER = ("op", "signal", "value", "cycles")


def canonical_op(op: dict) -> dict:
    """The op with keys in canonical serialization order."""
    return {key: op[key] for key in _OP_KEY_ORDER if key in op}


def fill_trace_ops(base_text: str, ops) -> list[dict]:
    """Recompute every ``expect`` value by replaying the ops on a fresh oracle.

    The returned ops are canonically ordered copies; non-expect ops pass
    through unchanged. This is the single source of every trace golden.
    """
    oracle = OracleSim(base_text)
    filled: list[dict] = []
    for op in ops:
        op = dict(op)
        match op["op"]:
            case "reset":
                oracle.reset()
            case "poke":
                oracle.poke(op["signal"], op["value"])
            case "step":
                oracle.step(op["cycles"])
            case "expect":
                op["value"] = oracle.peek(op["signal"])
        filled.append(canonical_op(op))
    return filled


def trace_json_text(trace_data: dict) -> str:
    """Canonical on-disk form of a trace file (stable key order, LF, newline-terminated)."""
    body = {
        "trace_format": trace_data["trace_format"],
        "name": trace_data["name"],
        "tier": trace_data["tier"],
        "description": trace_data["description"],
        "provenance": trace_data["provenance"],
        "ops": [canonical_op(op) for op in trace_data["ops"]],
    }
    return json.dumps(body, indent=2) + "\n"


def _trace_data(trace) -> dict:
    return {
        "trace_format": 1,
        "name": trace.name,
        "tier": trace.tier,
        "description": trace.description,
        "provenance": trace.provenance,
        "ops": [dict(op) for op in trace.ops],
    }


def refresh_golden_hashes(changed_paths) -> list[str]:
    """Rewrite the ``golden_hashes`` entries for the just-written goldens (CNF-9).

    ``regen --write`` is the *only* sanctioned golden writer, so it is also the
    only place the drift fingerprints in MANIFEST.json are refreshed. Reading
    the manifest fresh from disk and re-serializing canonically keeps every
    untouched entry byte-stable (the manifest round-trips through
    ``json.dumps(indent=2, ensure_ascii=False)``). Returns one report line per
    refreshed fingerprint.
    """
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    hashes = manifest.setdefault("golden_hashes", {})
    lines: list[str] = []
    for path in changed_paths:
        name = rel(path)
        hashes[name] = content_hash(path)
        lines.append(f"  golden_hashes[{name}] refreshed")
    manifest["golden_hashes"] = dict(sorted(hashes.items()))
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return lines


def regen_case(case_name: str, write: bool) -> tuple[list[str], int]:
    """Diff (and with ``write=True`` apply) regenerated goldens for one case."""
    try:
        suite = load_suite()
    except ConformanceError as exc:
        return str(exc).splitlines(), 1
    try:
        case: Case = suite.case(case_name)
    except KeyError:
        names = ", ".join(c.name for c in suite.cases)
        return [f"unknown case {case_name!r}; available: {names}"], 1

    lines = [f"regen {case.name} ({'WRITE' if write else 'dry run'})", ""]
    timestamp = suite.manifest.flatten_timestamp

    try:
        new_base = flatten_case(case, timestamp)
    except Exception as exc:
        lines.append(f"flattening {rel(case.circuit)} failed: {exc}")
        return lines, 1
    old_base = case.expected_base.read_text(encoding="utf-8")

    changed: list[tuple] = []  # (path, new_text)
    if new_base == old_base:
        lines.append(f"{rel(case.expected_base)}: unchanged")
    else:
        changed.append((case.expected_base, new_base))
        lines.append(f"{rel(case.expected_base)}: CHANGED")
        lines.extend(
            line.rstrip("\n")
            for line in difflib.unified_diff(
                old_base.splitlines(keepends=True),
                new_base.splitlines(keepends=True),
                fromfile=f"{rel(case.expected_base)} (frozen)",
                tofile=f"{rel(case.expected_base)} (regenerated)",
            )
        )
    lines.append("")

    for trace in case.traces:
        trace_rel = rel(trace.path)
        try:
            filled = fill_trace_ops(new_base, trace.ops)
        except ValueError as exc:
            lines.append(f"{trace_rel}: cannot refill — {exc}")
            return lines, 1
        deltas = [
            f"  op[{i}] expect {new['signal']}: {old['value']} -> {new['value']}"
            for i, (old, new) in enumerate(zip(trace.ops, filled))
            if old["op"] == "expect" and old["value"] != new["value"]
        ]
        if not deltas:
            lines.append(f"{trace_rel}: unchanged")
            continue
        data = _trace_data(trace)
        data["ops"] = filled
        changed.append((trace.path, trace_json_text(data)))
        lines.append(f"{trace_rel}: CHANGED ({len(deltas)} expect value(s))")
        lines.extend(deltas)
    lines.append("")

    if not changed:
        lines.append("all goldens already match the current toolchain; nothing to do")
        return lines, 0
    if write:
        for path, text in changed:
            path.write_text(text, encoding="utf-8")
        lines.append(f"wrote {len(changed)} golden(s)")
        lines.extend(refresh_golden_hashes(path for path, _ in changed))
        lines.append(
            "REMINDER: a golden change is a semantic change to the suite — bump the "
            "major suite_version and add a MANIFEST.json changelog entry (conformance.md)."
        )
    else:
        lines.append(
            f"dry run: {len(changed)} golden(s) would change; nothing written "
            "(pass --write to apply)"
        )
    return lines, 0
