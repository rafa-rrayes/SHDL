"""ABI-faithful oracle: BaseEval wrapped in the release-ABI peek/poke discipline.

:class:`shdlc.sim.base_eval.BaseEval` is the pure unit-delay reference — it
has no notion of the release ABI's dirty flag or lazy peek. :class:`OracleSim`
adds exactly that discipline, mirrored rule-for-rule from the generated C
(shdlc/codegen.py, shdlc_goals.md §2/§3):

- ``poke`` masks the value to the port width and arms the dirty flag
  (BaseEval itself rejects oversized values, so masking happens here);
- ``peek`` of an OUTPUT port performs one hidden tick iff dirty (the tick
  clears dirty), then reads;
- ``peek`` of an INPUT port gathers the poked bits — it never ticks and
  never clears dirty;
- ``step(n <= 0)`` is a no-op that preserves dirty; ``step(n > 0)`` runs n
  ticks and thereby clears dirty;
- ``reset`` zeroes inputs and state, applies ``meta.init`` seeds, clears
  dirty (cycle 0: ``__VCC__`` reads 0 until the first tick).

Every ``expect`` value in the committed traces was produced by this class —
never by the C implementation under test. ``shdl-conformance verify-oracle``
re-derives all of them and additionally runs the C library in lockstep
against this oracle to keep the two honest about each other.
"""

from __future__ import annotations

from shdlc.harness import parse_with_ports
from shdlc.sim.base_eval import BaseEval


class OracleSim:
    """Reference simulator over Base SHDL text, speaking the release ABI."""

    def __init__(self, base_text: str):
        comp = parse_with_ports(base_text)
        self._eval = BaseEval(comp)
        ports = comp.meta["ports"]
        self._in_widths = {name: len(wires) for name, wires in ports["inputs"].items()}
        self._outputs = frozenset(ports["outputs"])
        self.dirty = False

    def reset(self) -> None:
        self._eval.reset()
        self.dirty = False

    def poke(self, signal: str, value: int) -> None:
        if signal not in self._in_widths:
            raise ValueError(
                f"poke: unknown input signal {signal!r} "
                f"(inputs: {', '.join(sorted(self._in_widths)) or 'none'})"
            )
        self._eval.poke(signal, value & ((1 << self._in_widths[signal]) - 1))
        self.dirty = True

    def peek(self, signal: str) -> int:
        if signal in self._outputs:
            if self.dirty:
                self._eval.step(1)
                self.dirty = False
            return self._eval.peek(signal)
        if signal in self._in_widths:
            return self._eval.peek(signal)
        raise ValueError(
            f"peek: unknown signal {signal!r} "
            f"(ports: {', '.join(sorted(self._in_widths | set(self._outputs))) or 'none'})"
        )

    def step(self, cycles: int = 1) -> None:
        if cycles > 0:
            self._eval.step(cycles)
            self.dirty = False
