"""Structural tests for :func:`shdlc.codegen.generate_c`.

String/structure assertions only: the generated C is never compiled here
(integration tests elsewhere own that), and circuits are built by hand from
the :mod:`shdlc.model` dataclasses — no conftest fixtures, no meta JSON.
The pinned word statements double as the emission rules' documentation:
shift / broadcast gathers, and masks only where junk could reach a used lane.
"""

from __future__ import annotations

import re

from shdlc.codegen import _TICK_CHUNK, generate_c
from shdlc.layout import LANES
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


def fanout_circuit(gate_type: str) -> Circuit:
    """Three gates ANDing/ORing one shared select bit with a 3-bit bus."""
    return _circuit(
        name="Fanout",
        inputs=("s", "d0", "d1", "d2"),
        gates=tuple(Gate(f"a{k}", gate_type, _in(0), _in(1 + k)) for k in range(3)),
        outputs=("y0", "y1", "y2"),
        in_ports=(PortGroup("S", (_in(0),)), PortGroup("D", (_in(1), _in(2), _in(3)))),
        out_ports=(PortGroup("Y", (_g(0), _g(1), _g(2))),),
    )


def ring_circuit(n: int) -> Circuit:
    """n NOT gates in a ring: gate i reads gate i-1, gate 0 reads gate n-1."""
    gates = tuple(Gate(f"n{i}", "NOT", _g((i - 1) % n), None) for i in range(n))
    return _circuit(name="Ring", gates=gates, outputs=("o",), out_ports=(PortGroup("o", (_g(0),)),))


def empty_circuit() -> Circuit:
    return _circuit(name="Empty")


def wide_circuit() -> Circuit:
    """64-bit identity port pair: a full-width passthrough."""
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


def _word_stmts(body: str) -> list[str]:
    """The word statements of a tick/chunk body (``nxt[w] = ...`` / ``n[w] = ...``)."""
    return [ln.strip() for ln in body.splitlines() if re.match(r"\s*(nxt|n)\[\d+\] = ", ln)]


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
        "NUM_WORDS = 1",
        "OUT_o = 0",
        "static uint64_t inputs[",
        "static uint64_t buf_a[",
        "struct in_port",
        "static const struct in_port in_ports[",
        "static const char *const out_port_names[",
        "static uint64_t gather_out(int q)",
        "static void tick(void)",
        "SHDLC_API void reset(void)",
        "SHDLC_API void poke(const char *signal, uint64_t value)",
        "SHDLC_API uint64_t peek(const char *signal)",
        "SHDLC_API void step(int cycles)",
        "SHDLC_API int step_settle(int cycles)",
        "SHDLC_API void run_batch(const uint64_t *in, uint64_t *out,",
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
    assert first == "/* AndGate: 1 gate in 1 word, 2 input ports, 1 output port. */"


def test_counts_in_enums():
    src = generate_c(and_circuit())
    assert "NUM_GATES = 1" in src
    assert "NUM_WORDS = 1" in src
    assert "NUM_OUT_PORTS = 1" in src
    assert "NUM_IN_PORTS = 2" in src


def test_gate_enum_is_word_times_64_plus_lane():
    src = generate_c(ring_circuit(70))
    # 70 loose NOT gates fill word 0 and spill into word 1.
    assert "G_n0 = 0, /* NOT */" in src
    assert "G_n63 = 63, /* NOT */" in src
    assert f"G_n64 = {LANES}, /* NOT */" in src
    assert "NUM_WORDS = 2" in src


# --- word statements ----------------------------------------------------------


def test_one_statement_per_word_with_type_and_count_comment():
    src = generate_c(feedback_circuit())
    tick = _body(src, "static void tick(void)")
    stmts = _word_stmts(tick)
    # Both inverters share one word: lane 0 reads lane 1 (shift +1), lane 1
    # reads lane 0 (shift -1); NOT sets the unused lanes, so the word is masked.
    assert stmts == [
        "nxt[0] = ~((cur[0] >> 1) | (cur[0] << 1)) & 0x0000000000000003ULL; /* NOT n[2] */"
    ]


def test_binary_operators_and_aligned_gathers_need_no_mask():
    src = generate_c(and_circuit())
    assert "nxt[0] = inputs[0] & inputs[1]; /* AND g[1] */" in src
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
    assert "nxt[0] = inputs[0] | inputs[1]; /* OR o[1] */" in src
    assert "nxt[1] = cur[0] ^ inputs[1]; /* XOR x[1] */" in src


def test_not_is_complement_masked_to_used_lanes():
    src = generate_c(not_circuit())
    assert "nxt[0] = ~inputs[0] & 0x0000000000000001ULL; /* NOT n[1] */" in src
    # A NOT word using all 64 lanes needs no mask; the ring also shows the
    # maximum shift (lane 0 reads lane 63).
    src = generate_c(ring_circuit(64))
    assert "nxt[0] = ~((cur[0] << 1) | (cur[0] >> 63)); /* NOT n[64] */" in src


def test_broadcast_is_unmasked_under_and_but_masked_under_or():
    # The select bit fans out to every lane: one broadcast term. Its junk in
    # the unused lanes is absorbed by the AND with the clean bus operand ...
    src = generate_c(fanout_circuit("AND"))
    assert "nxt[0] = (0u - (inputs[0] & 1u)) & inputs[1]; /* AND a[3] */" in src
    # ... but would leak through an OR, so that word is masked.
    src = generate_c(fanout_circuit("OR"))
    assert (
        "nxt[0] = ((0u - (inputs[0] & 1u)) | inputs[1]) & 0x0000000000000007ULL; /* OR a[3] */"
        in src
    )


def test_vcc_gnd_emit_lane_masks():
    src = generate_c(power_circuit())
    assert "nxt[0] = 0x0000000000000001ULL; /* VCC p[1] */" in src
    assert "nxt[1] = 0ULL; /* GND z[1] */" in src


def test_tick_commit_is_pointer_swap_then_dirty():
    src = generate_c(and_circuit())
    tick = _body(src, "static void tick(void)")
    swap = tick.index("tmp = cur;")
    assert tick.index("cur = nxt;") > swap
    assert tick.index("nxt = tmp;") > tick.index("cur = nxt;")
    assert tick.index("dirty = 0;") > tick.index("nxt = tmp;")
    # All word computes happen before the commit.
    last_assign = max(tick.index(ln) for ln in _word_stmts(tick))
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
    # Seeds are data (word, lane, value), applied to cur[] by one loop.
    assert "{ 0u, 0u, 1u }, /* n1 */" in src
    assert "{ 0u, 1u, 0u }, /* n2 */" in src
    seed = "cur[init_seeds[i].word] |= (uint64_t)init_seeds[i].value << init_seeds[i].lane;"
    assert seed in reset
    assert "nxt[init_seeds" not in reset
    # Order: memsets -> re-pin -> seed loop -> dirty=0.
    assert (
        reset.index("memset(buf_b")
        < reset.index("cur = buf_a;")
        < reset.index("cur[init_seeds[i].word]")
        < reset.index("dirty = 0;")
    )
    # The table preserves seed order and lives before reset().
    assert src.index("/* n1 */") < src.index("/* n2 */")
    assert src.index("init_seeds[] = {") < src.index("SHDLC_API void reset(void)")
    # Seeds live only in reset, never in tick.
    assert "init_seeds" not in _body(src, "static void tick(void)")


def test_init_seeds_absent_without_init():
    src = generate_c(and_circuit())
    assert "init_seeds" not in src
    reset = _body(src, "SHDLC_API void reset(void)")
    assert "cur[" not in reset


# --- dirty discipline ---------------------------------------------------------


def test_dirty_handling():
    src = generate_c(and_circuit())
    # Set on every input write: poke, and run_batch's per-port loop.
    assert src.count("dirty = 1;") == 2
    assert "dirty = 1;" in _body(src, "SHDLC_API void poke(")
    assert "dirty = 1;" in _body(src, "SHDLC_API void run_batch(")
    assert "static int dirty = 0;" in src
    assert src.count("    dirty = 0;") == 2  # statements, not the declaration
    assert "dirty = 0;" in _body(src, "static void tick(void)")
    assert "dirty = 0;" in _body(src, "SHDLC_API void reset(void)")
    # Lazy-tick checks: peek's output branch, and run_batch's output gather.
    assert src.count("if (dirty)") == 2
    assert "if (dirty)" in _body(src, "SHDLC_API uint64_t peek(")
    assert "if (dirty)" in _body(src, "SHDLC_API void run_batch(")
    assert "if (dirty)" not in _body(src, "SHDLC_API void step(")
    assert "if (dirty)" not in _body(src, "SHDLC_API int step_settle(")


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
    assert "return gather_out(i);" in peek
    # An input port is one word: read back as poked.
    assert "return inputs[i];" in peek


def test_poke_masks_to_port_width_and_unknown_paths():
    src = generate_c(passthrough_circuit())
    poke = _body(src, "SHDLC_API void poke(")
    assert "strcmp(signal, in_ports[i].name)" in poke
    assert "inputs[i] = value & in_ports[i].mask;" in poke
    # Unknown-name diagnostics exist in poke and peek, after the scans.
    assert poke.count("fprintf(stderr") == 1
    peek = _body(src, "SHDLC_API uint64_t peek(")
    assert peek.count("fprintf(stderr") == 1
    assert peek.strip().endswith("return 0u;")


def test_outputs_are_gathered_on_demand():
    src = generate_c(passthrough_circuit())
    gather = _body(src, "static uint64_t gather_out(int q)")
    # Echo is the whole 3-bit input word; NotD1 is lane 0 of word 0 (no
    # other lane is used, so neither needs a mask).
    assert "case OUT_Echo:\n        return inputs[0];" in gather
    assert "case OUT_NotD1:\n        return cur[0];" in gather
    # Never recomputed per tick: the cycle loop only computes and swaps.
    assert "gather_out" not in _body(src, "static void tick(void)")
    assert "gather_out" not in _body(src, "static void step_impl(")
    src = generate_c(fanout_circuit("AND"))
    assert "case OUT_Y:\n        return cur[0];" in _body(src, "static uint64_t gather_out(int q)")


# --- multi-bit ports -----------------------------------------------------------


def test_multibit_port_mask():
    src = generate_c(passthrough_circuit())
    assert '{ "D", 0x0000000000000007ULL }' in src
    src = generate_c(wide_circuit())
    assert '{ "W", 0xFFFFFFFFFFFFFFFFULL }' in src
    assert "case OUT_E:\n        return inputs[0];" in src


def test_no_width_64_shift_anywhere():
    for circuit in (and_circuit(), passthrough_circuit(), wide_circuit(), ring_circuit(64)):
        src = generate_c(circuit)
        assert "<< 64" not in src
        assert ">> 64" not in src
    assert ">> 63)" in generate_c(ring_circuit(64))


# --- degenerate circuits --------------------------------------------------------


def test_degenerate_empty_circuit():
    src = generate_c(empty_circuit())
    assert not re.search(r"^static .*\[0\];", src, re.M), "zero-sized array"
    assert "static uint64_t inputs[1];" in src
    assert "static uint64_t buf_a[1];" in src
    assert "static uint64_t buf_b[1];" in src
    assert "NUM_GATES = 0" in src
    assert "NUM_WORDS = 0" in src
    assert "NUM_OUT_PORTS = 0" in src
    assert "NUM_IN_PORTS = 0" in src
    # Dummy 1-element tables guarded by the count constants.
    assert "static const struct in_port in_ports[1]" in src
    assert '{ "", 0 }' in src
    assert "static const char *const out_port_names[1]" in src
    gather = _body(src, "static uint64_t gather_out(int q)")
    assert "(void)q;" in gather
    assert "case OUT_" not in gather
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
    assert not re.search(r"^static .*\[0\];", src, re.M), "zero-sized array"
    assert "static uint64_t inputs[1];" in src
    assert "static uint64_t buf_a[2];" in src
    assert "NUM_IN_PORTS = 0" in src
    assert '{ "", 0 }' in src
    assert "nxt[0] = 0x0000000000000001ULL;" in src


def test_degenerate_no_output_ports():
    circuit = _circuit(
        name="Sink",
        inputs=("a",),
        gates=(Gate("n", "NOT", _in(0), None),),
        in_ports=(PortGroup("a", (_in(0),)),),
    )
    src = generate_c(circuit)
    assert not re.search(r"^static .*\[0\];", src, re.M), "zero-sized array"
    assert "NUM_OUT_PORTS = 0" in src
    assert "static const char *const out_port_names[1]" in src
    gather = _body(src, "static uint64_t gather_out(int q)")
    assert "case OUT_" not in gather


def test_uncovered_input_wire_reads_zero():
    # No port covers wire b: the operand has no source and is the constant 0.
    circuit = _circuit(
        name="Stuck",
        inputs=("a", "b"),
        gates=(Gate("g", "OR", _in(0), _in(1)),),
        outputs=("o",),
        in_ports=(PortGroup("a", (_in(0),)),),
        out_ports=(PortGroup("o", (_g(0),)),),
    )
    src = generate_c(circuit)
    assert "nxt[0] = inputs[0] | 0ULL; /* OR g[1] */" in src


# --- visibility / ABI surface ----------------------------------------------------


def test_shdlc_api_on_exactly_the_six_abi_functions():
    src = generate_c(and_circuit())
    api_lines = [ln for ln in src.splitlines() if ln.startswith("SHDLC_API")]
    assert api_lines == [
        "SHDLC_API void reset(void)",
        "SHDLC_API void poke(const char *signal, uint64_t value)",
        "SHDLC_API uint64_t peek(const char *signal)",
        "SHDLC_API void step(int cycles)",
        "SHDLC_API int step_settle(int cycles)",
        "SHDLC_API void run_batch(const uint64_t *in, uint64_t *out,",
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
    # step_impl holds the per-cycle hot loop; the exported step() is a thin
    # wrapper over it (the indirection keeps run_batch's internal call off the
    # interposable global symbol -- on ELF an exported step() collides with
    # libc's legacy regex step()).
    step = _body(src, "static void step_impl(")
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


# --- chunked tick (circuits above _TICK_CHUNK words) --------------------------


def chain_circuit(n: int) -> Circuit:
    """NOT-chain: gate 0 reads the input, gate i reads gate i-1 (64 per word)."""
    gates = [Gate("g0", "NOT", _in(0), None)]
    gates.extend(Gate(f"g{i}", "NOT", _g(i - 1), None) for i in range(1, n))
    return _circuit(
        name="Chain",
        inputs=("a",),
        gates=tuple(gates),
        outputs=("o",),
        in_ports=(PortGroup("a", (_in(0),)),),
        out_ports=(PortGroup("o", (_g(n - 1),)),),
    )


def input_only_circuit(n: int) -> Circuit:
    """n AND gates all reading input wires: no gate-output (c[]) read anywhere."""
    return _circuit(
        name="Flat",
        inputs=("a", "b"),
        gates=tuple(Gate(f"g{i}", "AND", _in(0), _in(1)) for i in range(n)),
        outputs=("o",),
        in_ports=(PortGroup("a", (_in(0),)), PortGroup("b", (_in(1),))),
        out_ports=(PortGroup("o", (_g(n - 1),)),),
    )


#: Gates that exactly fill _TICK_CHUNK words.
_CHUNK_GATES = _TICK_CHUNK * LANES

_CHUNK_SIG = "static void tick_chunk_{}({})"
_C_IN_N = "const uint64_t *restrict c, const uint64_t *restrict in, uint64_t *restrict n"
_C_N = "const uint64_t *restrict c, uint64_t *restrict n"
_IN_N = "const uint64_t *restrict in, uint64_t *restrict n"


def test_at_threshold_emits_inline_tick():
    src = generate_c(chain_circuit(_CHUNK_GATES))
    assert f"NUM_WORDS = {_TICK_CHUNK}" in src
    assert "tick_chunk_" not in src
    assert "SHDLC_NOINLINE" not in src
    assert "restrict" not in src
    tick = _body(src, "static void tick(void)")
    assert len(_word_stmts(tick)) == _TICK_CHUNK


def test_above_threshold_emits_chunks_full_then_remainder():
    src = generate_c(chain_circuit(_CHUNK_GATES + 1))
    assert f"NUM_WORDS = {_TICK_CHUNK + 1}" in src
    assert src.count("SHDLC_NOINLINE\nstatic void tick_chunk_") == 2
    assert "tick_chunk_2" not in src
    # Chunk 0 holds the word that reads the input; chunk 1 reads only c[].
    stmts0 = _word_stmts(_body(src, _CHUNK_SIG.format(0, _C_IN_N)))
    stmts1 = _word_stmts(_body(src, _CHUNK_SIG.format(1, _C_N)))
    assert len(stmts0) == _TICK_CHUNK
    assert len(stmts1) == 1
    # Every word statement appears exactly once, in word order.
    found = re.findall(r"(?<![A-Za-z_])n\[(\d+)\] =", src)
    assert found == [str(w) for w in range(_TICK_CHUNK + 1)]
    tick = _body(src, "static void tick(void)")
    assert (
        tick.index("tick_chunk_0(cur, inputs, nxt);")
        < tick.index("tick_chunk_1(cur, nxt);")
        < tick.index("tmp = cur;")
    )


def test_input_only_chunks_take_in_and_n_only():
    src = generate_c(input_only_circuit(_CHUNK_GATES + 1))
    # No unused-parameter bait: c never appears in any chunk signature.
    assert "restrict c" not in src
    assert _CHUNK_SIG.format(0, _IN_N) in src
    assert _CHUNK_SIG.format(1, _IN_N) in src
    tick = _body(src, "static void tick(void)")
    assert "tick_chunk_0(inputs, nxt);" in tick
    assert "tick_chunk_1(inputs, nxt);" in tick
    assert "(cur" not in tick


def test_chain_crossing_chunk_boundary_reads_previous_cycle_value():
    src = generate_c(chain_circuit(_CHUNK_GATES + 1))
    first = _word_stmts(_body(src, _CHUNK_SIG.format(1, _C_N)))[0]
    # The cross-chunk read targets c[] (the committed previous cycle), so the
    # chunk split cannot change semantics regardless of call order.
    assert first == (
        f"n[{_TICK_CHUNK}] = ~(c[{_TICK_CHUNK - 1}] >> 63) & 0x0000000000000001ULL; /* NOT g[1] */"
    )


def test_noinline_macro_block_present_iff_chunked():
    src = generate_c(chain_circuit(_CHUNK_GATES + 1))
    for line in (
        "#if defined(__GNUC__)",
        "#define SHDLC_NOINLINE __attribute__((noinline))",
        "#elif defined(_MSC_VER)",
        "#define SHDLC_NOINLINE __declspec(noinline)",
    ):
        assert line in src, line
    # Placed after the SHDLC_API block, before the chunk functions.
    assert (
        src.index("#define SHDLC_API")
        < src.index("#define SHDLC_NOINLINE")
        < src.index("static void tick_chunk_0")
    )
    for small in (chain_circuit(_CHUNK_GATES), and_circuit(), empty_circuit()):
        assert "SHDLC_NOINLINE" not in generate_c(small)


def test_chunked_emission_is_deterministic():
    assert generate_c(chain_circuit(_CHUNK_GATES + 1)) == generate_c(
        chain_circuit(_CHUNK_GATES + 1)
    )
