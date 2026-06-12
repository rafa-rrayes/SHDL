"""Pytest face of the conformance suite (conformance/conformance.md §11).

Same checks as ``shdl-conformance run`` + ``verify-oracle``, as individual
test items:

- one corpus-integrity test (any missing/corrupt/de-listed golden or
  coverage gap fails it, naming every artifact by repo-relative path);
- one Tier A test per case: the current flattener must reproduce the frozen
  ``expected.base.shdl`` byte-for-byte;
- one test per trace: the compiled C library must match every golden expect
  value, the goldens must be re-derivable from the reference oracle
  (provenance closure), and oracle and library must agree in lockstep.

Parametrization lists are read from MANIFEST.json / case.json with plain
``json`` at collection time (no validation, so a broken corpus still
collects); full validation happens once in the session-scoped ``suite``
fixture, so any integrity problem fails the integrity test directly and
errors every dependent test with the same named-artifact message.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conformance.runner import executor, gen, schema
from conformance.runner.oracle import OracleSim
from conformance.runner.schema import (
    CASES_DIR,
    MANIFEST_PATH,
    ConformanceError,
    content_hash,
    load_suite,
    rel,
)
from conformance.runner.suite import CaseBuild, check_trace_signals, tier_a_failures


def _collection_params() -> tuple[list[str], list[tuple[str, str]]]:
    """(tier A case names, (case, trace-relpath) pairs) from the raw JSON.

    Best-effort: unreadable files just shrink the lists — the integrity test
    is the authority on corpus health and will name the broken artifact.
    """
    tier_a: list[str] = []
    traces: list[tuple[str, str]] = []
    try:
        names = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["cases"]
    except Exception:
        return [], []
    for name in names:
        try:
            data = json.loads((CASES_DIR / name / "case.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if "A" in data.get("tiers", []):
            tier_a.append(name)
        for trace_rel in data.get("traces", []):
            traces.append((name, trace_rel))
    return tier_a, traces


TIER_A_CASES, TRACE_PARAMS = _collection_params()


@pytest.fixture(scope="session")
def suite():
    return load_suite()  # raises ConformanceError naming every problem


@pytest.fixture(scope="session")
def case_builds(suite, tmp_path_factory):
    """Lazy per-case compile cache: each frozen base is built at most once."""
    root = tmp_path_factory.mktemp("conformance-builds")
    cache: dict[str, CaseBuild] = {}

    def get(case_name: str) -> CaseBuild:
        if case_name not in cache:
            cache[case_name] = CaseBuild(suite.case(case_name), root / case_name)
        return cache[case_name]

    return get


def test_corpus_integrity():
    """Schema, manifest<->disk and case<->disk bijections, feature coverage."""
    load_suite()


@pytest.mark.parametrize("case_name", TIER_A_CASES)
def test_tier_a_flattening(case_name, suite):
    case = suite.case(case_name)
    failures = tier_a_failures(case, suite.manifest.flatten_timestamp)
    assert failures == [], "\n".join(failures)


@pytest.mark.parametrize(
    ("case_name", "trace_rel"),
    TRACE_PARAMS,
    ids=[f"{c}:{t}" for c, t in TRACE_PARAMS],
)
def test_trace(case_name, trace_rel, suite, case_builds):
    case = suite.case(case_name)
    build = case_builds(case_name)
    trace = next(t for t in case.traces if t.path == case.dir / trace_rel)

    bad_signals = check_trace_signals(case, build.base_text).get(rel(trace.path), [])
    assert bad_signals == [], "\n".join(bad_signals)

    sims = {"oracle": OracleSim(build.base_text), "lib": build.fresh_sim()}
    observations = executor.replay(trace.ops, sims)
    problems = (
        executor.mismatches(observations, "lib")  # C library vs frozen goldens
        + [
            f"golden not re-derivable from oracle: {line}"
            for line in executor.mismatches(observations, "oracle")
        ]
        + [
            f"lockstep divergence: {line}"
            for line in executor.disagreements(observations, "oracle", "lib")
        ]
    )
    assert problems == [], "\n".join(problems)


def test_collection_saw_the_corpus():
    """Guard against silently green runs if collection-time reads ever break."""
    # Minimums track the corpus size so silent loss fails loudly; raise them
    # whenever the corpus grows (suite v1.1.0: 38 cases / 40 traces, CNF-4).
    assert len(TIER_A_CASES) >= 38
    assert len(TRACE_PARAMS) >= 40


# ==========================================================================
# Self-tests for the runner itself: integrity checker (CNF-6), regen tooling
# (CNF-7), report determinism + CLI surface (CNF-8), and the mechanical drift
# fence (CNF-9). These prove the *checker* is honest — that a corrupted corpus,
# a misbehaving regen, a nondeterministic report, or a silently mutated golden
# actually fails — which the healthy-corpus run above can never demonstrate.
#
# GROUND RULE: the real corpus is NEVER mutated. Every negative test runs
# against a throwaway COPY in tmp_path; the path globals of ``schema``/``gen``
# are monkeypatched at the copy (and restored by the fixture).
# ==========================================================================

_REAL_CONFORMANCE = Path(schema.__file__).resolve().parents[1]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A throwaway corpus copy under ``tmp_path``; the real corpus is untouched.

    Yields the sandbox ``conformance/`` directory. ``schema``/``gen`` path
    globals point into it for the duration of the test, so ``load_suite`` and
    ``regen_case`` operate on the copy and ``rel(...)`` reports ``conformance/``
    paths relative to the sandbox repo root.
    """
    repo = tmp_path / "repo"
    conf = repo / "conformance"
    shutil.copytree(_REAL_CONFORMANCE, conf)
    monkeypatch.setattr(schema, "ROOT", conf)
    monkeypatch.setattr(schema, "CASES_DIR", conf / "cases")
    monkeypatch.setattr(schema, "MANIFEST_PATH", conf / "MANIFEST.json")
    monkeypatch.setattr(schema, "REPO", repo)
    # gen.py imported MANIFEST_PATH by value at module load — repoint that too.
    monkeypatch.setattr(gen, "MANIFEST_PATH", conf / "MANIFEST.json")
    return conf


def _read_manifest(conf: Path) -> dict:
    return json.loads((conf / "MANIFEST.json").read_text(encoding="utf-8"))


def _write_manifest(conf: Path, data: dict) -> None:
    (conf / "MANIFEST.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _refresh_all_hashes(conf: Path) -> None:
    """Recompute every golden_hashes entry from disk (after a structural edit),
    so a test exercising a non-hash rejection isn't shadowed by the drift fence."""
    data = _read_manifest(conf)
    hashes = {}
    for case_dir in sorted((conf / "cases").iterdir()):
        if not case_dir.is_dir():
            continue
        goldens = [case_dir / "expected.base.shdl"] + sorted(case_dir.glob("traces/*.json"))
        for p in goldens:
            if p.is_file():
                key = p.resolve().relative_to(conf.parent).as_posix()
                hashes[key] = content_hash(p)
    data["golden_hashes"] = dict(sorted(hashes.items()))
    _write_manifest(conf, data)


def _expect_problem(substr: str) -> str:
    with pytest.raises(ConformanceError) as exc:
        load_suite()
    msg = str(exc.value)
    assert substr in msg, f"expected {substr!r} in:\n{msg}"
    return msg


def test_sandbox_copy_is_healthy(sandbox):
    # CNF-6 baseline: an untouched copy passes, so every failure below is the
    # injected corruption talking, not a copy artifact.
    assert len(load_suite().cases) >= 38


# ----- CNF-6: corrupted-corpus matrix -------------------------------------


def test_cnf6_missing_artifact(sandbox):
    # CNF-6: a listed base golden deleted -> named missing artifact.
    (sandbox / "cases" / "single_gate" / "expected.base.shdl").unlink()
    _expect_problem("missing golden artifact: conformance/cases/single_gate/expected.base.shdl")


def test_cnf6_missing_trace_artifact(sandbox):
    # CNF-6: a listed trace deleted -> named missing artifact.
    (sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json").unlink()
    _expect_problem(
        "missing golden artifact: conformance/cases/single_gate/traces/cycle_semantics.json"
    )


def test_cnf6_stray_source_file(sandbox):
    # CNF-6: an unlisted .shdl on disk -> named stray source.
    (sandbox / "cases" / "single_gate" / "extra.shdl").write_text("component X() -> () {}\n")
    msg = _expect_problem("source file 'extra.shdl' on disk but not listed in sources")
    assert "single_gate" in msg


def test_cnf6_stray_trace_file(sandbox):
    # CNF-6: an unlisted traces/*.json on disk -> named stray trace.
    (sandbox / "cases" / "single_gate" / "traces" / "ghost.json").write_text("{}\n")
    _expect_problem("trace file 'traces/ghost.json' on disk but not listed in traces")


def test_cnf6_delisted_case_directory(sandbox):
    # CNF-6: a case dir on disk dropped from the manifest -> named stray dir.
    data = _read_manifest(sandbox)
    data["cases"] = [c for c in data["cases"] if c != "single_gate"]
    _write_manifest(sandbox, data)
    _expect_problem("case directory 'single_gate' on disk but not listed in cases")


def test_cnf6_manifest_lists_missing_case_directory(sandbox):
    # CNF-6: a case named in the manifest with no directory -> named missing dir.
    shutil.rmtree(sandbox / "cases" / "single_gate")
    _expect_problem("missing golden artifact: case directory conformance/cases/single_gate")


def test_cnf6_unsorted_cases_list(sandbox):
    # CNF-6: manifest cases out of order -> rejected.
    data = _read_manifest(sandbox)
    data["cases"] = list(reversed(data["cases"]))
    _write_manifest(sandbox, data)
    _expect_problem("cases must be a sorted list of unique case names")


def test_cnf6_unsorted_sources_list(sandbox):
    # CNF-6: a case.json sources list out of order -> rejected.
    case_json = sandbox / "cases" / "diamond" / "case.json"
    data = json.loads(case_json.read_text())
    data["sources"] = list(reversed(data["sources"]))
    case_json.write_text(json.dumps(data, indent=2) + "\n")
    _expect_problem("sources must be sorted")


def test_cnf6_unsorted_traces_list(sandbox):
    # CNF-6: a case.json traces list out of order -> rejected.
    case_json = sandbox / "cases" / "adder8_ripple" / "case.json"
    data = json.loads(case_json.read_text())
    assert len(data["traces"]) >= 2
    data["traces"] = list(reversed(data["traces"]))
    case_json.write_text(json.dumps(data, indent=2) + "\n")
    _expect_problem("traces must be sorted")


def test_cnf6_wrong_manifest_format(sandbox):
    # CNF-6: unknown manifest_format -> rejected.
    data = _read_manifest(sandbox)
    data["manifest_format"] = 99
    _write_manifest(sandbox, data)
    _expect_problem("manifest_format must be 1")


def test_cnf6_wrong_case_format(sandbox):
    # CNF-6: unknown case_format -> rejected.
    case_json = sandbox / "cases" / "single_gate" / "case.json"
    data = json.loads(case_json.read_text())
    data["case_format"] = 7
    case_json.write_text(json.dumps(data, indent=2) + "\n")
    _expect_problem("case_format must be 1")


def test_cnf6_wrong_trace_format(sandbox):
    # CNF-6: unknown trace_format -> rejected.
    trace = sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json"
    data = json.loads(trace.read_text())
    data["trace_format"] = 2
    trace.write_text(json.dumps(data, indent=2) + "\n")
    _refresh_all_hashes(sandbox)
    _expect_problem("trace_format must be 1")


def test_cnf6_ops0_not_reset(sandbox):
    # CNF-6: ops[0] not {"op":"reset"} -> rejected (replay must not depend on
    # prior state).
    trace = sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json"
    data = json.loads(trace.read_text())
    data["ops"][0] = {"op": "step", "cycles": 1}
    trace.write_text(json.dumps(data, indent=2) + "\n")
    _refresh_all_hashes(sandbox)
    _expect_problem('ops[0] must be {"op": "reset"}')


def test_cnf6_bad_op_keys(sandbox):
    # CNF-6: an op carrying the wrong key set -> rejected.
    trace = sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json"
    data = json.loads(trace.read_text())
    data["ops"][1] = {"op": "step", "cycles": 1, "bogus": 5}
    trace.write_text(json.dumps(data, indent=2) + "\n")
    _refresh_all_hashes(sandbox)
    _expect_problem("must have exactly the keys")


def test_cnf6_unknown_op(sandbox):
    # CNF-6: an op with an unknown op name -> rejected.
    trace = sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json"
    data = json.loads(trace.read_text())
    data["ops"][1] = {"op": "frobnicate"}
    trace.write_text(json.dumps(data, indent=2) + "\n")
    _refresh_all_hashes(sandbox)
    _expect_problem("unknown op 'frobnicate'")


def test_cnf6_value_out_of_range(sandbox):
    # CNF-6: a poke/expect value >= 2^64 -> rejected.
    trace = sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json"
    data = json.loads(trace.read_text())
    for op in data["ops"]:
        if op["op"] == "expect":
            op["value"] = 1 << 64
            break
    trace.write_text(json.dumps(data, indent=2) + "\n")
    _refresh_all_hashes(sandbox)
    _expect_problem("value must be an integer in [0, 2^64)")


def test_cnf6_step_cycles_out_of_range(sandbox):
    # CNF-6: a step cycles count past the sanity bound -> rejected.
    trace = sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json"
    data = json.loads(trace.read_text())
    for op in data["ops"]:
        if op["op"] == "step":
            op["cycles"] = schema.MAX_CYCLES + 1
            break
    trace.write_text(json.dumps(data, indent=2) + "\n")
    _refresh_all_hashes(sandbox)
    _expect_problem("cycles must be an integer in")


def test_cnf6_unknown_feature(sandbox):
    # CNF-6: a case.json feature not in required_features -> rejected by name.
    case_json = sandbox / "cases" / "single_gate" / "case.json"
    data = json.loads(case_json.read_text())
    data["features"] = data["features"] + ["lang:does-not-exist"]
    case_json.write_text(json.dumps(data, indent=2) + "\n")
    _expect_problem("unknown feature 'lang:does-not-exist'")


def test_cnf6_feature_coverage_gap(sandbox):
    # CNF-6: a required feature no case claims -> coverage gap, named.
    data = _read_manifest(sandbox)
    data["required_features"]["lang:orphan-feature"] = "claimed by nobody"
    _write_manifest(sandbox, data)
    _expect_problem("feature coverage gap: required feature 'lang:orphan-feature'")


def test_cnf6_empty_provenance(sandbox):
    # CNF-6: an empty provenance string -> rejected (principle 1).
    case_json = sandbox / "cases" / "single_gate" / "case.json"
    data = json.loads(case_json.read_text())
    data["provenance"]["traces"] = "   "
    case_json.write_text(json.dumps(data, indent=2) + "\n")
    _expect_problem("provenance.traces must be a non-empty string")


def test_cnf6_unknown_signal_trace_via_check_trace_signals(sandbox):
    # CNF-6: a trace naming a signal not in the frozen base's ports -> flagged by
    # check_trace_signals (the C ABI reads unknown signals as 0, so the validator
    # catches them before they masquerade as value mismatches).
    suite = load_suite()
    case = suite.case("single_gate")
    base_text = case.expected_base.read_text(encoding="utf-8")
    trace0 = case.traces[0]
    bogus_trace = trace0.__class__(
        **{
            **trace0.__dict__,
            "ops": tuple(
                {"op": "expect", "signal": "NOPE", "value": 0} if op["op"] == "expect" else op
                for op in trace0.ops
            ),
        }
    )
    bogus_case = case.__class__(**{**case.__dict__, "traces": (bogus_trace,)})
    problems = check_trace_signals(bogus_case, base_text)
    flat = [line for lines in problems.values() for line in lines]
    assert any("unknown signal 'NOPE'" in line for line in flat), flat


# ----- CNF-9: mechanical drift fence --------------------------------------


def test_cnf9_changed_golden_byte_fails(sandbox):
    # CNF-9: a base golden byte changed without refreshing its hash fails loudly,
    # naming the artifact (the coordinated-regen loophole closed).
    base = sandbox / "cases" / "single_gate" / "expected.base.shdl"
    base.write_text(base.read_text(encoding="utf-8") + "\n# drifted\n", encoding="utf-8")
    _expect_problem("golden content drift: conformance/cases/single_gate/expected.base.shdl")


def test_cnf9_changed_trace_byte_fails(sandbox):
    # CNF-9: a trace golden value mutated without a hash refresh fails.
    trace = sandbox / "cases" / "single_gate" / "traces" / "cycle_semantics.json"
    data = json.loads(trace.read_text())
    for op in data["ops"]:
        if op["op"] == "expect":
            op["value"] = (op["value"] + 1) % 2
            break
    trace.write_text(json.dumps(data, indent=2) + "\n")
    _expect_problem("golden content drift")


def test_cnf9_missing_hash_entry_fails(sandbox):
    # CNF-9: a golden with no golden_hashes entry fails (map must cover all).
    data = _read_manifest(sandbox)
    del data["golden_hashes"]["conformance/cases/single_gate/expected.base.shdl"]
    _write_manifest(sandbox, data)
    _expect_problem(
        "golden content drift: conformance/cases/single_gate/expected.base.shdl has no entry"
    )


def test_cnf9_stray_hash_entry_fails(sandbox):
    # CNF-9: a golden_hashes entry with no matching golden fails.
    data = _read_manifest(sandbox)
    data["golden_hashes"]["conformance/cases/ghost/expected.base.shdl"] = "0" * 64
    _write_manifest(sandbox, data)
    _expect_problem(
        "golden content drift: MANIFEST.json golden_hashes lists "
        "conformance/cases/ghost/expected.base.shdl"
    )


def test_cnf9_missing_golden_hashes_field(sandbox):
    # CNF-9: the field itself absent -> rejected (the fence is mandatory).
    data = _read_manifest(sandbox)
    del data["golden_hashes"]
    _write_manifest(sandbox, data)
    _expect_problem("golden_hashes must be a non-empty object")


def test_cnf9_real_manifest_hashes_match_disk():
    # CNF-9: the *committed* manifest's hashes match the *real* corpus on disk —
    # the suite ships drift-free (no sandbox; reads the real corpus).
    suite = load_suite()
    for case in suite.cases:
        for path in schema.golden_paths(case):
            name = rel(path)
            assert name in suite.manifest.golden_hashes
            assert content_hash(path) == suite.manifest.golden_hashes[name]


# ----- CNF-7: regen tooling contract (over the sandbox) -------------------


def _sandbox_snapshot(conf: Path) -> dict[str, bytes]:
    return {
        p.relative_to(conf).as_posix(): p.read_bytes()
        for p in sorted(conf.rglob("*"))
        if p.is_file()
    }


def test_cnf7_dry_run_writes_nothing(sandbox):
    # CNF-7: a dry run over an already-matching golden writes nothing.
    before = _sandbox_snapshot(sandbox)
    lines, code = gen.regen_case("single_gate", write=False)
    assert code == 0
    assert _sandbox_snapshot(sandbox) == before, "dry run must not write any file"
    assert any("nothing" in ln.lower() or "unchanged" in ln.lower() for ln in lines)


def test_cnf7_dry_run_shows_full_diff(sandbox):
    # CNF-7: when the on-disk base no longer matches a fresh flatten, the dry run
    # prints a full unified diff and still writes nothing.
    base = sandbox / "cases" / "single_gate" / "expected.base.shdl"
    base.write_text(base.read_text(encoding="utf-8") + "# tamper\n", encoding="utf-8")
    _refresh_all_hashes(sandbox)  # get past the drift fence to reach the regen diff
    before = _sandbox_snapshot(sandbox)
    lines, code = gen.regen_case("single_gate", write=False)
    assert _sandbox_snapshot(sandbox) == before, "dry run must not write even with a pending change"
    text = "\n".join(lines)
    assert "CHANGED" in text
    assert "---" in text and "+++" in text, "a unified diff header must be shown"


def test_cnf7_write_applies_only_golden_bytes(sandbox):
    # CNF-7: --write rewrites exactly the regenerated golden, refreshes its hash,
    # and touches nothing else (stimulus, metadata, descriptions frozen).
    case_dir = sandbox / "cases" / "single_gate"
    base = case_dir / "expected.base.shdl"
    case_json = case_dir / "case.json"
    trace = case_dir / "traces" / "cycle_semantics.json"

    case_json_before = case_json.read_bytes()
    trace_before = json.loads(trace.read_text())

    base.write_text(base.read_text(encoding="utf-8") + "# tamper\n", encoding="utf-8")
    _refresh_all_hashes(sandbox)
    lines, code = gen.regen_case("single_gate", write=True)
    assert code == 0
    assert "# tamper" not in base.read_text(encoding="utf-8"), "base must be rewritten clean"

    assert case_json.read_bytes() == case_json_before, "case.json must be frozen"
    trace_now = json.loads(trace.read_text())
    assert [op for op in trace_now["ops"] if op["op"] != "expect"] == [
        op for op in trace_before["ops"] if op["op"] != "expect"
    ], "stimulus (non-expect ops) must be frozen"
    for k in ("trace_format", "name", "tier", "description", "provenance"):
        assert trace_now[k] == trace_before[k], f"trace metadata field {k} must be frozen"

    suite = load_suite()  # hash was refreshed, so the corpus reloads clean
    assert content_hash(base) == suite.manifest.golden_hashes[rel(base)]
    assert any("refreshed" in ln for ln in lines)


def test_cnf7_write_reports_no_change_when_already_matching(sandbox):
    # CNF-7: --write on an already-correct case writes nothing and says so.
    before = _sandbox_snapshot(sandbox)
    lines, code = gen.regen_case("single_gate", write=True)
    assert code == 0
    assert _sandbox_snapshot(sandbox) == before
    assert any("nothing to do" in ln for ln in lines)


def test_cnf7_unknown_case_lists_names(sandbox):
    # CNF-7: an unknown case name errors and lists the available case names.
    lines, code = gen.regen_case("no_such_case", write=False)
    assert code == 1
    text = "\n".join(lines)
    assert "unknown case 'no_such_case'" in text
    assert "single_gate" in text, "the error must list the available case names"


# ----- CNF-8: report determinism + runner CLI surface ---------------------


def test_cnf8_report_byte_identical_across_runs():
    # CNF-8: two consecutive run invocations emit byte-identical reports. Filtered
    # to one tiny case to keep the C compile cheap; determinism is independent of
    # which case.
    from conformance.runner.suite import run

    lines1, code1 = run(name_filter="single_gate")
    lines2, code2 = run(name_filter="single_gate")
    assert code1 == 0 and code2 == 0
    assert lines1 == lines2, "two runs must produce byte-identical reports"


def test_cnf8_list_surface_is_manifest_ordered():
    # CNF-8: `list` enumerates every case, one line each, in manifest order.
    from conformance.runner.suite import list_cases

    suite = load_suite()
    lines = list_cases()
    body = [ln for ln in lines if ln and not ln.startswith(("SHDL", "flatten", "cases:"))]
    listed = [ln.split()[0] for ln in body]
    assert listed == list(suite.manifest.case_names), "list must be in manifest order"


def test_cnf8_cli_exit_codes_and_tier_filter():
    # CNF-8: the CLI surface — `list` exits 0; `run --tier A --filter` exits 0 on a
    # passing tier; an unknown regen case exits 1.
    from conformance.runner.cli import main

    assert main(["list"]) == 0
    assert main(["run", "--tier", "A", "--filter", "single_gate"]) == 0
    assert main(["regen", "--case", "no_such_case"]) == 1


def test_cnf8_run_failure_exits_nonzero(sandbox):
    # CNF-8: a run whose Tier A golden no longer matches the toolchain exits
    # nonzero. The golden is corrupted in the sandbox (hash refreshed to clear the
    # fence) so the byte-compare fails and `run` reports a failure + exit 1.
    from conformance.runner.cli import main

    base = sandbox / "cases" / "single_gate" / "expected.base.shdl"
    base.write_text(base.read_text(encoding="utf-8") + "# not what the flattener emits\n")
    _refresh_all_hashes(sandbox)
    assert main(["run", "--tier", "A", "--filter", "single_gate"]) == 1
