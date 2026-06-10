"""Reference unit-delay evaluator over parsed Base SHDL (shdl.md §11).

Semantics: every gate output holds a stored bit; ``step()`` recomputes all
gates simultaneously from the current state (one gate level per cycle). At
cycle 0 every stored bit is 0 except nets seeded by ``meta.init``; a
``__VCC__`` output therefore reads 0 at cycle 0 and 1 from cycle 1 on.
Component ports are transparent: inputs are poked values, outputs read
their driver combinationally.
"""

from __future__ import annotations

from ..baseshdl import BaseComponent

_BIN_OPS = {
    "AND": lambda a, b: a & b,
    "OR": lambda a, b: a | b,
    "XOR": lambda a, b: a ^ b,
}


class BaseEval:
    def __init__(self, comp: BaseComponent):
        self.comp = comp
        self.pin_src: dict[tuple[str, str], str] = {}
        self.out_src: dict[str, str] = {}
        for src, dst in comp.connections:
            if "." in dst:
                gate, pin = dst.split(".")
                self.pin_src[(gate, pin)] = src
            else:
                self.out_src[dst] = src
        self.inputs: dict[str, int] = {}
        self.state: dict[str, int] = {}
        self.reset()

    def reset(self) -> None:
        """Return to cycle 0: all inputs and gate outputs 0, then init seeds."""
        self.inputs = dict.fromkeys(self.comp.inputs, 0)
        self.state = dict.fromkeys(self.comp.gates, 0)
        for key, value in self.comp.meta.get("init", {}).items():
            self.state[self._seeded_gate(key)] = value

    def _seeded_gate(self, key: str) -> str:
        # An init key is a gate output "g.O" or an output-port wire, which
        # aliases the gate that drives it — possibly through a chain of
        # output-wire aliases (out -> out -> ... -> gate.O).
        sig = key
        seen: set[str] = set()
        while "." not in sig:
            if sig in self.inputs:  # passthrough: no gate to seed
                raise ValueError(f"init key {key!r} resolves to input wire {sig!r}")
            if sig in seen or sig not in self.out_src:
                raise ValueError(f"init key {key!r} does not resolve to a gate")
            seen.add(sig)
            sig = self.out_src[sig]
        return sig.split(".")[0]

    def _value(self, sig: str) -> int:
        if "." in sig:
            gate, pin = sig.split(".")
            assert pin == "O", sig
            return self.state[gate]
        if sig in self.inputs:
            return self.inputs[sig]
        return self._value(self.out_src[sig])  # an output wire read as a net

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            new = {}
            for gate, type_name in self.comp.gates.items():
                match type_name:
                    case "__VCC__":
                        v = 1
                    case "__GND__":
                        v = 0
                    case "NOT":
                        v = 1 - self._value(self.pin_src[(gate, "A")])
                    case _:
                        v = _BIN_OPS[type_name](
                            self._value(self.pin_src[(gate, "A")]),
                            self._value(self.pin_src[(gate, "B")]),
                        )
                new[gate] = v
            self.state = new

    def settle(self) -> None:
        timing = self.comp.meta["timing"]
        if timing["has_feedback"]:
            raise ValueError("settle() is disabled for circuits with feedback")
        self.step(timing["max_depth"])

    def poke(self, port: str, value: int) -> None:
        wires = self.comp.meta["ports"]["inputs"][port]
        if value < 0 or value >= (1 << len(wires)):
            raise ValueError(f"{value} does not fit {len(wires)}-bit port {port!r}")
        for i, wire in enumerate(wires):
            self.inputs[wire] = (value >> i) & 1

    def peek(self, port: str) -> int:
        groups = self.comp.meta["ports"]
        wires = groups["outputs"].get(port) or groups["inputs"][port]
        return sum(self._value(w) << i for i, w in enumerate(wires))

    def peek_wire(self, wire: str) -> int:
        return self._value(wire)
