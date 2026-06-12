"""CNF-5 — the conformance corpus is PySHDL's acceptance gate.

Each case's frozen ``expected.base.shdl`` is compiled once through the public
API; every trace then replays against a *fresh* Circuit instance and must
match its frozen golden values bit-exactly. ``strict=False`` because the
traces deliberately poke over-wide values to pin the ABI's masking rules.
"""

from __future__ import annotations

import pytest

from conformance.runner import executor
from conformance.runner.schema import load_suite
from pyshdl import Circuit
from shdlc.cc import lib_suffix

_SUITE = load_suite()
_PARAMS = [(case, trace) for case in _SUITE.cases for trace in case.traces]


@pytest.fixture(scope="module")
def case_lib(tmp_path_factory):
    """Build each case's frozen base once (via the public API), cached."""
    root = tmp_path_factory.mktemp("pyshdl-cnf5")
    built = {}

    def get(case):
        if case.name not in built:
            art = root / case.name
            Circuit.from_base(case.expected_base, build_dir=art, strict=False).close()
            built[case.name] = next(
                p for p in art.glob(f"*{lib_suffix()}") if ".copy" not in p.name
            )
        return built[case.name]

    return get


@pytest.mark.parametrize(("case", "trace"), _PARAMS, ids=[f"{c.name}-{t.name}" for c, t in _PARAMS])
def test_corpus_trace_replays_bit_exactly(case, trace, case_lib):
    with Circuit.from_library(case_lib(case), base=case.expected_base, strict=False) as circuit:
        observations = executor.replay(trace.ops, {"pyshdl": circuit})
    problems = executor.mismatches(observations, "pyshdl")
    assert not problems, "\n".join(problems)
