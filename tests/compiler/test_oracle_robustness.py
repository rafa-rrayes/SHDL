"""Oracle robustness & the stricter-than-ABI asymmetry (ROB-1 / ROB-2).

BaseEval is the ground-truth reference, not an ABI emulator. Several of its
raw ``ValueError`` paths are *intentional*: it surfaces oversized pokes and
malformed init metadata as test bugs rather than silently masking or skipping
them the way the compiled C ABI would. This file pins those intentional
asymmetries so they are never "fixed" into agreement with the C side by
accident (golden_tests.md §5: oracles stay strict).

The init-key ValueError paths in ``_seeded_gate`` are only reachable from
malformed ``meta.init`` (which ``shdlc.model.build_circuit`` rejects with a
ModelError). BaseEval is an *independent* consumer of the same text, so it
keeps its own guards; they are pinned here as intentional rather than removed.
"""

from __future__ import annotations

import json

import pytest

from shdlc.baseshdl import parse_base
from shdlc.sim.base_eval import BaseEval


def _oracle(core: str, meta: dict) -> BaseEval:
    return BaseEval(parse_base(core + "\nmeta " + json.dumps(meta)))


NOT1 = "component Not1(A) -> (Q) { n: NOT; connect { A -> n.A; n.O -> Q; } }"
PASS1 = "component Pass1(A) -> (Out) { connect { A -> Out; } }"
WIDE = (
    "component W(a, b, c, d) -> (y) {\n"
    "    g: AND;\n"
    "    connect { a -> g.A; b -> g.B; g.O -> y; }\n"
    "}"
)


# ---------------------------------------------------------------------------
# ROB-2: the intentional poke-overflow asymmetry, pinned with pytest.raises.
# ---------------------------------------------------------------------------


def test_baseeval_poke_overflow_raises_unlike_the_abi():
    # ROB-2: a value too wide for the port is a ValueError in the oracle. The
    # compiled C ABI masks the same value modulo 2**width (AMB-2) -- DualSim
    # bridges the two deliberately. This is the explicit pin the row asks for.
    oracle = _oracle(NOT1, {"ports": {"inputs": {"A": ["A"]}, "outputs": {"Q": ["Q"]}}})
    with pytest.raises(ValueError, match=r"does not fit 1-bit port 'A'"):
        oracle.poke("A", 2)  # 1-bit port: 2 overflows
    # The boundary value fits and does not raise.
    oracle.poke("A", 1)
    assert oracle.peek("A") == 1


def test_baseeval_poke_negative_raises():
    # ROB-2: negatives are rejected too (the ABI never sees negatives -- the
    # ctypes boundary is uint64 -- so this is purely an oracle-strictness pin).
    oracle = _oracle(
        WIDE,
        {
            "ports": {
                "inputs": {"P": ["a", "b"], "c": ["c"], "d": ["d"]},
                "outputs": {"y": ["y"]},
            }
        },
    )
    with pytest.raises(ValueError, match="does not fit"):
        oracle.poke("P", -1)


def test_baseeval_poke_overflow_intent_is_documented():
    # ROB-2: the stricter-than-ABI intent must live in the docstring so it is
    # never silently relaxed. Assert the contract is stated where maintainers
    # will see it.
    doc = BaseEval.poke.__doc__ or ""
    assert "stricter" in doc.lower()
    assert "abi" in doc.lower()


# ---------------------------------------------------------------------------
# ROB-1: the init-key ValueError paths in BaseEval, pinned as intentional.
# ---------------------------------------------------------------------------


def test_init_key_resolving_to_input_wire_raises():
    # ROB-1: an init key that aliases through to an input wire (a passthrough)
    # cannot seed a gate. BaseEval raises; this mirrors the model layer's
    # ModelError, kept as an independent guard in the oracle.
    with pytest.raises(ValueError, match=r"resolves to input wire 'A'"):
        _oracle(
            PASS1,
            {
                "ports": {"inputs": {"A": ["A"]}, "outputs": {"Out": ["Out"]}},
                "init": {"Out": 1},
            },
        )


def test_init_key_that_resolves_to_nothing_raises():
    # ROB-1: an init key naming neither a gate output nor a resolvable output
    # wire is a ValueError. Reachable only from malformed meta.init that the
    # model layer would reject -- BaseEval keeps its own guard regardless.
    with pytest.raises(ValueError, match="does not resolve to a gate"):
        _oracle(
            NOT1,
            {
                "ports": {"inputs": {"A": ["A"]}, "outputs": {"Q": ["Q"]}},
                "init": {"nope": 1},
            },
        )


def test_init_on_gate_output_succeeds():
    # ROB-1 positive boundary: a well-formed init seed does NOT raise -- the
    # guards above fire only on malformed keys, never on valid ones.
    oracle = _oracle(
        NOT1,
        {
            "ports": {"inputs": {"A": ["A"]}, "outputs": {"Q": ["Q"]}},
            "init": {"n.O": 1},
        },
    )
    # Seed visible at power-on (no tick), proving the seed took effect.
    assert oracle.peek("Q") == 1
