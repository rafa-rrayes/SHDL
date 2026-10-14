"""Phase 6 — hierarchy flattening (shdl.md §12, base_shdl.md §3).

Inlines every user component into the top, prefixing instance names
(``fa1`` containing ``x1`` becomes ``fa1_x1``), and resolves every connection
to a terminal driver by walking alias chains: every non-top component port
bit is an alias node, and each sink (gate input pin, top output bit) resolves
its driver by chasing the chain back to a terminal source (a gate output, a
power pin, or a top input bit). Pass-through components are chains of pure
aliases; a connection loop containing no gate is an error (E0506).

Emission order is hierarchical DFS source order: child components are inlined
at their declaration point, then the component's own per-bit connections
follow in source order — each emitting exactly one final connection per sink
it defines.

Also collected here: the hierarchy tree, source map, merged constants
metadata, and resolved init seeds — everything positional that the metadata
section needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..diagnostics import ErrorCode, err
from ..source import Pos
from .constants import LoweredComponent
from .expander import BitRef, ConstBit, InstBit, PortBit, primary_bits
from .monomorphize import MonoProgram

# A node in the global connection graph:
#   ("in", wire)              top-level input port bit
#   ("out", wire)             top-level output port bit
#   ("pin", gate, pin)        a primitive gate pin ("A"/"B"/"O")
#   ("alias", path, port, bit) a port bit of a non-top component instance
type Node = tuple


@dataclass(frozen=True, slots=True)
class FlatGate:
    name: str
    type_name: str
    decl_pos: Pos  # the defining primitive declaration site
    chain: tuple[Pos, ...]  # instantiation sites, root -> leaf


@dataclass(slots=True)
class FlatNetlist:
    name: str
    inputs: list[str]  # wire names, port order then LSB-first
    outputs: list[str]
    input_groups: dict[str, list[str]]  # user port name -> wires
    output_groups: dict[str, list[str]]
    gates: dict[str, FlatGate] = field(default_factory=dict)
    connections: list[tuple[Node, Node, Pos]] = field(default_factory=list)


@dataclass(slots=True)
class FlatResult:
    netlist: FlatNetlist
    hierarchy: dict
    source_map_gates: dict[str, dict]
    source_map_lines: dict[str, dict[str, list[str]]]
    constants: dict[str, dict]
    init: dict[str, int]


def node_str(node: Node) -> str:
    match node:
        case ("in", wire) | ("out", wire):
            return wire
        case ("pin", gate, pin):
            return f"{gate}.{pin}"
        case ("alias", path, port, bit):  # pragma: no cover - internal only
            return f"{'.'.join(path)}.{port}[{bit}]"
    raise AssertionError(node)  # pragma: no cover


def top_wire(name: str, bit: int, width: int) -> str:
    """Base SHDL bus-expansion naming (base_shdl.md §3.4)."""
    return name if width == 1 else f"{name}_{bit}_"


def flatten(mono: MonoProgram, lowered: dict[str, LoweredComponent]) -> FlatResult:
    top = lowered[mono.top_key]
    top_ec = top.ec

    input_groups = {
        name: [top_wire(name, b, w) for b in range(1, w + 1)] for name, w in top_ec.inputs
    }
    output_groups = {
        name: [top_wire(name, b, w) for b in range(1, w + 1)] for name, w in top_ec.outputs
    }
    netlist = FlatNetlist(
        name=top_ec.name,
        inputs=[w for wires in input_groups.values() for w in wires],
        outputs=[w for wires in output_groups.values() for w in wires],
        input_groups=input_groups,
        output_groups=output_groups,
    )

    incoming: dict[Node, tuple[Node, Pos]] = {}
    emission: list[tuple[Node, Node, Pos]] = []  # (dst sink, raw src, pos)
    # DFS-ordered records used after the graph is complete:
    comp_instances: list[tuple[tuple[str, ...], str, dict]] = []  # (path, key, ports_meta)
    init_jobs: list[tuple[tuple[str, ...], str, str]] = []  # (path, key, prefix)
    constants_meta: dict[str, dict] = {}

    def add_gate(name: str, type_name: str, decl_pos: Pos, chain: tuple[Pos, ...]) -> None:
        if name in netlist.gates:
            raise err(
                ErrorCode.E0308,
                f"flattened gate name '{name}' collides with an existing gate "
                f"(declared at {netlist.gates[name].decl_pos})",
                decl_pos,
            )
        if name in netlist.inputs or name in netlist.outputs:
            raise err(
                ErrorCode.E0308,
                f"flattened gate name '{name}' collides with a top-level port",
                decl_pos,
            )
        netlist.gates[name] = FlatGate(name, type_name, decl_pos, chain)

    def node_of(ref: BitRef, path: tuple[str, ...], prefix: str, lc: LoweredComponent) -> Node:
        ec = lc.ec
        match ref:
            case PortBit(name=name, bit=bit):
                if path == ():
                    width = ec.port_width(name)
                    wire = top_wire(name, bit, width)
                    return ("in", wire) if ec.port_dir(name) == "in" else ("out", wire)
                return ("alias", path, name, bit)
            case InstBit(inst=inst, port=port, bit=bit):
                info = ec.instances.get(inst)
                if info is None:  # a phase-5 power pin
                    assert inst in lc.const_gates, inst
                    return ("pin", prefix + inst, port)
                if info.kind == "prim":
                    return ("pin", prefix + inst, port)
                return ("alias", (*path, inst), port, bit)
            case ConstBit():  # pragma: no cover - removed in phase 5
                raise AssertionError(ref)
        raise AssertionError(ref)  # pragma: no cover

    def walk(key: str, path: tuple[str, ...], prefix: str, chain: tuple[Pos, ...]) -> dict:
        lc = lowered[key]
        ec = lc.ec
        instances_meta: dict[str, dict] = {}

        for info in ec.instances.values():
            if info.kind == "prim":
                gate_name = prefix + info.name
                add_gate(gate_name, info.type_ref, info.pos, chain)
                instances_meta[info.name] = {"type": info.type_ref, "gate": gate_name}
            else:
                child_prefix = f"{prefix}{info.name}_"
                child_path = (*path, info.name)
                child_meta = walk(
                    info.type_ref, child_path, child_prefix, (*chain, info.pos)
                )
                entry: dict = {"type": info.display_type}
                if info.bindings:
                    entry["params"] = dict(info.bindings)
                entry["source_file"] = info.pos.file
                entry["source_line"] = info.pos.line
                entry["prefix"] = child_prefix
                entry["ports"] = {}  # filled after the graph is complete
                entry["instances"] = child_meta
                instances_meta[info.name] = entry
                comp_instances.append((child_path, info.type_ref, entry["ports"]))

        for cg in lc.const_gates.values():
            gate_name = prefix + cg.name
            add_gate(gate_name, cg.type_name, cg.pos, chain)
            instances_meta[cg.name] = {"type": cg.type_name, "gate": gate_name}

        for const_name, meta in lc.const_meta.items():
            constants_meta[prefix + const_name] = {
                "value": meta["value"],
                "width": meta["width"],
                "bits": {bit: prefix + gate for bit, gate in meta["bits"].items()},
            }

        for bc in lc.bit_conns:
            src_node = node_of(bc.src, path, prefix, lc)
            dst_node = node_of(bc.dst, path, prefix, lc)
            if dst_node in incoming:
                raise err(
                    ErrorCode.E0501,
                    f"'{node_str(dst_node)}' is driven more than once "
                    f"(first driver at {incoming[dst_node][1]})",
                    bc.pos,
                )
            incoming[dst_node] = (src_node, bc.pos)
            if dst_node[0] in ("pin", "out"):
                emission.append((dst_node, src_node, bc.pos))

        if ec.init:
            init_jobs.append((path, key, prefix))
        return instances_meta

    top_instances_meta = walk(mono.top_key, (), "", ())
    hierarchy = {
        top_ec.name: {
            "source_file": top_ec.def_pos.file,
            "source_line": top_ec.def_pos.line,
            "instances": top_instances_meta,
        }
    }

    # ---- driver resolution -------------------------------------------------- #

    resolve_memo: dict[Node, Node] = {}

    def resolve(node: Node, at: Pos) -> Node:
        seen: list[Node] = []
        cur = node
        while True:
            if cur in resolve_memo:
                terminal = resolve_memo[cur]
                break
            if cur[0] in ("in",) or (cur[0] == "pin" and cur[2] == "O"):
                terminal = cur
                break
            if cur in seen:
                raise err(
                    ErrorCode.E0506,
                    f"connection cycle with no gate through '{node_str(cur)}'",
                    at,
                )
            seen.append(cur)
            entry = incoming.get(cur)
            if entry is None:
                # Per-component validation makes this unreachable for valid
                # graphs; kept as a defensive backstop.
                raise err(
                    ErrorCode.E0502,
                    f"'{node_str(cur)}' is never driven",
                    at,
                )
            cur = entry[0]
        for n in seen:
            resolve_memo[n] = terminal
        return terminal

    for dst_node, src_node, pos in emission:
        terminal = resolve(src_node, pos)
        netlist.connections.append((terminal, dst_node, pos))

    # ---- canonical wire naming (for hierarchy ports and init keys) --------- #
    # A net is named by its top-level port wire if its alias class contains
    # one, else by its driving gate pin "gate.O" (matches base_shdl.md §4.4).

    driver_to_top_out: dict[Node, str] = {}
    for wire in netlist.outputs:
        entry = incoming.get(("out", wire))
        if entry is None:  # pragma: no cover - per-component checks catch this
            raise err(
                ErrorCode.E0503,
                f"output '{wire}' is never driven",
                top_ec.def_pos,
            )
        terminal = resolve(entry[0], entry[1])
        driver_to_top_out.setdefault(terminal, wire)

    def canonical(terminal: Node) -> str:
        if terminal[0] == "in":
            return terminal[1]
        return driver_to_top_out.get(terminal, node_str(terminal))

    for path, key, ports_meta in comp_instances:
        spec = mono.specs[key]
        for name, width in [*spec.inputs, *spec.outputs]:
            wires = [
                canonical(resolve(("alias", path, name, bit), spec.comp.pos))
                for bit in range(1, width + 1)
            ]
            ports_meta[name] = wires[0] if width == 1 else wires

    # ---- init seeds (shdl.md §11.4 -> base_shdl.md §4.11) ------------------- #

    init_out: dict[str, int] = {}
    seeded: dict[Node, tuple[int, Pos]] = {}
    for path, key, prefix in init_jobs:
        lc = lowered[key]
        ec = lc.ec
        for target, value, pos in ec.init:
            _check_init_target(ec, mono, target, pos)
            bits = primary_bits(ec, mono, target)
            if value >= (1 << len(bits)):
                raise err(
                    ErrorCode.E0A03,
                    f"init value {value} does not fit the {len(bits)}-bit "
                    f"target '{_target_str(target)}'",
                    pos,
                )
            for i, ref in enumerate(bits):
                bit_value = (value >> i) & 1
                node = node_of(ref, path, prefix, lc)
                terminal = resolve(node, pos)
                if terminal[0] == "in":
                    raise err(
                        ErrorCode.E0A01,
                        f"init target '{_target_str(target)}' resolves to "
                        f"input '{terminal[1]}'; inputs are set by poke, not init",
                        pos,
                    )
                if terminal in seeded:
                    raise err(
                        ErrorCode.E0A02,
                        f"net '{canonical(terminal)}' is seeded more than once "
                        f"(first seed at {seeded[terminal][1]})",
                        pos,
                    )
                seeded[terminal] = (bit_value, pos)
                init_out[canonical(terminal)] = bit_value

    # ---- source map --------------------------------------------------------- #

    sm_gates: dict[str, dict] = {}
    # Buckets are dicts used as ordered sets: loop-generated hardware maps
    # tens of thousands of gates onto one source line, so membership must be
    # O(1), and first-insertion order is part of the emitted byte format.
    line_buckets: dict[str, dict[str, dict[str, None]]] = {}

    def add_line(file: str, line: int, gate: str) -> None:
        line_buckets.setdefault(file, {}).setdefault(str(line), {})[gate] = None

    for gate in netlist.gates.values():
        sm_gates[gate.name] = {
            "file": gate.decl_pos.file,
            "line": gate.decl_pos.line,
            "column": gate.decl_pos.col,
        }
        add_line(gate.decl_pos.file, gate.decl_pos.line, gate.name)
        for pos in gate.chain:
            add_line(pos.file, pos.line, gate.name)

    sm_lines = {
        file: {
            line: list(gates)
            for line, gates in sorted(lines.items(), key=lambda kv: int(kv[0]))
        }
        for file, lines in sorted(line_buckets.items())
    }

    return FlatResult(
        netlist=netlist,
        hierarchy=hierarchy,
        source_map_gates=sm_gates,
        source_map_lines=sm_lines,
        constants=constants_meta,
        init=init_out,
    )


def _check_init_target(ec, mono: MonoProgram, target, pos: Pos) -> None:
    """An init target must be drivable: an instance output or an output port
    (shdl.md §11.4); never an input, never a constant."""
    if target.port is not None:
        from .expand import instance_port_dir

        d = instance_port_dir(ec, mono, target.base, target.port, pos)
        if d != "out":
            raise err(
                ErrorCode.E0A01,
                f"init target '{_target_str(target)}' is an instance input; "
                "only instance outputs and output ports can be seeded",
                pos,
            )
        return
    if target.base in ec.constants:
        raise err(
            ErrorCode.E0A01,
            f"init target '{target.base}' is a constant",
            pos,
        )
    d = ec.port_dir(target.base)
    if d == "in":
        raise err(
            ErrorCode.E0A01,
            f"init target '{target.base}' is an input port; inputs are set "
            "by poke, not init",
            pos,
        )
    if d is None:
        # Unknown name -> canonical E0307 via the width lookup.
        from .expand import signal_width

        signal_width(ec, mono, target.base, None, pos)


def _target_str(target) -> str:
    s = target.base if target.port is None else f"{target.base}.{target.port}"
    match target.index:
        case ("bit", k):
            return f"{s}[{k}]"
        case ("slice", a, b):
            return f"{s}[{a}:{b}]"
    return s
