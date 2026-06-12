"""Loading and validation of conformance-suite artifacts.

Validation is collected, not fail-fast: every problem found is gathered and
raised as one :class:`ConformanceError` whose message names each offending
artifact by repo-relative path. A deleted, de-listed, or corrupted golden
therefore always fails loudly *by name*.

The schemas validated here (manifest, case.json, trace files) are documented
for third parties in ``conformance/conformance.md``; this module is the
executable form of that document.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # conformance/
CASES_DIR = ROOT / "cases"
MANIFEST_PATH = ROOT / "MANIFEST.json"
REPO = ROOT.parent

MANIFEST_FORMAT = 1
CASE_FORMAT = 1
TRACE_FORMAT = 1
TIERS = ("A", "B", "C")
TRACE_TIERS = ("B", "C")
OPS = ("reset", "poke", "step", "expect")
MAX_VALUE = (1 << 64) - 1  # ports are at most 64 bits wide (base_shdl.md)
MAX_CYCLES = 1_000_000  # sanity bound; real traces use a few dozen


class ConformanceError(Exception):
    """Suite integrity violation; the message lists every problem found."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__(
            "conformance suite integrity check failed "
            f"({len(self.problems)} problem(s)):\n"
            + "\n".join(f"  - {p}" for p in self.problems)
        )


def rel(path: Path) -> str:
    """Repo-relative POSIX path: the stable name an artifact is reported by."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def content_hash(path: Path) -> str:
    """SHA-256 hex of a golden's raw bytes — its drift fingerprint (CNF-9)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def golden_paths(case: Case) -> tuple[Path, ...]:
    """The drift-fingerprinted goldens of a case: its base plus every trace.

    These are exactly the artifacts ``regen`` may rewrite — the files whose
    bytes are a semantic golden. ``case.json`` (frozen metadata/stimulus) and
    the ``*.shdl`` sources are *not* fingerprinted: a source edit that changes
    the flattened output is caught by Tier A byte-equality, and the manifest
    hash of ``expected.base.shdl`` would change with it.
    """
    return (case.expected_base,) + tuple(t.path for t in case.traces)


@dataclass(frozen=True)
class Trace:
    path: Path
    name: str
    tier: str
    description: str
    provenance: str
    ops: tuple[dict, ...]


@dataclass(frozen=True)
class Case:
    dir: Path
    name: str
    title: str
    description: str
    tiers: tuple[str, ...]
    circuit: Path
    sources: tuple[Path, ...]
    expected_base: Path
    features: tuple[str, ...]
    provenance: dict
    traces: tuple[Trace, ...]
    top: str | None


@dataclass(frozen=True)
class Manifest:
    path: Path
    suite_version: str
    flatten_timestamp: str
    case_names: tuple[str, ...]
    required_features: dict[str, str]
    changelog: tuple[dict, ...]
    golden_hashes: dict[str, str]


@dataclass(frozen=True)
class Suite:
    manifest: Manifest
    cases: tuple[Case, ...]

    def case(self, name: str) -> Case:
        for c in self.cases:
            if c.name == name:
                return c
        raise KeyError(name)


# --------------------------------------------------------------------------
# low-level helpers
# --------------------------------------------------------------------------


def _read_json(path: Path, problems: list[str]) -> dict | None:
    if not path.is_file():
        problems.append(f"missing golden artifact: {rel(path)}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append(f"unreadable JSON artifact {rel(path)}: {exc}")
        return None
    if not isinstance(data, dict):
        problems.append(f"{rel(path)}: top level must be a JSON object")
        return None
    return data


def _str_field(data: dict, key: str, where: str, problems: list[str]) -> str | None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{where}: field {key!r} must be a non-empty string")
        return None
    return value


def _int_in_range(value, lo: int, hi: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi


# --------------------------------------------------------------------------
# trace files
# --------------------------------------------------------------------------


def _validate_op(op, index: int, where: str, problems: list[str]) -> None:
    if not isinstance(op, dict):
        problems.append(f"{where}: ops[{index}] must be a JSON object")
        return
    kind = op.get("op")
    if kind not in OPS:
        problems.append(
            f"{where}: ops[{index}] has unknown op {kind!r} (one of {', '.join(OPS)})"
        )
        return
    expected_keys = {
        "reset": {"op"},
        "poke": {"op", "signal", "value"},
        "step": {"op", "cycles"},
        "expect": {"op", "signal", "value"},
    }[kind]
    if set(op) != expected_keys:
        problems.append(
            f"{where}: ops[{index}] ({kind}) must have exactly the keys "
            f"{sorted(expected_keys)}, got {sorted(op)}"
        )
        return
    if kind in ("poke", "expect"):
        if not isinstance(op["signal"], str) or not op["signal"]:
            problems.append(f"{where}: ops[{index}] ({kind}) signal must be a non-empty string")
        if not _int_in_range(op["value"], 0, MAX_VALUE):
            problems.append(
                f"{where}: ops[{index}] ({kind}) value must be an integer in [0, 2^64)"
            )
    if kind == "step" and not _int_in_range(op["cycles"], 0, MAX_CYCLES):
        problems.append(
            f"{where}: ops[{index}] (step) cycles must be an integer in [0, {MAX_CYCLES}]"
        )


def load_trace(path: Path, case_tiers: tuple[str, ...], problems: list[str]) -> Trace | None:
    where = rel(path)
    data = _read_json(path, problems)
    if data is None:
        return None
    before = len(problems)
    if data.get("trace_format") != TRACE_FORMAT:
        problems.append(f"{where}: trace_format must be {TRACE_FORMAT}")
    name = _str_field(data, "name", where, problems)
    tier = data.get("tier")
    if tier not in TRACE_TIERS:
        problems.append(f"{where}: tier must be one of {TRACE_TIERS}, got {tier!r}")
    elif tier not in case_tiers:
        problems.append(f"{where}: tier {tier!r} is not declared in the case's tiers")
    description = _str_field(data, "description", where, problems)
    provenance = _str_field(data, "provenance", where, problems)
    ops = data.get("ops")
    if not isinstance(ops, list) or not ops:
        problems.append(f"{where}: ops must be a non-empty list")
        ops = []
    else:
        if ops[0] != {"op": "reset"}:
            problems.append(f"{where}: ops[0] must be {{\"op\": \"reset\"}}")
        for i, op in enumerate(ops):
            _validate_op(op, i, where, problems)
    if len(problems) > before:
        return None
    return Trace(
        path=path,
        name=name,
        tier=tier,
        description=description,
        provenance=provenance,
        ops=tuple(ops),
    )


# --------------------------------------------------------------------------
# case directories
# --------------------------------------------------------------------------


def load_case(case_dir: Path, required_features: dict[str, str] | None, problems: list[str]) -> Case | None:
    case_json = case_dir / "case.json"
    where = rel(case_json)
    data = _read_json(case_json, problems)
    if data is None:
        return None
    before = len(problems)

    if data.get("case_format") != CASE_FORMAT:
        problems.append(f"{where}: case_format must be {CASE_FORMAT}")
    name = _str_field(data, "name", where, problems)
    if name is not None and name != case_dir.name:
        problems.append(f"{where}: name {name!r} does not match directory {case_dir.name!r}")
    title = _str_field(data, "title", where, problems)
    description = _str_field(data, "description", where, problems)

    tiers = data.get("tiers")
    if (
        not isinstance(tiers, list)
        or not tiers
        or len(set(tiers)) != len(tiers)
        or any(t not in TIERS for t in tiers)
    ):
        problems.append(f"{where}: tiers must be a non-empty unique subset of {list(TIERS)}")
        tiers = []

    top = data.get("top")
    if top is not None and (not isinstance(top, str) or not top):
        problems.append(f"{where}: top must be null or a non-empty string")

    expected_name = _str_field(data, "expected_base", where, problems)
    expected_base = case_dir / (expected_name or "expected.base.shdl")
    if expected_name is not None and not expected_base.is_file():
        problems.append(f"missing golden artifact: {rel(expected_base)} (listed in {where})")

    # Sources: the case must be self-contained, and the listing must match the
    # directory exactly in both directions so a deleted or stray source file
    # is always reported by name.
    sources = data.get("sources")
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        problems.append(f"{where}: sources must be a list of file names")
        sources = []
    on_disk = sorted(
        p.name for p in case_dir.glob("*.shdl") if p.name != expected_base.name
    )
    if sources and sorted(sources) != sources:
        problems.append(f"{where}: sources must be sorted")
    for missing in sorted(set(sources) - set(on_disk)):
        problems.append(f"missing golden artifact: {rel(case_dir / missing)} (listed in {where})")
    for stray in sorted(set(on_disk) - set(sources)):
        problems.append(f"{where}: source file {stray!r} on disk but not listed in sources")

    circuit_name = _str_field(data, "circuit", where, problems)
    if circuit_name is not None and circuit_name not in sources:
        problems.append(f"{where}: circuit {circuit_name!r} must be listed in sources")

    features = data.get("features")
    if not isinstance(features, list) or not features or not all(isinstance(f, str) for f in features):
        problems.append(f"{where}: features must be a non-empty list of strings")
        features = []
    if required_features is not None:
        for feature in features:
            if feature not in required_features:
                problems.append(
                    f"{where}: unknown feature {feature!r} "
                    "(not in MANIFEST.json required_features)"
                )

    provenance = data.get("provenance")
    if not isinstance(provenance, dict):
        problems.append(f"{where}: provenance must be an object")
        provenance = {}
    else:
        for key in ("expected_base", "traces"):
            if not isinstance(provenance.get(key), str) or not provenance[key].strip():
                problems.append(f"{where}: provenance.{key} must be a non-empty string")

    # Trace listing, also bijective with the traces/ directory.
    trace_names = data.get("traces")
    if not isinstance(trace_names, list) or not all(isinstance(t, str) for t in trace_names):
        problems.append(f"{where}: traces must be a list of paths relative to the case")
        trace_names = []
    needs_traces = bool(set(tiers) & set(TRACE_TIERS))
    if needs_traces and not trace_names:
        problems.append(f"{where}: tiers {tiers} require at least one trace")
    if not needs_traces and trace_names:
        problems.append(f"{where}: traces listed but no B/C tier declared")
    traces_on_disk = sorted(p.relative_to(case_dir).as_posix() for p in case_dir.glob("traces/*.json"))
    if trace_names and sorted(trace_names) != trace_names:
        problems.append(f"{where}: traces must be sorted")
    for missing in sorted(set(trace_names) - set(traces_on_disk)):
        problems.append(f"missing golden artifact: {rel(case_dir / missing)} (listed in {where})")
    for stray in sorted(set(traces_on_disk) - set(trace_names)):
        problems.append(f"{where}: trace file {stray!r} on disk but not listed in traces")

    traces = []
    for trace_name in trace_names:
        trace_path = case_dir / trace_name
        if trace_path.is_file():
            trace = load_trace(trace_path, tuple(tiers), problems)
            if trace is not None:
                traces.append(trace)

    if len(problems) > before:
        return None
    return Case(
        dir=case_dir,
        name=name,
        title=title,
        description=description,
        tiers=tuple(tiers),
        circuit=case_dir / circuit_name,
        sources=tuple(case_dir / s for s in sources),
        expected_base=expected_base,
        features=tuple(features),
        provenance=provenance,
        traces=tuple(traces),
        top=top,
    )


# --------------------------------------------------------------------------
# manifest + whole-suite loading
# --------------------------------------------------------------------------


def load_manifest(problems: list[str]) -> Manifest | None:
    where = rel(MANIFEST_PATH)
    data = _read_json(MANIFEST_PATH, problems)
    if data is None:
        return None
    before = len(problems)
    if data.get("manifest_format") != MANIFEST_FORMAT:
        problems.append(f"{where}: manifest_format must be {MANIFEST_FORMAT}")
    suite_version = _str_field(data, "suite_version", where, problems)
    flatten_timestamp = _str_field(data, "flatten_timestamp", where, problems)
    case_names = data.get("cases")
    if (
        not isinstance(case_names, list)
        or not case_names
        or not all(isinstance(c, str) for c in case_names)
        or sorted(set(case_names)) != case_names
    ):
        problems.append(f"{where}: cases must be a sorted list of unique case names")
        case_names = []
    required = data.get("required_features")
    if not isinstance(required, dict) or not required or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in required.items()
    ):
        problems.append(f"{where}: required_features must be a non-empty object of str -> str")
        required = {}
    changelog = data.get("changelog")
    if not isinstance(changelog, list) or not changelog:
        problems.append(f"{where}: changelog must be a non-empty list")
        changelog = []
    golden_hashes = data.get("golden_hashes")
    if not isinstance(golden_hashes, dict) or not golden_hashes or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in golden_hashes.items()
    ):
        problems.append(
            f"{where}: golden_hashes must be a non-empty object of "
            "repo-relative-path -> sha256 hex (refresh it via 'shdl-conformance regen --write')"
        )
        golden_hashes = {}
    if len(problems) > before:
        return None
    return Manifest(
        path=MANIFEST_PATH,
        suite_version=suite_version,
        flatten_timestamp=flatten_timestamp,
        case_names=tuple(case_names),
        required_features=dict(required),
        changelog=tuple(changelog),
        golden_hashes=dict(golden_hashes),
    )


def load_suite() -> Suite:
    """Load and validate the whole corpus; raise ConformanceError on any problem.

    Checks, in order: manifest schema, manifest <-> disk agreement (both
    directions), every case (schema + per-artifact existence, both
    directions), every trace, and finally feature coverage: every key of
    ``required_features`` must be claimed by at least one case.
    """
    problems: list[str] = []
    manifest = load_manifest(problems)
    if manifest is None:
        raise ConformanceError(problems)

    if not CASES_DIR.is_dir():
        problems.append(f"missing cases directory: {rel(CASES_DIR)}")
        raise ConformanceError(problems)
    dirs_on_disk = sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())
    for missing in sorted(set(manifest.case_names) - set(dirs_on_disk)):
        problems.append(
            f"missing golden artifact: case directory {rel(CASES_DIR / missing)} "
            f"(listed in {rel(MANIFEST_PATH)})"
        )
    for stray in sorted(set(dirs_on_disk) - set(manifest.case_names)):
        problems.append(
            f"{rel(MANIFEST_PATH)}: case directory {stray!r} on disk but not listed in cases"
        )

    cases = []
    for case_name in manifest.case_names:
        case_dir = CASES_DIR / case_name
        if case_dir.is_dir():
            case = load_case(case_dir, manifest.required_features, problems)
            if case is not None:
                cases.append(case)

    covered: set[str] = set()
    for case in cases:
        covered.update(case.features)
    if not problems:  # coverage is only meaningful over a structurally valid corpus
        for uncovered in sorted(set(manifest.required_features) - covered):
            problems.append(
                f"feature coverage gap: required feature {uncovered!r} "
                "is not claimed by any case"
            )

    # Mechanical drift enforcement (CNF-9): every golden byte is fingerprinted
    # in MANIFEST.json. A changed golden whose hash was not deliberately
    # refreshed (via 'shdl-conformance regen --write', which also forces the
    # major-version-bump reminder) fails here loudly, by name — closing the
    # coordinated-regen loophole that the live oracle checks cannot see. Only
    # meaningful over a structurally valid corpus (paths must resolve first).
    if not problems:
        actual: dict[str, str] = {}
        for case in cases:
            for path in golden_paths(case):
                actual[rel(path)] = content_hash(path)
        listed = manifest.golden_hashes
        for name in sorted(set(actual) & set(listed)):
            if actual[name] != listed[name]:
                problems.append(
                    f"golden content drift: {name} hash {actual[name]} does not "
                    f"match MANIFEST.json golden_hashes {listed[name]} — a golden "
                    "changed without a deliberate manifest update; regenerate via "
                    "'shdl-conformance regen --case <name> --write' (bump suite_version)"
                )
        for missing in sorted(set(actual) - set(listed)):
            problems.append(
                f"golden content drift: {missing} has no entry in MANIFEST.json "
                "golden_hashes (refresh hashes via 'shdl-conformance regen --write')"
            )
        for stray in sorted(set(listed) - set(actual)):
            problems.append(
                f"golden content drift: MANIFEST.json golden_hashes lists {stray} "
                "which is not a golden of any case"
            )

    if problems:
        raise ConformanceError(problems)
    return Suite(manifest=manifest, cases=tuple(cases))
