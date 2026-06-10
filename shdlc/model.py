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


def build_circuit(comp: BaseComponent) -> Circuit:
    """Validate ``comp`` and lower it to a :class:`Circuit`.

    Raises :class:`ModelError` with a human-readable message naming the
    offending construct for any violation of the module invariants.
    """
    raise NotImplementedError
