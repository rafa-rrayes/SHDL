"""Tests for ``shdlc.model.build_circuit``: every invariant, plus positives.

Self-contained: no conftest fixtures. Real-world inputs are produced by
flattening tests/fixtures/*.shdl at test time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from flattener.pipeline import flatten_program
from shdlc.baseshdl import parse_base
from shdlc.model import Circuit, Gate, ModelError, PortGroup, Ref, build_circuit

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SPEC = Path(__file__).resolve().parent.parent.parent / "docs" / "base_shdl.md"
TS = "2026-01-01T00:00:00Z"


def build(text: str) -> Circuit:
    return build_circuit(parse_base(text))


def with_meta(core: str, meta: dict) -> str:
    return core + "\nmeta " + json.dumps(meta)


def flatten_fixture(name: str) -> str:
    return flatten_program(str(FIXTURES / f"{name}.shdl"), timestamp=TS).text


# A minimal valid AND component used as the base for many meta-error cases.
AND1 = """
component And1(A, B) -> (O1) {
    g1: AND;
    connect {
        A -> g1.A;
        B -> g1.B;
        g1.O -> O1;
    }
}
"""

# Minimal NOT-driven single output, for init-related cases.
NOT1 = """
component Not1(A) -> (Q) {
    n: NOT;
    connect {
        A -> n.A;
        n.O -> Q;
    }
}
"""

# Pure passthrough: output driven directly by an input wire, zero gates.
PASS1 = """
component Pass1(A) -> (Out) {
    connect {
        A -> Out;
    }
}
"""


def _wide_port_case(width: int) -> str:
    """A component with ``width`` input wires and a meta port covering all."""
    wires = [f"w{i}" for i in range(width)]
    core = (
        "component Wide(" + ", ".join(wires) + ") -> (Out) {\n"
        "    n: NOT;\n"
        "    connect { w0 -> n.A; n.O -> Out; }\n"
        "}"
    )
    meta = {"ports": {"inputs": {"W": wires}, "outputs": {"Out": ["Out"]}}}
    return with_meta(core, meta)


# ---------------------------------------------------------------------------
# Negative matrix: one minimal artifact per error rule.
# (id, base-shdl text, substrings the ModelError message must contain)
# ---------------------------------------------------------------------------

NEGATIVE_CASES = [
    (
        "dup-name-input-gate",
        "component X(A) -> (Out) { A: NOT; connect { } }",
        ["A", "input", "gate"],
    ),
    (
        "dup-name-input-output",
        "component X(A) -> (A) { connect { } }",
        ["A", "input", "output"],
    ),
    (
        "unknown-gate-in-dst",
        "component X(A) -> (Out) { n: NOT; connect { A -> nope.A; n.O -> Out; A -> n.A; } }",
        ["nope"],
    ),
    (
        "unknown-gate-in-src",
        "component X(A) -> (Out) { connect { nope.O -> Out; } }",
        ["nope"],
    ),
    (
        "bad-pin-name",
        "component X(A, B) -> (Out) { g1: AND; connect { A -> g1.A; B -> g1.C; g1.O -> Out; } }",
        ["g1", "C"],
    ),
    (
        "dst-is-output-pin",
        "component X(A, B) -> (Out) { g1: AND; connect { A -> g1.A; B -> g1.O; g1.O -> Out; } }",
        ["g1", "O"],
    ),
    (
        "src-pin-not-O",
        "component X(A) -> (Out) { n: NOT; connect { A -> n.A; n.A -> Out; } }",
        ["n.A"],
    ),
    (
        "src-bare-gate-name",
        "component X(A) -> (Out) { n: NOT; connect { A -> n.A; n -> Out; } }",
        ["n"],
    ),
    (
        "src-unknown-wire",
        "component X(A) -> (Out) { connect { nope -> Out; } }",
        ["nope"],
    ),
    (
        "driving-an-input-wire",
        "component X(A, B) -> (Out) { n: NOT; connect { A -> n.A; n.O -> Out; A -> B; } }",
        ["B"],
    ),
    (
        "dst-bare-gate-name",
        "component X(A) -> (Out) { n: NOT; connect { A -> n.A; n.O -> Out; A -> n; } }",
        ["n"],
    ),
    (
        "dst-unknown-wire",
        "component X(A) -> (Out) { connect { A -> Out; A -> nowhere; } }",
        ["nowhere"],
    ),
    (
        "binary-gate-missing-pin-B",
        "component X(A) -> (Out) { g1: AND; connect { A -> g1.A; g1.O -> Out; } }",
        ["g1", "B"],
    ),
    (
        "not-given-pin-B",
        "component X(A, B) -> (Out) { n: NOT; connect { A -> n.A; B -> n.B; n.O -> Out; } }",
        ["n", "B"],
    ),
    (
        "floating-not-pin-A",
        "component X(A) -> (Out) { n: NOT; v: __VCC__; connect { v.O -> Out; } }",
        ["n", "A"],
    ),
    (
        "pin-double-driven",
        "component X(A, B) -> (Out) { n: NOT; connect { A -> n.A; B -> n.A; n.O -> Out; } }",
        ["n.A"],
    ),
    (
        "output-double-driven",
        "component X(A, B) -> (Out) { n: NOT; m: NOT; connect"
        " { A -> n.A; B -> m.A; n.O -> Out; m.O -> Out; } }",
        ["Out"],
    ),
    (
        "undriven-output",
        "component X(A) -> (Out, Out2) { connect { A -> Out; } }",
        ["Out2"],
    ),
    (
        "connection-into-vcc",
        "component X(A) -> (Out) { v: __VCC__; connect { A -> v.A; v.O -> Out; } }",
        ["v"],
    ),
    (
        "connection-into-gnd",
        "component X(A) -> (Out) { g: __GND__; connect { A -> g.A; g.O -> Out; } }",
        ["g"],
    ),
    (
        "alias-cycle",
        "component X(A) -> (O1, O2) { connect { O2 -> O1; O1 -> O2; } }",
        ["O1", "O2", "cycle"],
    ),
    (
        "ports-not-object",
        with_meta(AND1, {"ports": None}),
        ["meta.ports"],
    ),
    # CCT-8: meta.ports.inputs / .outputs is not a JSON object.
    (
        "ports-inputs-not-object",
        with_meta(AND1, {"ports": {"inputs": "nope", "outputs": {}}}),
        ["meta.ports.inputs", "object"],
    ),
    (
        "ports-outputs-not-object",
        with_meta(AND1, {"ports": {"inputs": {}, "outputs": [1, 2]}}),
        ["meta.ports.outputs", "object"],
    ),
    # CCT-8: a port's wires value is not an array of names.
    (
        "ports-wires-not-array",
        with_meta(AND1, {"ports": {"inputs": {"P": "A"}, "outputs": {}}}),
        ["P", "array"],
    ),
    # CCT-8: unknown wire named by an INPUT port (distinct from the output
    # side already covered by ports-unknown-wire).
    (
        "ports-unknown-input-wire",
        with_meta(AND1, {"ports": {"inputs": {"P": ["nope"]}, "outputs": {}}}),
        ["P", "nope"],
    ),
    # CCT-8: meta.init is not a JSON object.
    (
        "init-not-object",
        with_meta(NOT1, {"init": [1, 2, 3]}),
        ["meta.init", "object"],
    ),
    # AMB-34: an input wire used by two ports is rejected (silent aliasing).
    (
        "ports-dup-input-wire-across-ports",
        with_meta(AND1, {"ports": {"inputs": {"P": ["A"], "Q": ["A"]}, "outputs": {}}}),
        ["A", "already used"],
    ),
    # AMB-34: an input wire repeated within one port is likewise rejected.
    (
        "ports-dup-input-wire-within-port",
        with_meta(AND1, {"ports": {"inputs": {"P": ["A", "A"]}, "outputs": {}}}),
        ["A", "already used"],
    ),
    # AMB-35: ports present but a direction key absent -> name the missing key.
    (
        "ports-missing-inputs-key",
        with_meta(AND1, {"ports": {"outputs": {"Y": ["O1"]}}}),
        ["inputs", "missing"],
    ),
    (
        "ports-missing-outputs-key",
        with_meta(AND1, {"ports": {"inputs": {"P": ["A", "B"]}}}),
        ["outputs", "missing"],
    ),
    (
        "ports-unknown-wire",
        with_meta(AND1, {"ports": {"inputs": {"A": ["A"]}, "outputs": {"Y": ["nope"]}}}),
        ["Y", "nope"],
    ),
    (
        "ports-input-port-names-output-wire",
        with_meta(AND1, {"ports": {"inputs": {"P": ["O1"]}, "outputs": {}}}),
        ["P", "O1"],
    ),
    (
        "ports-output-port-names-input-wire",
        with_meta(AND1, {"ports": {"inputs": {}, "outputs": {"P": ["A"]}}}),
        ["P", "A"],
    ),
    (
        "ports-dup-port-name",
        with_meta(AND1, {"ports": {"inputs": {"P": ["A"]}, "outputs": {"P": ["O1"]}}}),
        ["P"],
    ),
    (
        "ports-non-identifier-name",
        with_meta(AND1, {"ports": {"inputs": {"9bad": ["A"]}, "outputs": {}}}),
        ["9bad"],
    ),
    (
        "ports-width-0",
        with_meta(AND1, {"ports": {"inputs": {"E": []}, "outputs": {}}}),
        ["E", "0"],
    ),
    (
        "ports-width-65",
        _wide_port_case(65),
        ["W", "65"],
    ),
    (
        "init-unknown-bare-key",
        with_meta(NOT1, {"init": {"nope": 1}}),
        ["nope"],
    ),
    (
        "init-unknown-gate-key",
        with_meta(NOT1, {"init": {"nope.O": 1}}),
        ["nope"],
    ),
    (
        "init-key-pin-not-O",
        with_meta(NOT1, {"init": {"n.A": 1}}),
        ["n.A"],
    ),
    (
        "init-value-2",
        with_meta(NOT1, {"init": {"n.O": 2}}),
        ["n.O", "2"],
    ),
    (
        "init-value-bool-true",
        with_meta(NOT1, {"init": {"n.O": True}}),  # JSON true is not 0 or 1
        ["n.O"],
    ),
    (
        "init-value-float",
        with_meta(NOT1, {"init": {"n.O": 1.0}}),  # JSON 1.0 is not an exact int
        ["n.O"],
    ),
    (
        "init-passthrough-key",
        with_meta(PASS1, {"init": {"Out": 1}}),
        ["Out"],
    ),
    (
        "init-duplicate-seed-via-alias",
        with_meta(NOT1, {"init": {"Q": 1, "n.O": 1}}),
        ["Q", "n.O", "n"],
    ),
]


@pytest.mark.parametrize(
    ("text", "mentions"),
    [(text, mentions) for _, text, mentions in NEGATIVE_CASES],
    ids=[case_id for case_id, _, _ in NEGATIVE_CASES],
)
def test_negative(text: str, mentions: list[str]):
    with pytest.raises(ModelError) as ei:
        build(text)
    message = str(ei.value)
    for mention in mentions:
        assert mention in message, f"{mention!r} not in error: {message}"


# ---------------------------------------------------------------------------
# Positives: handwritten minimal circuits.
# ---------------------------------------------------------------------------


def test_and_gate_no_meta_synthesizes_identity_ports():
    c = build(AND1)
    assert c.name == "And1"
    assert c.inputs == ("A", "B")
    assert c.outputs == ("O1",)
    assert c.gates == (Gate("g1", "AND", Ref("in", 0), Ref("in", 1)),)
    assert c.in_ports == (
        PortGroup("A", (Ref("in", 0),)),
        PortGroup("B", (Ref("in", 1),)),
    )
    assert c.out_ports == (PortGroup("O1", (Ref("gate", 0),)),)
    assert c.init == ()


def test_and_gate_with_meta_ports_and_unrelated_meta_keys():
    meta = {
        "version": "2.0",
        "ports": {"inputs": {"X": ["A", "B"]}, "outputs": {"Y": ["O1"]}},
        "timing": {"max_depth": 1, "is_combinational": True, "has_feedback": False},
        "doc": {"description": "and gate"},
        "some_future_block": {"ignored": True},
    }
    c = build(with_meta(AND1, meta))
    assert c.in_ports == (PortGroup("X", (Ref("in", 0), Ref("in", 1))),)
    assert c.out_ports == (PortGroup("Y", (Ref("gate", 0),)),)
    assert c.init == ()


def test_model_level_unknown_primitive_rejected():
    # CCT-8: the model's own unknown-primitive check. parse_base shadows it
    # (it rejects unknown types first), so reach it via a direct BaseComponent,
    # proving the model layer does not trust its input's gate types.
    from shdlc.baseshdl import BaseComponent

    comp = BaseComponent(
        name="X",
        inputs=["a"],
        outputs=["y"],
        gates={"g": "NAND"},
        connections=[("a", "g.A"), ("g.O", "y")],
        meta={},
    )
    with pytest.raises(ModelError) as ei:
        build_circuit(comp)
    assert "g" in str(ei.value) and "NAND" in str(ei.value)


def test_ports_subset_coverage_is_legal():
    # AMB-33: meta.ports may cover only a subset of header wires. The uncovered
    # input wire (B) becomes ABI-unreachable (stuck at 0); the uncovered output
    # is unobservable. This is legal-but-defined, matching the
    # referenced-bits-only philosophy.
    c = build(
        with_meta(
            "component Sub(A, B) -> (O1, O2) {\n"
            "    g: AND;\n"
            "    h: NOT;\n"
            "    connect { A -> g.A; B -> g.B; g.O -> O1; A -> h.A; h.O -> O2; }\n"
            "}",
            {"ports": {"inputs": {"P": ["A"]}, "outputs": {"Q": ["O1"]}}},
        )
    )
    # Only the covered port exists; B and O2 are simply absent from the ABI.
    assert tuple(p.name for p in c.in_ports) == ("P",)
    assert c.in_ports[0].refs == (Ref("in", 0),)  # wire A only
    assert tuple(p.name for p in c.out_ports) == ("Q",)


def test_output_wire_reuse_across_ports_is_allowed():
    # AMB-34: reusing an OUTPUT wire across ports is harmless read fan-out and
    # must be accepted (unlike input-wire reuse, which is rejected).
    c = build(
        with_meta(
            AND1,
            {"ports": {"inputs": {"P": ["A", "B"]}, "outputs": {"Y": ["O1"], "Z": ["O1"]}}},
        )
    )
    out = {p.name: p.refs for p in c.out_ports}
    assert out["Y"] == out["Z"] == (Ref("gate", 0),)


def test_width_64_port_is_accepted():
    c = build(_wide_port_case(64))
    (in_port,) = c.in_ports
    assert in_port.name == "W"
    assert len(in_port.refs) == 64
    assert in_port.refs[0] == Ref("in", 0)
    assert in_port.refs[63] == Ref("in", 63)


def test_passthrough_zero_gates():
    c = build(PASS1)
    assert c.gates == ()
    assert c.in_ports == (PortGroup("A", (Ref("in", 0),)),)
    assert c.out_ports == (PortGroup("Out", (Ref("in", 0),)),)


def test_vcc_gnd_normalization_zero_inputs():
    text = """
    component Const() -> (H, L) {
        v: __VCC__;
        g: __GND__;
        connect { v.O -> H; g.O -> L; }
    }
    """
    c = build(text)
    assert c.inputs == ()
    assert c.gates == (Gate("v", "VCC", None, None), Gate("g", "GND", None, None))
    assert c.out_ports == (
        PortGroup("H", (Ref("gate", 0),)),
        PortGroup("L", (Ref("gate", 1),)),
    )


def test_zero_outputs():
    c = build("component Sink(A) -> () { n: NOT; connect { A -> n.A; } }")
    assert c.outputs == ()
    assert c.out_ports == ()
    assert c.gates == (Gate("n", "NOT", Ref("in", 0), None),)


def test_alias_chain_resolves_to_gate():
    text = """
    component AC(A) -> (O1, O2, O3) {
        n: NOT;
        connect { A -> n.A; n.O -> O3; O3 -> O2; O2 -> O1; }
    }
    """
    c = build(text)
    assert c.out_ports == (
        PortGroup("O1", (Ref("gate", 0),)),
        PortGroup("O2", (Ref("gate", 0),)),
        PortGroup("O3", (Ref("gate", 0),)),
    )


def test_gate_pin_driven_by_output_wire_resolves_through_chain():
    text = """
    component AC2(A) -> (O1, O2, P) {
        n: NOT;
        m: NOT;
        connect { A -> n.A; n.O -> O2; O2 -> O1; O1 -> m.A; m.O -> P; }
    }
    """
    c = build(text)
    m = c.gates[1]
    assert m.name == "m"
    assert m.a == Ref("gate", 0)  # through O1 -> O2 -> n.O, never an alias


def test_gate_pin_driven_by_input_passthrough_output_wire():
    text = """
    component AC3(A) -> (Out, P) {
        n: NOT;
        connect { A -> Out; Out -> n.A; n.O -> P; }
    }
    """
    c = build(text)
    assert c.gates[0].a == Ref("in", 0)


def test_init_via_gate_key_and_output_port_name():
    c = build(with_meta(NOT1, {"init": {"Q": 1}}))
    assert c.init == ((0, 1),)
    c = build(with_meta(NOT1, {"init": {"n.O": 0}}))
    assert c.init == ((0, 0),)


def test_init_preserves_meta_insertion_order():
    text = """
    component Two(A) -> (Q1, Q2) {
        g1: NOT;
        g2: NOT;
        connect { A -> g1.A; A -> g2.A; g1.O -> Q1; g2.O -> Q2; }
    }
    """
    c = build(with_meta(text, {"init": {"g2.O": 1, "g1.O": 0}}))
    assert c.init == ((1, 1), (0, 0))


def test_determinism_and_slot_order():
    text = """
    component D(I2, I1) -> (Z2, Z1) {
        b: NOT;
        a: NOT;
        connect { I2 -> b.A; I1 -> a.A; b.O -> Z2; a.O -> Z1; }
    }
    """
    c = build(text)
    assert c.inputs == ("I2", "I1")  # header order, not sorted
    assert tuple(g.name for g in c.gates) == ("b", "a")  # declaration order
    assert c.outputs == ("Z2", "Z1")
    assert build(text) == c  # rebuilding yields an identical Circuit


# ---------------------------------------------------------------------------
# The worked example from base_shdl.md section 3.7.
# ---------------------------------------------------------------------------


def test_spec_section_3_7_add2_example():
    spec = SPEC.read_text()
    m = re.search(r"```\n(component Add2.*?)```", spec, re.DOTALL)
    assert m, "base_shdl.md section 3.7 Add2 example not found"
    c = build(m.group(1))
    assert c.name == "Add2"
    assert c.inputs == ("A_1_", "A_2_", "B_1_", "B_2_", "Cin")
    assert c.outputs == ("Sum_1_", "Sum_2_", "Cout")
    names = tuple(g.name for g in c.gates)
    assert names == (
        "fa1_x1", "fa1_x2", "fa1_a1", "fa1_a2", "fa1_o1",
        "fa2_x1", "fa2_x2", "fa2_a1", "fa2_a2", "fa2_o1",
    )
    idx = {name: i for i, name in enumerate(names)}
    # No meta section: identity 1-bit groups synthesized from the header.
    assert tuple(p.name for p in c.in_ports) == c.inputs
    assert all(p.refs == (Ref("in", i),) for i, p in enumerate(c.in_ports))
    assert c.out_ports == (
        PortGroup("Sum_1_", (Ref("gate", idx["fa1_x2"]),)),
        PortGroup("Sum_2_", (Ref("gate", idx["fa2_x2"]),)),
        PortGroup("Cout", (Ref("gate", idx["fa2_o1"]),)),
    )
    # Spot-check resolved pins: fa2_x2.B is driven by fa1_o1.O.
    fa2_x2 = c.gates[idx["fa2_x2"]]
    assert fa2_x2.b == Ref("gate", idx["fa1_o1"])


# ---------------------------------------------------------------------------
# Real fixtures, flattened at test time.
# ---------------------------------------------------------------------------


def test_fixture_add2_builds():
    comp = parse_base(flatten_fixture("add2"))
    c = build_circuit(comp)
    assert c.name == "Add2"
    assert len(c.inputs) == 5 and len(c.outputs) == 3
    assert tuple(g.name for g in c.gates) == tuple(comp.gates)  # declaration order
    assert {p.name for p in c.in_ports} == {"A", "B", "Cin"}
    assert {p.name for p in c.out_ports} == {"Sum", "Cout"}
    assert all(r.kind == "in" for p in c.in_ports for r in p.refs)
    assert all(r.kind == "gate" for p in c.out_ports for r in p.refs)


def test_fixture_srlatch_init_resolves_to_driving_gates():
    comp = parse_base(flatten_fixture("srlatch"))
    c = build_circuit(comp)
    out_ports = {p.name: p for p in c.out_ports}
    q_ref, qn_ref = out_ports["Q"].refs[0], out_ports["Qn"].refs[0]
    assert q_ref.kind == "gate" and qn_ref.kind == "gate"
    # The fixture seeds via output-port wires: Q = 0, Qn = 1 (in meta order).
    assert comp.meta["init"] == {"Q": 0, "Qn": 1}
    assert c.init == ((q_ref.index, 0), (qn_ref.index, 1))
    # Each seed lands on the NOT gate that drives the latch output.
    assert c.gates[q_ref.index].type == "NOT"
    assert c.gates[qn_ref.index].type == "NOT"


def test_fixture_passthru_out_ports_reach_input_refs():
    c = build_circuit(parse_base(flatten_fixture("passthru")))
    assert c.inputs == ("A_1_", "A_2_")
    out_ports = {p.name: p for p in c.out_ports}
    assert out_ports["B"].refs == (Ref("in", 0), Ref("in", 1))
    (c_ref,) = out_ports["C"].refs
    assert c_ref == Ref("gate", 0)  # the lone XOR
    assert c.gates[0] == Gate("x1", "XOR", Ref("in", 0), Ref("in", 1))


def test_too_many_input_wires_rejected():
    # The generated C indexes input wires with uint16_t; beyond 65535 the
    # wire tables would silently truncate under release cflags. The model
    # must reject at the boundary. (BaseComponent built directly: parsing a
    # 65k-name header is needlessly slow.)
    from shdlc.baseshdl import BaseComponent

    n = 0x10000
    comp = BaseComponent(
        name="Huge",
        inputs=[f"i{k}" for k in range(n)],
        outputs=["y"],
        gates={},
        connections=[("i0", "y")],
        meta={"ports": {"inputs": {"i0": ["i0"]}, "outputs": {"y": ["y"]}}},
    )
    with pytest.raises(ModelError, match=r"too many input wires \(65536\)"):
        build_circuit(comp)
    # One fewer is fine.
    comp.inputs = comp.inputs[:-1]
    assert len(build_circuit(comp).inputs) == 0xFFFF
