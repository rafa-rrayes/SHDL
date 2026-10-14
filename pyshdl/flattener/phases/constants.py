"""Phase 5 — constant materialization (shdl.md §8, §12).

Each *referenced* bit of a named constant becomes a power-pin instance
``{NAME}_bit{K}`` of type ``__VCC__`` (bit is 1) or ``__GND__`` (bit is 0).
A constant is an unbounded unsigned value, so bits beyond its significant
bits are simply ``__GND__`` — referencing ``Hundred[99]`` is legal and yields
0. Unreferenced constants materialize nothing and produce no metadata entry.

User identifiers like ``FIVE_bit3`` are lexically legal (they match neither
reserved pattern), so a collision with a generated power-pin name is detected
here and reported as a positioned naming error (E0308) rather than silently
renamed — renaming would break the documented naming scheme.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..diagnostics import ErrorCode, err
from ..source import Pos
from .expand import ExpandedComponent
from .expander import BitConn, ConstBit, InstBit


@dataclass(frozen=True, slots=True)
class ConstGate:
    name: str
    type_name: str  # "__VCC__" | "__GND__"
    const: str
    bit: int
    pos: Pos  # the constant declaration site


@dataclass(slots=True)
class LoweredComponent:
    """A component after phases 4 and 5: per-bit connections, constants
    materialized as power-pin gates (kept separate from the phase-3 model so
    that remains a faithful snapshot of the program after expansion)."""

    ec: ExpandedComponent
    bit_conns: list[BitConn]
    const_gates: dict[str, ConstGate] = field(default_factory=dict)
    # const name -> {"value": int, "width": int, "bits": {bit: gate name}}
    const_meta: dict[str, dict] = field(default_factory=dict)


def materialize_constants(ec: ExpandedComponent, bit_conns: list[BitConn]) -> LoweredComponent:
    lc = LoweredComponent(ec=ec, bit_conns=[])
    for bc in bit_conns:
        src = bc.src
        if isinstance(src, ConstBit):
            info = ec.constants[src.const]
            gate_name = f"{src.const}_bit{src.bit}"
            if gate_name not in lc.const_gates:
                if gate_name in ec.instances:
                    raise err(
                        ErrorCode.E0308,
                        f"instance '{gate_name}' collides with the power-pin "
                        f"name generated for bit {src.bit} of constant "
                        f"'{src.const}' (declared at {info.pos})",
                        ec.instances[gate_name].pos,
                    )
                bit_value = (info.value >> (src.bit - 1)) & 1
                lc.const_gates[gate_name] = ConstGate(
                    name=gate_name,
                    type_name="__VCC__" if bit_value else "__GND__",
                    const=src.const,
                    bit=src.bit,
                    pos=info.pos,
                )
                meta = lc.const_meta.setdefault(
                    src.const,
                    {"value": info.value, "width": info.effective_width, "bits": {}},
                )
                meta["bits"][src.bit] = gate_name
            src = InstBit(gate_name, "O", 1)
        lc.bit_conns.append(BitConn(src, bc.dst, bc.pos))

    # Sort each constant's bits numerically for deterministic metadata.
    for meta in lc.const_meta.values():
        meta["bits"] = dict(sorted(meta["bits"].items()))
    return lc
