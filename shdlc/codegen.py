"""C code generation from a validated :class:`~shdlc.model.Circuit`.

``generate_c`` is pure and byte-deterministic: the same Circuit always yields
the same C source, with no timestamps, paths, or versions embedded.

The emitted translation unit implements the unit-delay, two-buffer
compute/commit simulation model (shdl.md §11, shdlc_goals.md §2.3): every
gate reads only the previous cycle's committed values (``cur[]`` for gate
outputs, ``inputs[]`` for poked input wires) and writes ``nxt[]``; the commit
is a pointer swap. One gate level advances per tick — the netlist is never
topologically settled — so feedback circuits work with no special handling.
"""

from __future__ import annotations

from .model import Circuit, Gate, Ref

#: C bitwise operator for each two-input primitive.
_BINARY_OPS = {"AND": "&", "OR": "|", "XOR": "^"}

#: Wrap an ``in_wires_*`` initializer onto multiple lines past this length.
_WIRE_LINE_LIMIT = 80


def _count(n: int, noun: str) -> str:
    """``3 gates`` / ``1 gate`` — for the header comment."""
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _src(circuit: Circuit, ref: Ref) -> str:
    """C rvalue for a resolved signal source (previous-cycle value)."""
    if ref.kind == "in":
        return f"inputs[IN_{circuit.inputs[ref.index]}]"
    return f"cur[G_{circuit.gates[ref.index].name}]"


def _gate_expr(circuit: Circuit, gate: Gate) -> str:
    """Right-hand side of the per-gate compute statement."""
    if gate.type in _BINARY_OPS:
        assert gate.a is not None and gate.b is not None
        op = _BINARY_OPS[gate.type]
        return f"(uint8_t)({_src(circuit, gate.a)} {op} {_src(circuit, gate.b)})"
    if gate.type == "NOT":
        assert gate.a is not None
        return f"(uint8_t)({_src(circuit, gate.a)} ^ 1u)"
    if gate.type == "VCC":
        return "1u"
    if gate.type == "GND":
        return "0u"
    raise ValueError(f"unknown gate type: {gate.type!r}")


def _wire_array_lines(port_name: str, wire_names: list[str]) -> list[str]:
    """Declaration of one input port's wire-index array, LSB first."""
    decl = f"static const uint16_t in_wires_{port_name}[] = "
    single = decl + "{ " + ", ".join(wire_names) + " };"
    if len(single) <= _WIRE_LINE_LIMIT:
        return [single]
    lines = [decl + "{"]
    for i in range(0, len(wire_names), 8):
        chunk = ", ".join(wire_names[i : i + 8])
        comma = "," if i + 8 < len(wire_names) else ""
        lines.append(f"    {chunk}{comma}")
    lines.append("};")
    return lines


def generate_c(circuit: Circuit) -> str:
    """Render ``circuit`` as a complete, self-contained C translation unit.

    The generated file implements the unit-delay two-buffer simulation model
    (shdl.md §11) and exports exactly the release ABI ``reset``/``poke``/
    ``peek``/``step`` (shdlc_goals.md §2); everything else is static.
    """
    ni = len(circuit.inputs)
    ng = len(circuit.gates)
    nip = len(circuit.in_ports)
    nop = len(circuit.out_ports)

    out: list[str] = []
    w = out.append

    # --- 1. Header comment (name + counts only: byte-determinism). --------
    w(
        f"/* {circuit.name}: {_count(ng, 'gate')}, "
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

    # --- 3. Index enums. ----------------------------------------------------
    w("/* Input wire slots. */")
    w("enum {")
    for i, name in enumerate(circuit.inputs):
        w(f"    IN_{name} = {i},")
    w(f"    NUM_INPUTS = {ni}")
    w("};")
    w("")
    w("/* Gate slots, in declaration order. */")
    w("enum {")
    for i, gate in enumerate(circuit.gates):
        w(f"    G_{gate.name} = {i}, /* {gate.type} */")
    w(f"    NUM_GATES = {ng}")
    w("};")
    w("")
    w("/* Output port slots: indices into out_vals[]. */")
    w("enum {")
    for i, port in enumerate(circuit.out_ports):
        w(f"    OUT_{port.name} = {i},")
    w(f"    NUM_OUT_PORTS = {nop}")
    w("};")
    w("")
    w("/* Input port count (NUM_INPUTS counts wires; a port may be multi-bit). */")
    w("enum {")
    w(f"    NUM_IN_PORTS = {nip}")
    w("};")
    w("")

    # --- 4. Simulation state (array sizes clamped to 1: pedantic C11). -----
    w("/*")
    w(" * Simulation state. Gate outputs are double-buffered: every cycle reads")
    w(" * cur[] and writes nxt[], then the buffers swap (shdlc_goals.md §2.3).")
    w(" */")
    w(f"static uint8_t inputs[{max(1, ni)}];")
    w(f"static uint8_t buf_a[{max(1, ng)}];")
    w(f"static uint8_t buf_b[{max(1, ng)}];")
    w("static uint8_t *cur = buf_a;")
    w("static uint8_t *nxt = buf_b;")
    w("static int dirty = 0;")
    w(f"static uint64_t out_vals[{max(1, nop)}];")
    w("")

    # --- 5. Port tables. ----------------------------------------------------
    if nip > 0:
        w("/* Input ports: bit b of a poked value lands on wires[b] (LSB first). */")
        for port in circuit.in_ports:
            names = [f"IN_{circuit.inputs[ref.index]}" for ref in port.refs]
            for line in _wire_array_lines(port.name, names):
                w(line)
        w("")
    w("struct in_port {")
    w("    const char *name;")
    w("    int width;")
    w("    const uint16_t *wires;")
    w("};")
    w("")
    if nip > 0:
        w("static const struct in_port in_ports[] = {")
        rows = [
            f'    {{ "{port.name}", {len(port.refs)}, in_wires_{port.name} }}'
            for port in circuit.in_ports
        ]
        w(",\n".join(rows))
        w("};")
    else:
        w("/* No input ports; one dummy entry keeps the table valid C11. */")
        w("static const struct in_port in_ports[1] = {")
        w('    { "", 0, 0 }')
        w("};")
    w("")
    if nop > 0:
        w("/* Output port names, aligned with out_vals[] / the OUT_ indices. */")
        w("static const char *const out_port_names[] = {")
        w(",\n".join(f'    "{port.name}"' for port in circuit.out_ports))
        w("};")
    else:
        w("/* No output ports; one dummy entry keeps the table valid C11. */")
        w("static const char *const out_port_names[1] = {")
        w('    ""')
        w("};")
    w("")

    # --- 6. recompute_outputs and tick. ------------------------------------
    w("/*")
    w(" * Pack each output port's bits (LSB first) from the committed state;")
    w(" * passthrough output bits read inputs[] directly. Runs after every")
    w(" * commit so out_vals[] always mirrors the visible cycle.")
    w(" */")
    w("static void recompute_outputs(void)")
    w("{")
    if nop == 0:
        w("    /* No output ports. */")
    for port in circuit.out_ports:
        terms = [
            f"((uint64_t){_src(circuit, ref)} << {bit})"
            for bit, ref in enumerate(port.refs)
        ]
        head = f"    out_vals[OUT_{port.name}] = {terms[0]}"
        if len(terms) == 1:
            w(head + ";")
        else:
            w(head)
            for term in terms[1:-1]:
                w(f"        | {term}")
            w(f"        | {terms[-1]};")
    w("}")
    w("")
    w("/*")
    w(" * One unit-delay cycle (shdl.md §11, shdlc_goals.md §2.3): every gate")
    w(" * reads only the previous cycle's values (cur[]/inputs[]) and writes")
    w(" * nxt[]; the commit is a pointer swap, so no gate observes a same-cycle")
    w(" * update and feedback advances one gate level per cycle. Hot path: no")
    w(" * allocation, no string ops, no branches on signal values.")
    w(" */")
    w("static void tick(void)")
    w("{")
    w("    uint8_t *tmp;")
    w("")
    for gate in circuit.gates:
        w(
            f"    nxt[G_{gate.name}] = {_gate_expr(circuit, gate)};"
            f" /* {gate.name}: {gate.type} */"
        )
    if ng > 0:
        w("")
    w("    tmp = cur;")
    w("    cur = nxt;")
    w("    nxt = tmp;")
    w("    recompute_outputs();")
    w("    dirty = 0;")
    w("}")
    w("")

    # --- 7. The four ABI functions, then the load-time constructor. --------
    w("/*")
    w(" * Return to cycle 0 (shdlc_goals.md §2.4): all state zero, buffers")
    w(" * re-pinned (idempotent), then init seeds applied to cur[] only so")
    w(" * VCC/GND still read 0 until the first tick.")
    w(" */")
    w("SHDLC_API void reset(void)")
    w("{")
    w("    memset(inputs, 0, sizeof(inputs));")
    w("    memset(buf_a, 0, sizeof(buf_a));")
    w("    memset(buf_b, 0, sizeof(buf_b));")
    w("    cur = buf_a;")
    w("    nxt = buf_b;")
    for gate_index, bit in circuit.init:
        gate_name = circuit.gates[gate_index].name
        w(f"    cur[G_{gate_name}] = {bit}u; /* init: {gate_name} = {bit} */")
    w("    dirty = 0;")
    w("    recompute_outputs();")
    w("}")
    w("")
    w("/* Set an input port; the per-bit scatter masks the value to the port")
    w(" * width for free (max shift 63, so no width-64 shift exists). */")
    w("SHDLC_API void poke(const char *signal, uint64_t value)")
    w("{")
    w("    int i;")
    w("    int b;")
    w("")
    w("    for (i = 0; i < NUM_IN_PORTS; i++) {")
    w("        if (strcmp(signal, in_ports[i].name) == 0) {")
    w("            for (b = 0; b < in_ports[i].width; b++) {")
    w("                inputs[in_ports[i].wires[b]] = (uint8_t)((value >> b) & 1u);")
    w("            }")
    w("            dirty = 1;")
    w("            return;")
    w("        }")
    w("    }")
    w('    fprintf(stderr, "poke: unknown signal \\"%s\\"\\n", signal);')
    w("}")
    w("")
    w("/* Read a port. Outputs are scanned first and trigger one lazy tick per")
    w(" * poke-batch (tick clears dirty); inputs gather from inputs[] and never")
    w(" * tick. */")
    w("SHDLC_API uint64_t peek(const char *signal)")
    w("{")
    w("    int i;")
    w("    int b;")
    w("    uint64_t v;")
    w("")
    w("    for (i = 0; i < NUM_OUT_PORTS; i++) {")
    w("        if (strcmp(signal, out_port_names[i]) == 0) {")
    w("            if (dirty) {")
    w("                tick();")
    w("            }")
    w("            return out_vals[i];")
    w("        }")
    w("    }")
    w("    for (i = 0; i < NUM_IN_PORTS; i++) {")
    w("        if (strcmp(signal, in_ports[i].name) == 0) {")
    w("            v = 0u;")
    w("            for (b = 0; b < in_ports[i].width; b++) {")
    w("                v |= (uint64_t)inputs[in_ports[i].wires[b]] << b;")
    w("            }")
    w("            return v;")
    w("        }")
    w("    }")
    w('    fprintf(stderr, "peek: unknown signal \\"%s\\"\\n", signal);')
    w("    return 0u;")
    w("}")
    w("")
    w("/* Advance exactly `cycles` unit-delay cycles; <= 0 naturally no-ops")
    w(" * and dirty is untouched. */")
    w("SHDLC_API void step(int cycles)")
    w("{")
    w("    int i;")
    w("")
    w("    for (i = 0; i < cycles; i++) {")
    w("        tick();")
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
