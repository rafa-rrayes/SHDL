"""Read-only introspection over a circuit's Base SHDL metadata.

:class:`CircuitInfo` and its parts are plain values built once from the
``meta`` JSON (base_shdl.md §4) — nothing here recomputes or touches the
simulation. ``init`` and ``stats`` are exposed as read-only mappings taken
straight from the metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .errors import SignalNotFoundError


@dataclass(frozen=True, slots=True)
class PortInfo:
    """One user-facing port: name, direction, and its single-bit wires.

    ``wires`` lists the structural wires LSB first (``ports`` metadata,
    base_shdl.md §4.3); its length is the port's width.
    """

    name: str
    direction: str  # "input" | "output"
    wires: tuple[str, ...]

    @property
    def width(self) -> int:
        return len(self.wires)

    @property
    def max_value(self) -> int:
        """Largest unsigned value the port can hold: ``2**width - 1``."""
        return (1 << self.width) - 1

    @property
    def min_value(self) -> int:
        """Most negative value strict validation accepts: ``-(2**(width-1))``
        (negative pokes encode as two's complement)."""
        return -(1 << (self.width - 1))


@dataclass(frozen=True, slots=True)
class TimingInfo:
    """The ``timing`` metadata that drives ``settle()`` (base_shdl.md §4.7).

    Under feedback, ``max_depth`` covers the feedback-free shell only — it is
    not a settle count, which is why ``settle()`` is refused in that case.
    """

    max_depth: int
    is_combinational: bool
    has_feedback: bool


@dataclass(frozen=True, slots=True)
class CircuitInfo:
    """Everything PySHDL knows about a circuit, read once from its metadata."""

    name: str
    inputs: tuple[PortInfo, ...]
    outputs: tuple[PortInfo, ...]
    timing: TimingInfo | None
    init: Mapping[str, int] = field(default_factory=dict)
    stats: Mapping[str, object] = field(default_factory=dict)
    description: str | None = None

    @property
    def has_init(self) -> bool:
        """Whether any net is seeded to a non-default power-on value."""
        return bool(self.init)

    def port(self, name: str) -> PortInfo:
        """The named input or output port; raises SignalNotFoundError."""
        for port in self.inputs + self.outputs:
            if port.name == name:
                return port
        raise SignalNotFoundError(
            f"unknown port {name!r}; "
            f"inputs: {', '.join(p.name for p in self.inputs) or 'none'}; "
            f"outputs: {', '.join(p.name for p in self.outputs) or 'none'}"
        )


def info_from_meta(name: str, meta: dict) -> CircuitInfo:
    """Build a :class:`CircuitInfo` from a parsed ``meta`` JSON object.

    ``meta["ports"]`` must be present and well-formed (the caller validates
    the artifact through the compiler's model first); the other blocks are
    optional and default to empty.
    """
    ports = meta["ports"]
    inputs = tuple(PortInfo(port, "input", tuple(wires)) for port, wires in ports["inputs"].items())
    outputs = tuple(
        PortInfo(port, "output", tuple(wires)) for port, wires in ports["outputs"].items()
    )

    raw_timing = meta.get("timing")
    timing = None
    if isinstance(raw_timing, dict) and "max_depth" in raw_timing and "has_feedback" in raw_timing:
        has_feedback = bool(raw_timing["has_feedback"])
        timing = TimingInfo(
            max_depth=int(raw_timing["max_depth"]),
            is_combinational=bool(raw_timing.get("is_combinational", not has_feedback)),
            has_feedback=has_feedback,
        )

    return CircuitInfo(
        name=name,
        inputs=inputs,
        outputs=outputs,
        timing=timing,
        init=MappingProxyType(dict(meta.get("init") or {})),
        stats=MappingProxyType(dict(meta.get("stats") or {})),
        description=(meta.get("doc") or {}).get("description"),
    )
