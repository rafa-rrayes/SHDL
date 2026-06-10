"""Validated circuit model: the seam between Base SHDL parsing and codegen.

``build_circuit`` turns a parsed :class:`~shdlc.baseshdl.BaseComponent` into a
:class:`Circuit` — a fully resolved, index-based netlist — rejecting every
malformed input with a :class:`ModelError`. Codegen consumes only ``Circuit``
and may assume all invariants below hold; in particular it never sees
output-alias chains (they are resolved to ultimate drivers here) and never
sees ``meta`` JSON.

Invariants established (each violation is a distinct ModelError):

1. Names are unique across inputs, outputs, and gates.
2. Every dotted connection endpoint is a known ``gate.PIN``; a connection
   source must be ``gate.O`` or an input/output wire; a bare destination must
   be an output-port wire (driving an input wire is an error).
3. Pin arity matches the primitive: AND/OR/XOR take exactly {A, B}; NOT takes
   exactly {A}; VCC/GND take none.
4. Exactly one driver per (gate, pin) and per output wire.
5. No floating gate input pins; no undriven output wires.
6. Output-alias chains (output wire -> output wire) resolve transitively to an
   ultimate driver (a gate or an input wire); alias cycles are an error.
7. ``meta.ports``, when present, names existing wires of the right direction,
   port names are unique identifiers across inputs+outputs, widths are 1..64.
   When absent, identity single-bit groups are synthesized from the header.
8. ``meta.init`` keys are ``gate.O`` or output-port wires whose alias chain
   ends at a driving gate (an input-wire passthrough is an error); values are
   0 or 1; two keys may not seed the same gate.

All sequences are ordered deterministically by parse / JSON insertion order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .baseshdl import BaseComponent

#: Gate type names as they appear in :class:`Gate.type`. Base SHDL spells the
#: power primitives ``__VCC__``/``__GND__``; the model normalizes them.
GATE_TYPES = ("AND", "OR", "XOR", "NOT", "VCC", "GND")


class ModelError(ValueError):
    """A Base SHDL artifact that parses but violates a structural rule."""


@dataclass(frozen=True, slots=True)
class Ref:
    """A resolved signal source: an input wire slot or a gate output slot."""

    kind: str  # "in" | "gate"
    index: int


@dataclass(frozen=True, slots=True)
class Gate:
    """One gate slot. ``a``/``b`` are the resolved sources of pins A and B.

    NOT uses only ``a``; VCC/GND use neither (both None).
    """

    name: str
    type: str  # one of GATE_TYPES
    a: Ref | None
    b: Ref | None


@dataclass(frozen=True, slots=True)
class PortGroup:
    """A named multi-bit port: ``refs`` are its bits, LSB first."""

    name: str
    refs: tuple[Ref, ...]


@dataclass(frozen=True, slots=True)
class Circuit:
    """A validated, fully resolved netlist ready for codegen.

    - ``inputs``: input wire names; position = input slot index.
    - ``gates``: gate slots in declaration order; position = gate slot index.
    - ``outputs``: output wire names from the header (kept for reporting).
    - ``in_ports``: user-facing input ports; every ref has kind "in".
    - ``out_ports``: user-facing output ports; refs are ultimate drivers,
      kind "gate" or (for input passthrough) kind "in".
    - ``init``: ``(gate_index, bit)`` seeds applied by reset, in meta order.
    """

    name: str
    inputs: tuple[str, ...]
    gates: tuple[Gate, ...]
    outputs: tuple[str, ...]
    in_ports: tuple[PortGroup, ...]
    out_ports: tuple[PortGroup, ...]
    init: tuple[tuple[int, int], ...]


#: Required input pins per normalized gate type (invariant 3).
_INPUT_PINS: dict[str, tuple[str, ...]] = {
    "AND": ("A", "B"),
    "OR": ("A", "B"),
    "XOR": ("A", "B"),
    "NOT": ("A",),
    "VCC": (),
    "GND": (),
}

#: Base SHDL spellings of the power primitives -> model spellings.
_NORMALIZE = {"__VCC__": "VCC", "__GND__": "GND"}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Port-width ceiling imposed by the uint64_t poke/peek ABI.
_MAX_PORT_WIDTH = 64

#: Input-wire ceiling imposed by the uint16_t wire-index tables in the
#: generated C; beyond it the table initializers would silently truncate
#: under release cflags (no -Werror).
_MAX_INPUT_WIRES = 0xFFFF


def build_circuit(comp: BaseComponent) -> Circuit:
    """Validate ``comp`` and lower it to a :class:`Circuit`.

    Raises :class:`ModelError` with a human-readable message naming the
    offending construct for any violation of the module invariants.
    """
    # --- invariant 1: name uniqueness across inputs, outputs, gates -------
    region: dict[str, str] = {}

    def declare(name: str, kind: str) -> None:
        if name in region:
            raise ModelError(f"duplicate name {name!r}: declared as {region[name]} and {kind}")
        region[name] = kind

    if len(comp.inputs) > _MAX_INPUT_WIRES:
        raise ModelError(
            f"too many input wires ({len(comp.inputs)}): the generated C "
            f"indexes input wires with uint16_t (max {_MAX_INPUT_WIRES})"
        )
    for name in comp.inputs:
        declare(name, "input")
    for name in comp.outputs:
        declare(name, "output")
    gate_types: dict[str, str] = {}
    for name, raw_type in comp.gates.items():
        declare(name, "gate")
        normalized = _NORMALIZE.get(raw_type, raw_type)
        if normalized not in GATE_TYPES:
            raise ModelError(f"gate {name!r}: unknown primitive type {raw_type!r}")
        gate_types[name] = normalized

    in_slot = {name: i for i, name in enumerate(comp.inputs)}
    gate_slot = {name: i for i, name in enumerate(comp.gates)}
    gate_names = list(comp.gates)
    out_set = set(comp.outputs)

    # --- invariants 2-4: endpoint resolution, pin validity, single driver -
    pin_src: dict[tuple[str, str], str] = {}
    out_src: dict[str, str] = {}
    for src, dst in comp.connections:
        if "." in src:
            gate, _, pin = src.partition(".")
            if gate not in gate_types:
                raise ModelError(f"unknown gate {gate!r} in connection source {src!r}")
            if pin != "O":
                raise ModelError(
                    f"connection source {src!r}: only pin 'O' of gate {gate!r} is readable"
                )
        elif src in in_slot or src in out_set:
            pass
        elif src in gate_types:
            raise ModelError(
                f"connection source {src!r} is a gate; read its output as '{src}.O'"
            )
        else:
            raise ModelError(f"unknown connection source {src!r}")

        if "." in dst:
            gate, _, pin = dst.partition(".")
            if gate not in gate_types:
                raise ModelError(f"unknown gate {gate!r} in connection destination {dst!r}")
            type_name = gate_types[gate]
            pins = _INPUT_PINS[type_name]
            if not pins:
                raise ModelError(
                    f"connection destination {dst!r}: {type_name} gate {gate!r} "
                    "takes no pin connections"
                )
            if pin not in pins:
                raise ModelError(
                    f"connection destination {dst!r}: {type_name} gate {gate!r} "
                    f"has no input pin {pin!r}"
                )
            if (gate, pin) in pin_src:
                raise ModelError(f"pin {dst!r} driven more than once")
            pin_src[(gate, pin)] = src
        elif dst in out_set:
            if dst in out_src:
                raise ModelError(f"output wire {dst!r} driven more than once")
            out_src[dst] = src
        elif dst in in_slot:
            raise ModelError(f"cannot drive input wire {dst!r}")
        elif dst in gate_types:
            raise ModelError(
                f"connection destination {dst!r} is a gate, not an output wire"
            )
        else:
            raise ModelError(f"unknown connection destination {dst!r}")

    # --- invariant 5: no floating gate pins, no undriven output wires -----
    for gate, type_name in gate_types.items():
        for pin in _INPUT_PINS[type_name]:
            if (gate, pin) not in pin_src:
                raise ModelError(f"gate {gate!r}: {type_name} input pin {pin!r} is not driven")
    for name in comp.outputs:
        if name not in out_src:
            raise ModelError(f"output wire {name!r} is not driven")

    # --- invariant 6: resolve output-alias chains to ultimate drivers -----
    resolved: dict[str, Ref] = {}

    def resolve_out(wire: str) -> Ref:
        chain: list[str] = []
        seen: set[str] = set()
        current = wire
        while True:
            if current in resolved:
                ref = resolved[current]
                break
            if current in seen:
                cycle = chain[chain.index(current) :] + [current]
                raise ModelError("output alias cycle: " + " -> ".join(cycle))
            seen.add(current)
            chain.append(current)
            src = out_src[current]
            if "." in src:
                ref = Ref("gate", gate_slot[src.partition(".")[0]])
                break
            if src in in_slot:
                ref = Ref("in", in_slot[src])
                break
            current = src  # src is an output wire: follow the alias
        for name in chain:
            resolved[name] = ref
        return ref

    for name in comp.outputs:  # eager: detect cycles even on unreferenced wires
        resolve_out(name)

    def resolve_src(src: str) -> Ref:
        if "." in src:
            return Ref("gate", gate_slot[src.partition(".")[0]])
        if src in in_slot:
            return Ref("in", in_slot[src])
        return resolve_out(src)

    gates: list[Gate] = []
    for gate, type_name in gate_types.items():
        pins = _INPUT_PINS[type_name]
        a = resolve_src(pin_src[(gate, "A")]) if "A" in pins else None
        b = resolve_src(pin_src[(gate, "B")]) if "B" in pins else None
        gates.append(Gate(name=gate, type=type_name, a=a, b=b))

    # --- invariant 7: port groups ------------------------------------------
    if "ports" in comp.meta:
        ports_meta = comp.meta["ports"]
        if not isinstance(ports_meta, dict):
            raise ModelError("meta.ports must be a JSON object")
        port_names: set[str] = set()

        def build_group(direction: str) -> tuple[PortGroup, ...]:
            group = ports_meta.get(direction, {})
            if not isinstance(group, dict):
                raise ModelError(f"meta.ports.{direction} must be a JSON object")
            result: list[PortGroup] = []
            for port_name, wires in group.items():
                if not isinstance(port_name, str) or not _IDENT.fullmatch(port_name):
                    raise ModelError(f"port name {port_name!r} is not an identifier")
                if port_name in port_names:
                    raise ModelError(f"duplicate port name {port_name!r}")
                port_names.add(port_name)
                if not isinstance(wires, list) or not all(
                    isinstance(w, str) for w in wires
                ):
                    raise ModelError(f"port {port_name!r}: wires must be an array of wire names")
                if not 1 <= len(wires) <= _MAX_PORT_WIDTH:
                    raise ModelError(
                        f"port {port_name!r}: width {len(wires)} out of range "
                        f"1..{_MAX_PORT_WIDTH}"
                    )
                refs: list[Ref] = []
                for wire in wires:
                    if direction == "inputs":
                        if wire in in_slot:
                            refs.append(Ref("in", in_slot[wire]))
                        elif wire in out_set:
                            raise ModelError(
                                f"port {port_name!r}: wire {wire!r} is an output wire, "
                                "not an input wire"
                            )
                        else:
                            raise ModelError(f"port {port_name!r}: unknown wire {wire!r}")
                    else:
                        if wire in out_set:
                            refs.append(resolve_out(wire))
                        elif wire in in_slot:
                            raise ModelError(
                                f"port {port_name!r}: wire {wire!r} is an input wire, "
                                "not an output wire"
                            )
                        else:
                            raise ModelError(f"port {port_name!r}: unknown wire {wire!r}")
                result.append(PortGroup(name=port_name, refs=tuple(refs)))
            return tuple(result)

        in_ports = build_group("inputs")
        out_ports = build_group("outputs")
    else:
        in_ports = tuple(
            PortGroup(name=name, refs=(Ref("in", i),)) for i, name in enumerate(comp.inputs)
        )
        out_ports = tuple(
            PortGroup(name=name, refs=(resolve_out(name),)) for name in comp.outputs
        )

    # --- invariant 8: init seeds -------------------------------------------
    init_entries: list[tuple[int, int]] = []
    if "init" in comp.meta:
        init_meta = comp.meta["init"]
        if not isinstance(init_meta, dict):
            raise ModelError("meta.init must be a JSON object")
        seeded: dict[int, str] = {}
        for key, value in init_meta.items():
            if type(value) is not int or value not in (0, 1):
                raise ModelError(f"init {key!r}: value must be 0 or 1, got {value!r}")
            if "." in key:
                gate, _, pin = key.partition(".")
                if gate not in gate_slot:
                    raise ModelError(f"init key {key!r}: unknown gate {gate!r}")
                if pin != "O":
                    raise ModelError(f"init key {key!r}: only 'gate.O' may be seeded")
                index = gate_slot[gate]
            elif key in out_set:
                ref = resolve_out(key)
                if ref.kind != "gate":
                    raise ModelError(
                        f"init key {key!r}: resolves to input wire "
                        f"{comp.inputs[ref.index]!r}, not a driving gate"
                    )
                index = ref.index
            else:
                raise ModelError(
                    f"unknown init key {key!r}: not a gate output or output wire"
                )
            if index in seeded:
                raise ModelError(
                    f"init keys {seeded[index]!r} and {key!r} both seed gate "
                    f"{gate_names[index]!r}"
                )
            seeded[index] = key
            init_entries.append((index, value))

    return Circuit(
        name=comp.name,
        inputs=tuple(comp.inputs),
        gates=tuple(gates),
        outputs=tuple(comp.outputs),
        in_ports=in_ports,
        out_ports=out_ports,
        init=tuple(init_entries),
    )
