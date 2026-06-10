"""Phase 4 — expander expansion (shdl.md §6, §12).

Rewrites every whole-vector connection, slice, concatenation, and replication
into individual single-bit connections. Both ends of a statement flatten to
LSB-first bit lists (concatenation items are MSB-first *within the braces*,
replication emits N adjacent copies); bits pair positionally; the per-bit
connections of one statement are emitted MSB-to-LSB, matching §6.5.2.

Also validates per statement: signal roles (§6.1), index bounds (E0402),
slice shape (E0404), width agreement (E0401), and self-connection (E0504).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from ..diagnostics import ErrorCode, err
from ..loader import PRIMITIVES
from ..source import Pos
from .expand import (
    ExpandedComponent,
    RConcat,
    RPrimary,
    RRepl,
    RSignal,
    instance_port_dir,
    signal_width,
)
from .monomorphize import MonoProgram


class PortBit(NamedTuple):
    """One bit of a port of the component being expanded."""

    name: str
    bit: int


class InstBit(NamedTuple):
    """One bit of a port of an instance inside the component."""

    inst: str
    port: str
    bit: int


class ConstBit(NamedTuple):
    """One bit of a named constant (resolved away in phase 5)."""

    const: str
    bit: int


type BitRef = PortBit | InstBit | ConstBit


@dataclass(frozen=True, slots=True)
class BitConn:
    src: BitRef
    dst: BitRef
    pos: Pos


def primary_bits(
    ec: ExpandedComponent, mono: MonoProgram, p: RPrimary
) -> list[BitRef]:
    """Flatten one resolved primary to its LSB-first bit list."""
    is_const = p.port is None and p.base in ec.constants
    width = signal_width(ec, mono, p.base, p.port, p.pos)

    match p.index:
        case None:
            lo, hi = 1, width
        case ("bit", k):
            if k < 1 or (not is_const and k > width):
                raise err(
                    ErrorCode.E0402,
                    f"bit index [{k}] out of range for "
                    f"'{_describe(p)}' of width {width}",
                    p.pos,
                )
            lo = hi = k
        case ("slice", a, b):
            if a < 1 or a > b:
                raise err(
                    ErrorCode.E0404,
                    f"invalid slice [{a}:{b}] on '{_describe(p)}'",
                    p.pos,
                )
            if not is_const and b > width:
                raise err(
                    ErrorCode.E0402,
                    f"slice [{a}:{b}] out of range for "
                    f"'{_describe(p)}' of width {width}",
                    p.pos,
                )
            lo, hi = a, b
        case _:  # pragma: no cover
            raise AssertionError(p.index)

    if p.port is not None:
        return [InstBit(p.base, p.port, k) for k in range(lo, hi + 1)]
    if is_const:
        return [ConstBit(p.base, k) for k in range(lo, hi + 1)]
    return [PortBit(p.base, k) for k in range(lo, hi + 1)]


def signal_bits(ec: ExpandedComponent, mono: MonoProgram, s: RSignal) -> list[BitRef]:
    """Flatten a resolved signal to its LSB-first bit list (shdl.md §6.5.2).

    Concatenation items are written MSB-first, so the LSB-first list is the
    items in *reverse* order, each item itself LSB-first.
    """
    match s:
        case RPrimary():
            return primary_bits(ec, mono, s)
        case RConcat(items=items):
            bits: list[BitRef] = []
            for item in reversed(items):
                bits.extend(_concat_item_bits(ec, mono, item))
            return bits
    raise AssertionError(s)  # pragma: no cover


def _concat_item_bits(ec: ExpandedComponent, mono: MonoProgram, item) -> list[BitRef]:
    match item:
        case RPrimary():
            return primary_bits(ec, mono, item)
        case RRepl(count=count, items=items):
            group: list[BitRef] = []
            for sub in reversed(items):
                group.extend(_concat_item_bits(ec, mono, sub))
            return group * count
    raise AssertionError(item)  # pragma: no cover


def _describe(p: RPrimary) -> str:
    return p.base if p.port is None else f"{p.base}.{p.port}"


def _signal_primaries(s: RSignal):
    match s:
        case RPrimary():
            yield s
        case RConcat(items=items) | RRepl(items=items):
            for item in items:
                yield from _signal_primaries(item)


def _has_replication(s: RSignal) -> bool:
    match s:
        case RPrimary():
            return False
        case RRepl():
            return True
        case RConcat(items=items):
            return any(_has_replication(i) for i in items)
    raise AssertionError(s)  # pragma: no cover


def _check_role(
    ec: ExpandedComponent, mono: MonoProgram, p: RPrimary, role: str
) -> None:
    """Enforce the source/destination table of shdl.md §6.1."""
    if p.port is not None:
        d = instance_port_dir(ec, mono, p.base, p.port, p.pos)
        if role == "src" and d != "out":
            raise err(
                ErrorCode.E0505,
                f"'{_describe(p)}' is an instance input and cannot be a "
                "connection source",
                p.pos,
            )
        if role == "dst" and d != "in":
            raise err(
                ErrorCode.E0505,
                f"'{_describe(p)}' is an instance output and cannot be a "
                "connection destination",
                p.pos,
            )
        return
    if p.base in ec.constants:
        if role == "dst":
            raise err(
                ErrorCode.E0505,
                f"constant '{p.base}' cannot be a connection destination",
                p.pos,
            )
        return
    d = ec.port_dir(p.base)
    if d is None:
        # Unknown name; let the width lookup raise the canonical E0307.
        signal_width(ec, mono, p.base, p.port, p.pos)
        raise AssertionError  # pragma: no cover
    if role == "src" and d != "in":
        raise err(
            ErrorCode.E0505,
            f"output port '{p.base}' cannot be a connection source",
            p.pos,
        )
    if role == "dst" and d != "out":
        raise err(
            ErrorCode.E0505,
            f"input port '{p.base}' cannot be a connection destination",
            p.pos,
        )


def expand_connections(ec: ExpandedComponent, mono: MonoProgram) -> list[BitConn]:
    out: list[BitConn] = []
    for conn in ec.connections:
        if _has_replication(conn.dst):
            raise err(
                ErrorCode.E0505,
                "replication cannot appear in a connection destination",
                conn.dst.pos,
            )
        for p in _signal_primaries(conn.src):
            _check_role(ec, mono, p, "src")
        for p in _signal_primaries(conn.dst):
            _check_role(ec, mono, p, "dst")

        src_bits = signal_bits(ec, mono, conn.src)
        dst_bits = signal_bits(ec, mono, conn.dst)
        if len(src_bits) != len(dst_bits):
            raise err(
                ErrorCode.E0401,
                f"connection width mismatch: source has {len(src_bits)} "
                f"bit(s), destination has {len(dst_bits)}",
                conn.pos,
            )
        for k in reversed(range(len(src_bits))):  # MSB-to-LSB (§6.5.2)
            s, d = src_bits[k], dst_bits[k]
            if s == d:
                raise err(
                    ErrorCode.E0504,
                    "a signal may not drive itself",
                    conn.pos,
                )
            out.append(BitConn(s, d, conn.pos))
    return out


def validate_component_connections(
    ec: ExpandedComponent,
    mono: MonoProgram,
    bit_conns: list[BitConn],
) -> None:
    """Per-component connection rules (shdl.md §6.4) — one driver per sink,
    no floating instance inputs, no floating outputs. Positions here are
    better than anything recoverable after flattening."""
    drivers: dict[BitRef, BitConn] = {}
    for bc in bit_conns:
        if bc.dst in drivers:
            raise err(
                ErrorCode.E0501,
                f"'{_bitref_str(bc.dst)}' is driven more than once "
                f"(first driver at {drivers[bc.dst].pos})",
                bc.pos,
            )
        drivers[bc.dst] = bc

    for name, width in ec.outputs:
        for bit in range(1, width + 1):
            if PortBit(name, bit) not in drivers:
                label = name if width == 1 else f"{name}[{bit}]"
                raise err(
                    ErrorCode.E0503,
                    f"output port '{label}' of '{ec.name}' is never driven",
                    ec.def_pos,
                )

    for info in ec.instances.values():
        if info.kind == "prim":
            in_ports = [(p, 1) for p in PRIMITIVES[info.type_ref][0]]
        else:
            in_ports = mono.specs[info.type_ref].inputs
        for port, width in in_ports:
            for bit in range(1, width + 1):
                if InstBit(info.name, port, bit) not in drivers:
                    label = port if width == 1 else f"{port}[{bit}]"
                    raise err(
                        ErrorCode.E0502,
                        f"input '{label}' of instance '{info.name}' "
                        f"({info.display_type}) is never connected",
                        info.pos,
                    )


def _bitref_str(ref: BitRef) -> str:
    match ref:
        case PortBit(name=name, bit=bit):
            return f"{name}[{bit}]"
        case InstBit(inst=inst, port=port, bit=bit):
            return f"{inst}.{port}[{bit}]"
        case ConstBit(const=const, bit=bit):
            return f"{const}[{bit}]"
    raise AssertionError(ref)  # pragma: no cover
