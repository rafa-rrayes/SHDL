"""Independent reference evaluator over the phase-3 model (shdl.md §11).

Interprets the expanded-component tree (`expand_all` output) directly,
without going through phases 4-6 or the emitted Base SHDL. It re-derives the
spec's semantics with a different mechanism — union-find over alias classes
instead of driver-chain resolution — so that agreement with ``BaseEval`` over
random stimulus is evidence the lowering preserved behavior, not that two
copies of the same code agree.

Cells with stored state: primitive gate outputs, referenced constant bits
(power pins: 0 at cycle 0, their bit value from cycle 1), and top-level input
bits (poked). All component ports at any depth are transparent aliases.
"""

from __future__ import annotations

from ..phases.expand import ExpandedComponent, RConcat, RPrimary, RRepl
from ..phases.monomorphize import MonoProgram

# Node keys:
#   ("port", path, name, bit)    component port bit (path == () -> top port)
#   ("pin",  path, inst, pin)    primitive gate pin (single-bit)
#   ("const", path, name, bit)   one referenced bit of a named constant
type Node = tuple


class HighEval:
    def __init__(self, mono: MonoProgram, expanded: dict[str, ExpandedComponent]):
        self.mono = mono
        self.expanded = expanded
        self.top = expanded[mono.top_key]
        self._parent: dict[Node, Node] = {}
        self.gates: dict[Node, str] = {}  # ("pin", path, inst, "O") -> type
        self.consts: dict[Node, int] = {}  # const node -> its bit value
        self.pin_src: dict[Node, Node] = {}
        self._raw_seeds: list[tuple[Node, int]] = []

        self._elaborate(mono.top_key, ())
        # The alias graph is complete; freeze every read to its terminal.
        self.pin_src = {pin: self._find(src) for pin, src in self.pin_src.items()}
        self.seeds: dict[Node, int] = {}
        for node, value in self._raw_seeds:
            self.seeds[self._find(node)] = value

        self.state: dict[Node, int] = {}
        self.reset()

    # ---- elaboration ---------------------------------------------------- #

    def _elaborate(self, key: str, path: tuple[str, ...]) -> None:
        ec = self.expanded[key]
        for info in ec.instances.values():
            if info.kind == "prim":
                self.gates[("pin", path, info.name, "O")] = info.type_ref
            else:
                self._elaborate(info.type_ref, (*path, info.name))
        for conn in ec.connections:
            src_bits = self._signal_bits(ec, path, conn.src)
            dst_bits = self._signal_bits(ec, path, conn.dst)
            assert len(src_bits) == len(dst_bits), conn
            for s, d in zip(src_bits, dst_bits):
                if d[0] == "pin":
                    self.pin_src[d] = s
                else:
                    self._alias(d, s)
        for target, value, _pos in ec.init:
            for i, node in enumerate(self._primary_bits(ec, path, target)):
                self._raw_seeds.append((node, (value >> i) & 1))

    def _signal_bits(self, ec, path, signal) -> list[Node]:
        match signal:
            case RPrimary():
                return self._primary_bits(ec, path, signal)
            case RConcat(items=items) | RRepl(items=items):
                bits: list[Node] = []
                for item in reversed(items):  # items are MSB-first
                    bits.extend(self._signal_bits(ec, path, item))
                if isinstance(signal, RRepl):
                    bits = bits * signal.count
                return bits
        # Unreachable: RSignal is closed over RPrimary/RConcat/RRepl, all matched.
        raise AssertionError(signal)  # pragma: no cover

    def _primary_bits(self, ec, path, p: RPrimary) -> list[Node]:
        if p.port is not None:
            info = ec.instances[p.base]
            if info.kind == "prim":
                return [("pin", path, p.base, p.port)]
            spec = self.mono.specs[info.type_ref]
            width = spec.port_width(p.port)
            child = (*path, p.base)
            make = lambda k: ("port", child, p.port, k)  # noqa: E731
        elif p.base in ec.constants:
            cinfo = ec.constants[p.base]
            width = cinfo.effective_width

            def make(k, name=p.base, value=cinfo.value):
                node = ("const", path, name, k)
                self.consts[node] = (value >> (k - 1)) & 1
                return node
        else:
            width = ec.port_width(p.base)
            make = lambda k: ("port", path, p.base, k)  # noqa: E731

        match p.index:
            case None:
                lo, hi = 1, width
            case ("bit", k):
                lo = hi = k
            case ("slice", a, b):
                lo, hi = a, b
        return [make(k) for k in range(lo, hi + 1)]

    # ---- union-find over alias classes ----------------------------------- #

    def _find(self, node: Node) -> Node:
        parent = self._parent
        root = node
        while root in parent:
            root = parent[root]
        while node != root:
            nxt = parent[node]
            parent[node] = root
            node = nxt
        return root

    def _alias(self, dst: Node, src: Node) -> None:
        rd, rs = self._find(dst), self._find(src)
        if rd != rs:
            self._parent[rd] = rs

    # ---- simulation ------------------------------------------------------ #

    def reset(self) -> None:
        state = dict.fromkeys(self.gates, 0)
        state.update(dict.fromkeys(self.consts, 0))
        for name, width in self.top.inputs:
            for b in range(1, width + 1):
                state[("port", (), name, b)] = 0
        for terminal, value in self.seeds.items():
            assert terminal in state, terminal  # E0A01 excludes inputs upstream
            state[terminal] = value
        self.state = state

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            new = dict(self.state)
            for gate_out, type_name in self.gates.items():
                _, path, inst, _ = gate_out
                match type_name:
                    case "__VCC__":
                        v = 1
                    case "__GND__":
                        v = 0
                    case "NOT":
                        v = 1 - self.state[self.pin_src[("pin", path, inst, "A")]]
                    case _:
                        a = self.state[self.pin_src[("pin", path, inst, "A")]]
                        b = self.state[self.pin_src[("pin", path, inst, "B")]]
                        v = (
                            a & b
                            if type_name == "AND"
                            else (a | b)
                            if type_name == "OR"
                            else a ^ b
                        )
                new[gate_out] = v
            for cnode, bit in self.consts.items():
                new[cnode] = bit  # power pins assert their value from cycle 1
            self.state = new

    def poke(self, port: str, value: int) -> None:
        """Set an input port. Like BaseEval, this oracle is *intentionally*
        stricter than the compiled C ABI: an out-of-range value raises
        ``ValueError`` rather than masking modulo 2^width (the C `poke`'s
        AMB-2 behavior). Never relax this to match the implementation — the
        DualSim harness bridges the asymmetry deliberately (golden_tests §5)."""
        width = self.top.port_width(port)
        assert self.top.port_dir(port) == "in", port
        if value < 0 or value >= (1 << width):
            raise ValueError(f"{value} does not fit {width}-bit port {port!r}")
        for b in range(1, width + 1):
            self.state[("port", (), port, b)] = (value >> (b - 1)) & 1

    def peek(self, port: str) -> int:
        width = self.top.port_width(port)
        return sum(
            self.state[self._find(("port", (), port, b))] << (b - 1)
            for b in range(1, width + 1)
        )
