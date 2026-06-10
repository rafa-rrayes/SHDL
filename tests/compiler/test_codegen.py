"""Structural tests for :func:`shdlc.codegen.generate_c`.

String/structure assertions only: the generated C is never compiled here
(integration tests elsewhere own that), and circuits are built by hand from
the :mod:`shdlc.model` dataclasses — no conftest fixtures, no meta JSON.
"""

from __future__ import annotations

import re

from shdlc.codegen import generate_c
from shdlc.model import Circuit, Gate, PortGroup, Ref


def _in(n: int) -> Ref:
    return Ref("in", n)


def _g(n: int) -> Ref:
    return Ref("gate", n)


def _circuit(
    name="C",
    inputs=(),
    gates=(),
    outputs=(),
    in_ports=(),
    out_ports=(),
    init=(),
) -> Circuit:
    return Circuit(
        name=name,
        inputs=tuple(inputs),
        gates=tuple(gates),
        outputs=tuple(outputs),
        in_ports=tuple(in_ports),
        out_ports=tuple(out_ports),
        init=tuple(init),
    )


def and_circuit() -> Circuit:
    """Single AND gate, identity single-bit ports."""
    return _circuit(
        name="AndGate",
        inputs=("a", "b"),
        gates=(Gate("g1", "AND", _in(0), _in(1)),),
        outputs=("o",),
        in_ports=(PortGroup("a", (_in(0),)), PortGroup("b", (_in(1),))),
        out_ports=(PortGroup("o", (_g(0),)),),
    )


def not_circuit() -> Circuit:
    return _circuit(
        name="Inv",
        inputs=("x",),
        gates=(Gate("n1", "NOT", _in(0), None),),
        outputs=("y",),
        in_ports=(PortGroup("x", (_in(0),)),),
        out_ports=(PortGroup("y", (_g(0),)),),
    )


def power_circuit() -> Circuit:
    return _circuit(
        name="Power",
        gates=(Gate("p", "VCC", None, None), Gate("z", "GND", None, None)),
        outputs=("Hi", "Lo"),
        out_ports=(PortGroup("Hi", (_g(0),)), PortGroup("Lo", (_g(1),))),
    )


def feedback_circuit() -> Circuit:
    """Two NOT gates reading each other, seeded 1/0 (a bistable pair)."""
    return _circuit(
        name="InvPair",
        gates=(Gate("n1", "NOT", _g(1), None), Gate("n2", "NOT", _g(0), None)),
        outputs=("Q", "Qn"),
        out_ports=(PortGroup("Q", (_g(0),)), PortGroup("Qn", (_g(1),))),
        init=((0, 1), (1, 0)),
    )


def passthrough_circuit() -> Circuit:
    """3-bit input port; one output echoes the inputs, one is a gate."""
    return _circuit(
        name="Mixed",
        inputs=("d1", "d2", "d3"),
        gates=(Gate("inv", "NOT", _in(0), None),),
        outputs=("Echo", "NotD1"),
        in_ports=(PortGroup("D", (_in(0), _in(1), _in(2))),),
        out_ports=(
            PortGroup("Echo", (_in(0), _in(1), _in(2))),
            PortGroup("NotD1", (_g(0),)),
        ),
    )


def empty_circuit() -> Circuit:
    return _circuit(name="Empty")


def wide_circuit() -> Circuit:
    """64-bit identity port pair: exercises the maximum shift (63)."""
    return _circuit(
        name="Wide",
        inputs=tuple(f"w{k}" for k in range(64)),
        in_ports=(PortGroup("W", tuple(_in(k) for k in range(64))),),
        out_ports=(PortGroup("E", tuple(_in(k) for k in range(64))),),
    )


def _body(src: str, signature: str) -> str:
    """The brace-delimited body of the function starting at ``signature``."""
    start = src.index(signature)
    brace = src.index("{", start)
    depth = 0
    for k in range(brace, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[brace + 1 : k]
    raise AssertionError(f"unterminated function body after {signature!r}")


# --- section order and overall shape ---------------------------------------


def test_section_order():
    src = generate_c(and_circuit())
    markers = [
        "/* AndGate:",
        "#include <stdint.h>",
        "#include <stdio.h>",
        "#include <string.h>",
        "#define SHDLC_API",
        "IN_a = 0",
        "G_g1 = 0",
        "OUT_o = 0",
        "NUM_IN_PORTS = 2",
        "static uint8_t inputs[",
        "static const uint16_t in_wires_a[",
        "struct in_port",
        "static const struct in_port in_ports[",
        "static const char *const out_port_names[",
        "static void recompute_outputs(void)",
        "static void tick(void)",
        "SHDLC_API void reset(void)",
        "SHDLC_API void poke(const char *signal, uint64_t value)",
        "SHDLC_API uint64_t peek(const char *signal)",
        "SHDLC_API void step(int cycles)",
        "__attribute__((constructor)) static void shdlc_ctor(void)",
    ]
    positions = []
    for m in markers:
        assert m in src, f"missing marker: {m!r}"
        positions.append(src.index(m))
    assert positions == sorted(positions), "sections out of order"


def test_header_comment_has_name_and_counts_only():
    src = generate_c(and_circuit())
    first = src.splitlines()[0]
    assert first == "/* AndGate: 1 gate, 2 input ports, 1 output port. */"


def test_counts_in_enums():
    src = generate_c(and_circuit())
    assert "NUM_INPUTS = 2" in src
    assert "NUM_GATES = 1" in src
    assert "NUM_OUT_PORTS = 1" in src
    assert "NUM_IN_PORTS = 2" in src


# --- per-gate statements ----------------------------------------------------


def test_one_nxt_assignment_per_gate_with_name_comment():
    circuit = feedback_circuit()
    src = generate_c(circuit)
    tick = _body(src, "static void tick(void)")
    assigns = [ln for ln in tick.splitlines() if ln.strip().startswith("nxt[")]
    assert len(assigns) == len(circuit.gates)
    assert "nxt[G_n1] = (uint8_t)(cur[G_n2] ^ 1u); /* n1: NOT */" in tick
    assert "nxt[G_n2] = (uint8_t)(cur[G_n1] ^ 1u); /* n2: NOT */" in tick


def test_and_reads_inputs_and_or_xor_operators():
    src = generate_c(and_circuit())
    assert "nxt[G_g1] = (uint8_t)(inputs[IN_a] & inputs[IN_b]); /* g1: AND */" in src
    fa = _circuit(
        name="OrXor",
        inputs=("a", "b"),
        gates=(
            Gate("o1", "OR", _in(0), _in(1)),
            Gate("x1", "XOR", _g(0), _in(1)),
        ),
        outputs=("o",),
        in_ports=(PortGroup("a", (_in(0),)), PortGroup("b", (_in(1),))),
        out_ports=(PortGroup("o", (_g(1),)),),
    )
    src = generate_c(fa)
    assert "nxt[G_o1] = (uint8_t)(inputs[IN_a] | inputs[IN_b]); /* o1: OR */" in src
    assert "nxt[G_x1] = (uint8_t)(cur[G_o1] ^ inputs[IN_b]); /* x1: XOR */" in src


def test_not_is_xor_one_and_no_tilde_in_gate_lines():
    src = generate_c(not_circuit())
    tick = _body(src, "static void tick(void)")
    assert "nxt[G_n1] = (uint8_t)(inputs[IN_x] ^ 1u); /* n1: NOT */" in tick
    gate_lines = [ln for ln in src.splitlines() if "nxt[" in ln]
    assert gate_lines, "no gate lines found"
    assert all("~" not in ln for ln in gate_lines)
    assert all("!" not in ln for ln in gate_lines)


def test_vcc_gnd_emit_literals():
    src = generate_c(power_circuit())
    assert "nxt[G_p] = 1u; /* p: VCC */" in src
    assert "nxt[G_z] = 0u; /* z: GND */" in src


def test_tick_commit_is_pointer_swap_then_outputs_then_dirty():
    src = generate_c(and_circuit())
    tick = _body(src, "static void tick(void)")
    swap = tick.index("tmp = cur;")
    assert tick.index("cur = nxt;") > swap
    assert tick.index("nxt = tmp;") > tick.index("cur = nxt;")
    assert tick.index("recompute_outputs();") > tick.index("nxt = tmp;")
    assert tick.index("dirty = 0;") > tick.index("recompute_outputs();")
    # All gate computes happen before the commit.
    last_assign = max(tick.index(ln) for ln in tick.splitlines() if "nxt[G_" in ln)
    assert last_assign < swap


# --- reset / init seeds ------------------------------------------------------


def test_reset_memsets_repins_and_seeds_cur_only():
    src = generate_c(feedback_circuit())
    reset = _body(src, "SHDLC_API void reset(void)")
    assert "memset(inputs, 0, sizeof(inputs));" in reset
    assert "memset(buf_a, 0, sizeof(buf_a));" in reset
    assert "memset(buf_b, 0, sizeof(buf_b));" in reset
    assert "cur = buf_a;" in reset
    assert "nxt = buf_b;" in reset
    assert "cur[G_n1] = 1u;" in reset
    assert "cur[G_n2] = 0u;" in reset
    assert "nxt[G_n1]" not in reset and "nxt[G_n2]" not in reset
    # Order: memsets -> re-pin -> seeds -> dirty=0 -> recompute_outputs.
    assert (
        reset.index("memset(buf_b")
        < reset.index("cur = buf_a;")
        < reset.index("cur[G_n1] = 1u;")
        < reset.index("dirty = 0;")
        < reset.index("recompute_outputs();")
    )
    # Seeds live only in reset, never in tick.
    tick = _body(src, "static void tick(void)")
    assert "cur[G_" not in tick.replace("(uint8_t)(cur[G_", "")


def test_init_seeds_absent_without_init():
    src = generate_c(and_circuit())
    reset = _body(src, "SHDLC_API void reset(void)")
    assert "/* init:" not in reset
    assert "cur[G_" not in reset


def test_recompute_outputs_called_in_tick_and_reset():
    src = generate_c(feedback_circuit())
    assert "recompute_outputs();" in _body(src, "static void tick(void)")
    assert "recompute_outputs();" in _body(src, "SHDLC_API void reset(void)")
    assert src.count("recompute_outputs();") == 2


# --- dirty discipline ---------------------------------------------------------


def test_dirty_handling():
    src = generate_c(and_circuit())
    assert src.count("dirty = 1;") == 1
    assert "dirty = 1;" in _body(src, "SHDLC_API void poke(")
    assert "static int dirty = 0;" in src
    assert src.count("    dirty = 0;") == 2  # statements, not the declaration
    assert "dirty = 0;" in _body(src, "static void tick(void)")
    assert "dirty = 0;" in _body(src, "SHDLC_API void reset(void)")
    assert src.count("if (dirty)") == 1
    assert "if (dirty)" in _body(src, "SHDLC_API uint64_t peek(")
    assert "if (dirty)" not in _body(src, "SHDLC_API void step(")


# --- peek/poke behavior --------------------------------------------------------


def test_peek_scans_outputs_first_and_input_path_never_ticks():
    src = generate_c(passthrough_circuit())
    peek = _body(src, "SHDLC_API uint64_t peek(")
    out_scan = peek.index("out_port_names[i]")
    in_scan = peek.index("in_ports[i].name")
    assert out_scan < in_scan
    # The only tick() call sits in the output branch (before the input scan).
    assert peek.count("tick();") == 1
    assert peek.index("tick();") < in_scan
    assert "return out_vals[i];" in peek
    # Input gather: bit b comes from wires[b], shifted into place.
    assert "v |= (uint64_t)inputs[in_ports[i].wires[b]] << b;" in peek


def test_poke_per_bit_scatter_and_unknown_paths():
    src = generate_c(passthrough_circuit())
    poke = _body(src, "SHDLC_API void poke(")
    assert "strcmp(signal, in_ports[i].name)" in poke
    assert "for (b = 0; b < in_ports[i].width; b++)" in poke
    assert "inputs[in_ports[i].wires[b]] = (uint8_t)((value >> b) & 1u);" in poke
    # Unknown-name diagnostics exist in poke and peek, after the scans.
    assert poke.count("fprintf(stderr") == 1
    peek = _body(src, "SHDLC_API uint64_t peek(")
    assert peek.count("fprintf(stderr") == 1
    assert peek.strip().endswith("return 0u;")


def test_passthrough_output_reads_inputs_in_recompute():
    src = generate_c(passthrough_circuit())
    rec = _body(src, "static void recompute_outputs(void)")
    assert "out_vals[OUT_Echo] = ((uint64_t)inputs[IN_d1] << 0)" in rec
    assert "| ((uint64_t)inputs[IN_d2] << 1)" in rec
    assert "| ((uint64_t)inputs[IN_d3] << 2);" in rec
    assert "out_vals[OUT_NotD1] = ((uint64_t)cur[G_inv] << 0);" in rec


# --- multi-bit ports -----------------------------------------------------------


def test_multibit_port_wires_lsb_first():
    src = generate_c(passthrough_circuit())
    assert "static const uint16_t in_wires_D[] = { IN_d1, IN_d2, IN_d3 };" in src
    assert '{ "D", 3, in_wires_D }' in src


def test_no_width_64_shift_anywhere():
    for circuit in (and_circuit(), passthrough_circuit(), wide_circuit()):
        src = generate_c(circuit)
        assert "<< 64" not in src
    src = generate_c(wide_circuit())
    assert "<< 63)" in src  # MSB of a 64-bit output port


# --- degenerate circuits --------------------------------------------------------


def test_degenerate_empty_circuit():
    src = generate_c(empty_circuit())
    assert "[0]" not in src
    assert "static uint8_t inputs[1];" in src
    assert "static uint8_t buf_a[1];" in src
    assert "static uint8_t buf_b[1];" in src
    assert "static uint64_t out_vals[1];" in src
    assert "NUM_INPUTS = 0" in src
    assert "NUM_GATES = 0" in src
    assert "NUM_OUT_PORTS = 0" in src
    assert "NUM_IN_PORTS = 0" in src
    # Dummy 1-element tables guarded by the count constants.
    assert "static const struct in_port in_ports[1]" in src
    assert '{ "", 0, 0 }' in src
    assert "static const char *const out_port_names[1]" in src
    assert "in_wires_" not in src.replace("in_ports[i].wires", "")
    # ABI functions still all present.
    for sig in (
        "SHDLC_API void reset(void)",
        "SHDLC_API void poke(",
        "SHDLC_API uint64_t peek(",
        "SHDLC_API void step(int cycles)",
    ):
        assert sig in src


def test_degenerate_no_inputs_but_gates():
    src = generate_c(power_circuit())
    assert "[0]" not in src
    assert "static uint8_t inputs[1];" in src
    assert "static uint8_t buf_a[2];" in src
    assert "NUM_IN_PORTS = 0" in src
    assert '{ "", 0, 0 }' in src
    assert "nxt[G_p] = 1u;" in src


def test_degenerate_no_output_ports():
    circuit = _circuit(
        name="Sink",
        inputs=("a",),
        gates=(Gate("n", "NOT", _in(0), None),),
        in_ports=(PortGroup("a", (_in(0),)),),
    )
    src = generate_c(circuit)
    assert "[0]" not in src
    assert "static uint64_t out_vals[1];" in src
    assert "NUM_OUT_PORTS = 0" in src
    assert "static const char *const out_port_names[1]" in src
    rec = _body(src, "static void recompute_outputs(void)")
    assert "out_vals[OUT_" not in rec


# --- visibility / ABI surface ----------------------------------------------------


def test_shdlc_api_on_exactly_the_four_abi_functions():
    src = generate_c(and_circuit())
    api_lines = [ln for ln in src.splitlines() if ln.startswith("SHDLC_API")]
    assert api_lines == [
        "SHDLC_API void reset(void)",
        "SHDLC_API void poke(const char *signal, uint64_t value)",
        "SHDLC_API uint64_t peek(const char *signal)",
        "SHDLC_API void step(int cycles)",
    ]


def test_every_other_function_is_static():
    src = generate_c(feedback_circuit())
    # A function definition line ends in ')' and is followed by a '{' line.
    lines = src.splitlines()
    defs = [
        ln
        for k, ln in enumerate(lines)
        if ln
        and not ln[0].isspace()
        and ln.endswith(")")
        and k + 1 < len(lines)
        and lines[k + 1] == "{"
    ]
    assert defs, "no function definitions found"
    for ln in defs:
        assert ln.startswith(("static", "SHDLC_API", "__attribute__((constructor)) static")), ln


def test_constructor_behind_gnuc_calls_reset():
    src = generate_c(and_circuit())
    k = src.index("#ifdef __GNUC__")
    ctor = src.index("__attribute__((constructor)) static void shdlc_ctor(void)")
    endif = src.index("#endif", k)
    assert k < ctor < endif
    assert "reset();" in _body(src, "__attribute__((constructor))")


def test_visibility_macro_definition():
    src = generate_c(and_circuit())
    assert "#if defined(_WIN32)" in src
    assert "#define SHDLC_API __declspec(dllexport)" in src
    assert '#define SHDLC_API __attribute__((visibility("default")))' in src
    # Fallback: empty definition.
    assert "\n#define SHDLC_API\n" in src


# --- hot-path purity ---------------------------------------------------------------


def test_step_and_tick_bodies_are_cold_path_free():
    src = generate_c(passthrough_circuit())
    step = _body(src, "SHDLC_API void step(")
    for forbidden in ("strcmp", "fprintf", "malloc", "if ("):
        assert forbidden not in step, forbidden
    assert "tick();" in step
    assert "for (i = 0; i < cycles; i++)" in step
    tick = _body(src, "static void tick(void)")
    for forbidden in ("strcmp", "fprintf", "malloc", "if (", "for (", "while ("):
        assert forbidden not in tick, forbidden


def test_strcmp_only_in_poke_and_peek():
    src = generate_c(and_circuit())
    total = src.count("strcmp")
    in_poke = _body(src, "SHDLC_API void poke(").count("strcmp")
    in_peek = _body(src, "SHDLC_API uint64_t peek(").count("strcmp")
    assert in_poke == 1
    assert in_peek == 2  # output scan + input scan
    assert total == in_poke + in_peek


# --- determinism / no provenance ----------------------------------------------------


def test_no_timestamps_paths_or_versions():
    src = generate_c(and_circuit())
    assert not re.search(r"\b20\d\d\b", src), "looks like a year/timestamp"
    assert ".py" not in src
    assert "shdlc/" not in src
    assert "/Users" not in src
    assert not re.search(r"\bv?\d+\.\d+\.\d+\b", src), "looks like a version"


def test_double_call_is_byte_identical():
    for circuit in (and_circuit(), feedback_circuit(), passthrough_circuit(), empty_circuit()):
        assert generate_c(circuit) == generate_c(circuit)


def test_render_ends_with_newline_and_no_trailing_whitespace():
    src = generate_c(feedback_circuit())
    assert src.endswith("\n")
    assert not any(ln != ln.rstrip() for ln in src.splitlines())
