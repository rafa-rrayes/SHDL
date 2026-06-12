"""Base SHDL reader (shdlc.baseshdl) diagnostics and frontend robustness.

Covers the obligations on the *consumer's* independent Base SHDL reader:

- CCT-9: each of the seven ``BaseParseError`` raise sites is triggered by a
  minimal artifact, asserting the message names the offending construct.
- CCT-7 / ROB-6: malformed ``meta`` JSON is wrapped in ``BaseParseError`` and
  surfaced cleanly through the shdlc CLI -- never a raw ``json.JSONDecodeError``.
- CCT-18 / AMB-36: Base-level naming reservations (``__x``, ``Sum_2_``) are a
  producer-side obligation; shdlc accepts such gate names unchecked while
  fully re-validating the structural connection rules.
- MET-8 (consumer half): unknown ``meta`` keys are tolerated, and no consumer
  reads ``meta.version`` -- a version-mismatch artifact still loads.

Every message assertion checks substance (the offending token), never an exact
string, so wording can evolve without churning the suite.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from shdlc.baseshdl import BaseParseError, parse_base
from shdlc.model import build_circuit
from shdlc.sim.base_eval import BaseEval

from .harness import REPO

# A minimal valid artifact the malformed cases mutate from.
VALID = """\
component X(a, b) -> (y) {
    g: AND;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
"""


# ---------------------------------------------------------------------------
# CCT-9: the seven BaseParseError raise sites, one minimal artifact each.
# (id, source text, substrings the BaseParseError message must contain)
# ---------------------------------------------------------------------------

PARSE_ERROR_CASES = [
    # 1. scanner EOF: a token is demanded past the end of input.
    ("scanner-eof", "component", ["end of input"]),
    # 2. expect mismatch: 'component' keyword wrong, then a structural token.
    ("expect-mismatch", "widget X(a) -> (y) { connect { } }", ["expected", "component"]),
    # 3. non-identifier where an identifier is required (the component name).
    # The scanner tokenizes a leading digit as a single '\\S' token, so the
    # message names '9' -- the offending token at that position.
    ("non-identifier", "component 9bad(a) -> (y) { connect { } }", ["identifier", "9"]),
    # 4. unknown primitive type.
    (
        "unknown-primitive",
        "component X(a) -> (y) { g: NAND; connect { a -> y; } }",
        ["unknown primitive", "NAND"],
    ),
    # 5. duplicate instance name.
    (
        "duplicate-instance",
        "component X(a) -> (y) { g: NOT; g: NOT; connect { a -> y; } }",
        ["duplicate instance", "g"],
    ),
    # 6. one-component-per-file: a stray token after the closing brace.
    (
        "trailing-token-after-component",
        VALID + "component Y(a) -> (b) { connect { a -> b; } }",
        ["component"],
    ),
    # 7. trailing content after the meta object.
    (
        "trailing-after-meta",
        VALID + 'meta { "ports": {} } leftover',
        ["trailing content", "meta"],
    ),
]


@pytest.mark.parametrize(
    ("text", "mentions"),
    [(text, mentions) for _, text, mentions in PARSE_ERROR_CASES],
    ids=[case_id for case_id, _, _ in PARSE_ERROR_CASES],
)
def test_base_parse_error_sites(text: str, mentions: list[str]):
    # CCT-9
    with pytest.raises(BaseParseError) as ei:
        parse_base(text)
    message = str(ei.value)
    for mention in mentions:
        assert mention in message, (
            f"{mention!r} not in BaseParseError: {message!r}\n--- source ---\n{text}"
        )


# ---------------------------------------------------------------------------
# CCT-7 / ROB-6: malformed meta JSON -> BaseParseError, not a raw decode error.
# ---------------------------------------------------------------------------

MALFORMED_META = [
    ("bare-words", VALID + "meta { this is not json }"),
    ("trailing-comma", VALID + 'meta { "ports": {}, }'),
    ("unterminated", VALID + 'meta { "ports": '),
    ("not-an-object", VALID + "meta [1, 2, 3] extra"),
]


@pytest.mark.parametrize("text", [t for _, t in MALFORMED_META], ids=[i for i, _ in MALFORMED_META])
def test_malformed_meta_json_wrapped(text: str):
    # CCT-7 / ROB-6: the wrapper catches json.JSONDecodeError specifically;
    # any escape would be a raw exception, not a BaseParseError.
    with pytest.raises(BaseParseError) as ei:
        parse_base(text)
    assert "meta" in str(ei.value).lower()
    # And it really is the wrapped decode error, not some other failure.
    assert not isinstance(ei.value, json.JSONDecodeError)


def test_malformed_meta_json_surfaces_cleanly_through_cli(tmp_path):
    # CCT-7 / ROB-6: the live crash reproducer, now diagnosed. The CLI must
    # exit 1 with a single 'shdlc: error:' line and no Python traceback.
    bad = tmp_path / "badmeta.base"
    bad.write_text(VALID + "meta { not valid json at all }")
    proc = subprocess.run(
        ["uv", "run", "--project", str(REPO), "shdlc", str(bad)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    assert "shdlc: error:" in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "JSONDecodeError" not in proc.stderr, proc.stderr


# ---------------------------------------------------------------------------
# CCT-18 / AMB-36: producer-side naming reservations are NOT consumer-enforced.
# ---------------------------------------------------------------------------

# A gate named '__x' (dunder) and one named 'Sum_2_' (bus pattern): both would
# be rejected at the *producer* (flattener) but shdlc accepts them, because
# §3.6 makes naming reservations a producer obligation. The structural
# connection rules ARE still fully validated (the gate is wired correctly).
RESERVED_NAME_TEXT = """\
component Reserved(a) -> (y, z) {
    __x: NOT;
    Sum_2_: NOT;
    connect { a -> __x.A; __x.O -> y; a -> Sum_2_.A; Sum_2_.O -> z; }
}
meta { "ports": { "inputs": { "a": ["a"] }, "outputs": { "y": ["y"], "z": ["z"] } } }
"""


def test_reserved_gate_names_accepted_unchecked():
    # CCT-18 / AMB-36: pin the trust as the contract.
    comp = parse_base(RESERVED_NAME_TEXT)
    assert set(comp.gates) == {"__x", "Sum_2_"}
    # The model builds it without complaint: codegen consumes these names as-is.
    circuit = build_circuit(comp)
    assert {g.name for g in circuit.gates} == {"__x", "Sum_2_"}


def test_reserved_names_still_validate_connection_rules():
    # CCT-18: acceptance of reserved NAMES does not relax §3.6 wiring rules.
    # Here Sum_2_ has a floating input pin: still a structural error.
    from shdlc.model import ModelError

    bad = """\
component R(a) -> (y) {
    __x: NOT;
    Sum_2_: NOT;
    connect { a -> __x.A; __x.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"] }, "outputs": { "y": ["y"] } } }
"""
    with pytest.raises(ModelError) as ei:
        build_circuit(parse_base(bad))
    assert "Sum_2_" in str(ei.value)


# ---------------------------------------------------------------------------
# MET-8 (consumer half): unknown meta keys tolerated; no consumer reads version.
# ---------------------------------------------------------------------------

FUTURE_META_TEXT = (
    """\
component Met(a) -> (y) {
    g: NOT;
    connect { a -> g.A; g.O -> y; }
}
meta """
    + json.dumps(
        {
            "version": "999.0-from-the-future",
            "ports": {"inputs": {"a": ["a"]}, "outputs": {"y": ["y"]}},
            "init": {"g.O": 1},
            "some_future_block": {"anything": [1, 2, 3]},
            "monitors": {"unknown": "schema"},
        }
    )
    + "\n"
)


def test_baseeval_tolerates_unknown_meta_keys_and_version():
    # MET-8 consumer half: BaseEval reads ports/init/timing only -- a future
    # version string and an unknown block must not perturb it.
    comp = parse_base(FUTURE_META_TEXT)
    oracle = BaseEval(comp)
    # init seed visible at power-on without a tick.
    assert oracle.peek("y") == 1
    oracle.poke("a", 1)
    oracle.step(1)
    assert oracle.peek("y") == 0  # NOT(1) at cycle 1


def test_no_consumer_reads_meta_version():
    # MET-8: a wildly mismatched version still parses, builds, and simulates.
    # Pin by mutating ONLY the version and proving identical behavior.
    base = parse_base(FUTURE_META_TEXT)
    other_text = FUTURE_META_TEXT.replace("999.0-from-the-future", "0.0.0-ancient")
    other = parse_base(other_text)
    a, b = BaseEval(base), BaseEval(other)
    assert a.peek("y") == b.peek("y") == 1
    # The model layer likewise ignores version: both build to equal circuits.
    assert build_circuit(base) == build_circuit(other)
