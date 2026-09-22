"""C code generation from a validated :class:`~shdlc.model.Circuit`.

``generate_c`` is pure and byte-deterministic: the same Circuit always yields
the same C source, with no timestamps, paths, or versions embedded.

The emitted translation unit implements the unit-delay, two-buffer
compute/commit simulation model (shdl.md §11, shdlc_goals.md §2.3): every
gate reads only the previous cycle's committed values (``cur[]`` for gate
outputs, ``inputs[]`` for poked input ports) and writes ``nxt[]``; the commit
is a pointer swap. One gate level advances per tick — the netlist is never
topologically settled — so feedback circuits work with no special handling.

State is bit-packed (shdlc_goals.md §5.2): :mod:`shdlc.layout` assigns every
gate a lane of a ``uint64_t`` word, and one C statement evaluates all the
gates of a word at once. Each operand is gathered from the previous cycle's
words as an OR of *groups* -- an aligned shift of one source word, or one
source bit broadcast across lanes -- masked only where stray bits could reach
a lane the word uses. Unused lanes are kept 0 in both buffers, so the
whole-state ``memcmp`` that detects a fixed point stays exact. An input port
is one word (``poke`` masks the value to the port width); output ports are
gathered lazily on ``peek``/``run_batch``.

Circuits above :data:`_TICK_CHUNK` words emit their statements into noinline
chunk functions with restrict parameters instead of one giant ``tick()`` body
(the generated C carries the rationale); at or below the threshold the output
is byte-identical to the unchunked form. Init seeds are emitted as a static
table that ``reset()`` loops over, never per-seed stores, for the same reason.
"""

from __future__ import annotations

from . import layout
from .layout import Gather, Group, Word
from .model import Circuit

#: C bitwise operator for each two-input primitive.
_BINARY_OPS = {"AND": "&", "OR": "|", "XOR": "^"}

#: Split tick() into noinline chunk functions of this many word statements
#: when the circuit has more words than this; at or below it the emission is
#: unchanged (byte-identical output for small circuits).
_TICK_CHUNK = 64


def _count(n: int, noun: str) -> str:
    """``3 gates`` / ``1 gate`` — for the header comment."""
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _hex(mask: int) -> str:
    return f"0x{mask:016X}ULL"


def _group_expr(g: Group, c: str, inputs: str) -> str:
    """C rvalue of one gather group (previous-cycle values)."""
    base = f"{c}[{g.index}]" if g.array == "c" else f"{inputs}[{g.index}]"
    if g.bcast:
        bit = f"(({base} >> {g.shift}) & 1u)" if g.shift else f"({base} & 1u)"
        if g.masked:
            return f"({bit} * {_hex(g.lanes)})"
        return f"(0u - {bit})"
    if g.shift > 0:
        term = f"({base} >> {g.shift})"
    elif g.shift < 0:
        term = f"({base} << {-g.shift})"
    else:
        term = base
    if g.masked:
        return f"({term} & {_hex(g.lanes)})"
    return term


def _gather_expr(groups: tuple[Group, ...], c: str, inputs: str) -> str:
    """OR of the groups as a balanced tree (short dependency chains)."""
    if not groups:
        return "0ULL"
    terms = [_group_expr(g, c, inputs) for g in groups]
    while len(terms) > 1:
        terms = [
            f"({terms[i]} | {terms[i + 1]})" if i + 1 < len(terms) else terms[i]
            for i in range(0, len(terms), 2)
        ]
    return terms[0]


def _word_expr(word: Word, c: str, inputs: str) -> str:
    """Right-hand side of a word's compute statement."""
    t = word.type
    if t in _BINARY_OPS:
        a = _gather_expr(word.a, c, inputs)
        b = _gather_expr(word.b, c, inputs)
        expr = f"{a} {_BINARY_OPS[t]} {b}"
        return f"({expr}) & {_hex(word.mask)}" if word.masked else expr
    if t == "NOT":
        a = _gather_expr(word.a, c, inputs)
        return f"~{a} & {_hex(word.mask)}" if word.masked else f"~{a}"
    if t == "VCC":
        return _hex(word.mask)
    if t == "GND":
        return "0ULL"
    # Unreachable from user input: parse_base rejects unknown primitive names
    # and Circuit validation re-checks gate types before codegen runs (ROB-1).
    raise AssertionError(f"unknown gate type: {word.type!r}")  # pragma: no cover


def _out_expr(gather: Gather) -> str:
    expr = _gather_expr(gather.groups, "cur", "inputs")
    return f"{expr} & {_hex(gather.mask)}" if gather.masked else expr


def _word_stmt(word: Word, n: str, w: int, c: str, inputs: str) -> str:
    return f"    {n}[{w}] = {_word_expr(word, c, inputs)}; /* {word.type} {word.label}[{len(word.gates)}] */"


def _reads(words: tuple[Word, ...], array: str) -> bool:
    """True iff any word's operand reads ``array`` (``"c"`` or ``"in"``)."""
    return any(g.array == array for word in words for g in word.a + word.b)


def generate_c(circuit: Circuit) -> str:
    """Render ``circuit`` as a complete, self-contained C translation unit.

    The generated file implements the unit-delay two-buffer simulation model
    (shdl.md §11) and exports exactly the release ABI ``reset``/``poke``/
    ``peek``/``step`` plus the additive batch-and-settle entries
    ``step_settle``/``run_batch`` (shdlc_goals.md §3.1); everything else is
    static.
    """
    plan = layout.plan(circuit)
    words = plan.words
    ng = len(circuit.gates)
    nw = len(words)
    nip = len(circuit.in_ports)
    nop = len(circuit.out_ports)
    chunks: list[tuple[int, tuple[Word, ...]]] = []
    if nw > _TICK_CHUNK:
        chunks = [(k, words[k : k + _TICK_CHUNK]) for k in range(0, nw, _TICK_CHUNK)]

    out: list[str] = []
    w = out.append

    # --- 1. Header comment (name + counts only: byte-determinism). --------
    w(
        f"/* {circuit.name}: {_count(ng, 'gate')} in {_count(nw, 'word')}, "
        f"{_count(nip, 'input port')}, {_count(nop, 'output port')}. */"
    )
    w("")

    # --- 2. Includes and the export-visibility macro. ----------------------
    w("#include <stdint.h>")
    w("#include <stdio.h>")
    w("#include <string.h>")
    w("")
    w("#if defined(_WIN32)")
    w("#define SHDLC_API __declspec(dllexport)")
    w("#elif defined(__GNUC__)")
    w('#define SHDLC_API __attribute__((visibility("default")))')
    w("#else")
    w("#define SHDLC_API")
    w("#endif")
    w("")
    if chunks:
        w("/* Keeps the tick chunk functions out of line; rationale above them. */")
        w("#if defined(__GNUC__)")
        w("#define SHDLC_NOINLINE __attribute__((noinline))")
        w("#elif defined(_MSC_VER)")
        w("#define SHDLC_NOINLINE __declspec(noinline)")
        w("#else")
        w("#define SHDLC_NOINLINE")
        w("#endif")
        w("")

    # --- 3. Index enums. ----------------------------------------------------
    w("/* Input port words: bit b of inputs[IN_p] is bit b of the poked value. */")
    w("enum {")
    for i, port in enumerate(circuit.in_ports):
        w(f"    IN_{port.name} = {i},")
    w(f"    NUM_IN_PORTS = {nip}")
    w("};")
    w("")
    w("/* Gate bits, in declaration order: word * 64 + lane of cur[]/nxt[]. */")
    w("enum {")
    for i, gate in enumerate(circuit.gates):
        word, lane = plan.place[i]
        w(f"    G_{gate.name} = {word * layout.LANES + lane}, /* {gate.type} */")
    w(f"    NUM_GATES = {ng}")
    w("};")
    w("")
    w("/* State words (64 gate bits each). */")
    w("enum {")
    w(f"    NUM_WORDS = {nw}")
    w("};")
    w("")
    w("/* Output port slots. */")
    w("enum {")
    for i, port in enumerate(circuit.out_ports):
        w(f"    OUT_{port.name} = {i},")
    w(f"    NUM_OUT_PORTS = {nop}")
    w("};")
    w("")

    # --- 4. Simulation state (array sizes clamped to 1: pedantic C11). -----
    w("/*")
    w(" * Simulation state. Gate outputs are double-buffered: every cycle reads")
    w(" * cur[] and writes nxt[], then the buffers swap (shdlc_goals.md §2.3).")
    w(" * Lanes no gate uses are 0 in both buffers.")
    w(" */")
    w(f"static uint64_t inputs[{max(1, nip)}];")
    w(f"static uint64_t buf_a[{max(1, nw)}];")
    w(f"static uint64_t buf_b[{max(1, nw)}];")
    w("static uint64_t *cur = buf_a;")
    w("static uint64_t *nxt = buf_b;")
    w("static int dirty = 0;")
    w("")

    # --- 5. Port tables. ----------------------------------------------------
    w("struct in_port {")
    w("    const char *name;")
    w("    uint64_t mask; /* the port's width, as a bit mask */")
    w("};")
    w("")
    if nip > 0:
        w("static const struct in_port in_ports[] = {")
        rows = [
            f'    {{ "{port.name}", {_hex((1 << len(port.refs)) - 1)} }}'
            for port in circuit.in_ports
        ]
        w(",\n".join(rows))
        w("};")
    else:
        w("/* No input ports; one dummy entry keeps the table valid C11. */")
        w("static const struct in_port in_ports[1] = {")
        w('    { "", 0 }')
        w("};")
    w("")
    if nop > 0:
        w("/* Output port names, aligned with the OUT_ indices. */")
        w("static const char *const out_port_names[] = {")
        w(",\n".join(f'    "{port.name}"' for port in circuit.out_ports))
        w("};")
    else:
        w("/* No output ports; one dummy entry keeps the table valid C11. */")
        w("static const char *const out_port_names[1] = {")
        w('    ""')
        w("};")
    w("")

    # --- 6. gather_out and tick. --------------------------------------------
    w("/*")
    w(" * Pack output port q's bits (LSB first) from the committed state;")
    w(" * passthrough output bits read inputs[] directly. Gathered on demand")
    w(" * by peek()/run_batch(), never inside the cycle loop.")
    w(" */")
    w("static uint64_t gather_out(int q)")
    w("{")
    if nop == 0:
        w("    (void)q;")
        w("    return 0ULL;")
    else:
        w("    switch (q) {")
        for i, port in enumerate(circuit.out_ports):
            w(f"    case OUT_{port.name}:")
            w(f"        return {_out_expr(plan.outputs[i])};")
        w("    default:")
        w("        return 0ULL;")
        w("    }")
    w("}")
    w("")
    if chunks:
        w("/*")
        w(" * The word statements live in noinline chunk functions instead of one")
        w(" * giant tick() body: a single huge basic block sends the compiler's")
        w(" * instruction scheduler quadratic. The restrict parameters assert the")
        w(" * read buffers and the write buffer are disjoint, and noinline keeps")
        w(" * each scheduling region small (single-call statics would otherwise be")
        w(" * re-inlined, reconstructing the giant block). Every chunk reads only")
        w(" * c[]/in[] (the committed cycle) and writes only n[], so the split")
        w(" * cannot change semantics; chunks take only the arrays they read.")
        w(" */")
        for k, (start, chunk) in enumerate(chunks):
            params = []
            if _reads(chunk, "c"):
                params.append("const uint64_t *restrict c")
            if _reads(chunk, "in"):
                params.append("const uint64_t *restrict in")
            params.append("uint64_t *restrict n")
            w("SHDLC_NOINLINE")
            w(f"static void tick_chunk_{k}({', '.join(params)})")
            w("{")
            for j, word in enumerate(chunk):
                w(_word_stmt(word, "n", start + j, "c", "in"))
            w("}")
            w("")
    w("/*")
    w(" * One unit-delay cycle (shdl.md §11, shdlc_goals.md §2.3): every word")
    w(" * reads only the previous cycle's values (cur[]/inputs[]) and writes")
    w(" * nxt[]; the commit is a pointer swap, so no gate observes a same-cycle")
    w(" * update and feedback advances one gate level per cycle. Hot path: no")
    w(" * allocation, no string ops, no branches on signal values.")
    w(" */")
    w("static void tick(void)")
    w("{")
    w("    uint64_t *tmp;")
    w("")
    if chunks:
        for k, (_, chunk) in enumerate(chunks):
            args = []
            if _reads(chunk, "c"):
                args.append("cur")
            if _reads(chunk, "in"):
                args.append("inputs")
            args.append("nxt")
            w(f"    tick_chunk_{k}({', '.join(args)});")
        w("")
    else:
        for i, word in enumerate(words):
            w(_word_stmt(word, "nxt", i, "cur", "inputs"))
        if nw > 0:
            w("")
    w("    tmp = cur;")
    w("    cur = nxt;")
    w("    nxt = tmp;")
    w("    dirty = 0;")
    w("}")
    w("")

    # --- 7. The four ABI functions, then the load-time constructor. --------
    if circuit.init:
        w("/* Init seeds applied by reset(), as data: per-seed stores would")
        w(" * rebuild the giant-basic-block problem the tick chunks avoid. */")
        w("static const struct init_seed {")
        w("    uint32_t word;")
        w("    uint8_t lane;")
        w("    uint8_t value;")
        w("} init_seeds[] = {")
        for gate_index, bit in circuit.init:
            word, lane = plan.place[gate_index]
            w(f"    {{ {word}u, {lane}u, {bit}u }}, /* {circuit.gates[gate_index].name} */")
        w("};")
        w("")
    w("/*")
    w(" * Return to cycle 0 (shdlc_goals.md §2.4): all state zero, buffers")
    w(" * re-pinned (idempotent), then init seeds applied to cur[] only so")
    w(" * VCC/GND still read 0 until the first tick.")
    w(" */")
    w("SHDLC_API void reset(void)")
    w("{")
    if circuit.init:
        w("    size_t i;")
        w("")
    w("    memset(inputs, 0, sizeof(inputs));")
    w("    memset(buf_a, 0, sizeof(buf_a));")
    w("    memset(buf_b, 0, sizeof(buf_b));")
    w("    cur = buf_a;")
    w("    nxt = buf_b;")
    if circuit.init:
        w("    for (i = 0; i < sizeof(init_seeds) / sizeof(init_seeds[0]); i++) {")
        w("        cur[init_seeds[i].word] |= (uint64_t)init_seeds[i].value << init_seeds[i].lane;")
        w("    }")
    w("    dirty = 0;")
    w("}")
    w("")
    w("/* Set an input port; the value is masked to the port width. */")
    w("SHDLC_API void poke(const char *signal, uint64_t value)")
    w("{")
    w("    int i;")
    w("")
    w("    /* NULL takes the unknown-signal path; no name comparison on it. */")
    w("    if (signal != 0) {")
    w("        for (i = 0; i < NUM_IN_PORTS; i++) {")
    w("            if (strcmp(signal, in_ports[i].name) == 0) {")
    w("                inputs[i] = value & in_ports[i].mask;")
    w("                dirty = 1;")
    w("                return;")
    w("            }")
    w("        }")
    w("    }")
    w('    fprintf(stderr, "poke: unknown signal \\"%s\\"\\n",')
    w('            signal != 0 ? signal : "(null)");')
    w("}")
    w("")
    w("/* Read a port. Outputs are scanned first and trigger one lazy tick per")
    w(" * poke-batch (tick clears dirty); inputs read inputs[] and never")
    w(" * tick. */")
    w("SHDLC_API uint64_t peek(const char *signal)")
    w("{")
    w("    int i;")
    w("")
    w("    /* NULL takes the unknown-signal path; no name comparison on it. */")
    w("    if (signal != 0) {")
    w("        for (i = 0; i < NUM_OUT_PORTS; i++) {")
    w("            if (strcmp(signal, out_port_names[i]) == 0) {")
    w("                if (dirty) {")
    w("                    tick();")
    w("                }")
    w("                return gather_out(i);")
    w("            }")
    w("        }")
    w("        for (i = 0; i < NUM_IN_PORTS; i++) {")
    w("            if (strcmp(signal, in_ports[i].name) == 0) {")
    w("                return inputs[i];")
    w("            }")
    w("        }")
    w("    }")
    w('    fprintf(stderr, "peek: unknown signal \\"%s\\"\\n",')
    w('            signal != 0 ? signal : "(null)");')
    w("    return 0u;")
    w("}")
    w("")
    # step()/step_settle() are exported, so on ELF their names live in the
    # global symbol namespace -- and the exported step() collides with libc's
    # legacy regex step@GLIBC_2.2.5. An internal call to step() from run_batch()
    # would bind to that interposing libc symbol (a SIGSEGV: it reads the int
    # cycles as a regex program pointer). Routing every internal call through
    # these static impls keeps the cross-references out of the global namespace,
    # so they always bind locally; the exported names stay thin wrappers.
    w("/* Advance exactly `cycles` unit-delay cycles; <= 0 naturally no-ops")
    w(" * and dirty is untouched. */")
    w("static void step_impl(int cycles)")
    w("{")
    w("    int i;")
    w("")
    w("    for (i = 0; i < cycles; i++) {")
    w("        tick();")
    w("    }")
    w("}")
    w("")
    w("static int step_settle_impl(int cycles)")
    w("{")
    w("    int i;")
    w("")
    w("    for (i = 0; i < cycles; i++) {")
    w("        tick();")
    w("        if (memcmp(cur, nxt, sizeof(buf_a)) == 0) {")
    w("            return i + 1;")
    w("        }")
    w("    }")
    w("    return i;")
    w("}")
    w("")
    w("SHDLC_API void step(int cycles)")
    w("{")
    w("    step_impl(cycles);")
    w("}")
    w("")
    w("/* step(cycles) with fixed-point early exit: once a tick changes no")
    w(" * gate, every further tick recomputes the identical state (inputs are")
    w(" * held between ticks), so stopping is observably identical. After a")
    w(" * tick the swapped-out nxt[] still holds the previous cycle, so one")
    w(" * memcmp detects the fixed point; oscillators never compare equal and")
    w(" * run all `cycles`. Returns the number of ticks actually run. */")
    w("SHDLC_API int step_settle(int cycles)")
    w("{")
    w("    return step_settle_impl(cycles);")
    w("}")
    w("")
    w("/*")
    w(" * Drive `count` input frames through the circuit in one call. Frame k")
    w(" * pokes in[k*NUM_IN_PORTS + p] into input port p (declaration order,")
    w(" * poke semantics), advances `cycles` cycles -- exactly when `settle`")
    w(" * is 0, with fixed-point early exit when nonzero -- then gathers each")
    w(" * output port into out[k*NUM_OUT_PORTS + q] with peek semantics,")
    w(" * including the lazy tick when `cycles` <= 0 leaves pokes pending.")
    w(" * Observably identical to the same poke/step/peek calls made one by")
    w(" * one; `in`/`out` are not dereferenced when their dimension is zero.")
    w(" */")
    w("SHDLC_API void run_batch(const uint64_t *in, uint64_t *out,")
    w("                         int count, int cycles, int settle)")
    w("{")
    w("    int k;")
    w("    int i;")
    w("")
    w("    for (k = 0; k < count; k++) {")
    w("        for (i = 0; i < NUM_IN_PORTS; i++) {")
    w("            inputs[i] = in[(size_t)k * NUM_IN_PORTS + (size_t)i] & in_ports[i].mask;")
    w("            dirty = 1;")
    w("        }")
    w("        if (settle) {")
    w("            (void)step_settle_impl(cycles);")
    w("        } else {")
    w("            step_impl(cycles);")
    w("        }")
    w("        for (i = 0; i < NUM_OUT_PORTS; i++) {")
    w("            if (dirty) {")
    w("                tick();")
    w("            }")
    w("            out[(size_t)k * NUM_OUT_PORTS + (size_t)i] = gather_out(i);")
    w("        }")
    w("    }")
    w("}")
    w("")
    w("/* Make init seeds live at load time, before any explicit reset(). */")
    w("#ifdef __GNUC__")
    w("__attribute__((constructor)) static void shdlc_ctor(void)")
    w("{")
    w("    reset();")
    w("}")
    w("#endif")

    return "\n".join(out) + "\n"
