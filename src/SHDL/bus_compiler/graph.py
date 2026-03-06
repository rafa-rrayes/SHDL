"""
Connection Graph builder from flattened Component (expanded AST).

Transforms the flat list of Instances and Connections into a structured
directed graph of GateNodes with explicit input/output wiring.
"""

from dataclasses import dataclass, field
from typing import Optional

from ..flattener.ast import (
    Component, Instance, Connection, Signal, IndexExpr, NumberLiteral, Port, Node
)


@dataclass
class WireRef:
    """Identifies one bit of a signal."""
    kind: str          # "port_input", "gate_output", "constant"
    name: str          # port name or instance name
    bit_index: int     # 1-based for ports, 0 for gate outputs

    def __hash__(self):
        return hash((self.kind, self.name, self.bit_index))

    def __eq__(self, other):
        if not isinstance(other, WireRef):
            return NotImplemented
        return (self.kind, self.name, self.bit_index) == (other.kind, other.name, other.bit_index)


@dataclass
class GateNode:
    """One primitive gate instance."""
    name: str          # instance name
    primitive: str     # "AND", "OR", "XOR", "NOT", "__VCC__", "__GND__"
    inputs: dict[str, WireRef] = field(default_factory=dict)
    # output is implicitly (gate_output, self.name, 0)


@dataclass
class OutputSink:
    """Component output port bit driven by a gate or input."""
    port_name: str
    bit_index: int     # 1-based
    source: WireRef


class ConnectionGraph:
    """Directed graph of gates and their connections."""

    def __init__(self):
        self.gates: dict[str, GateNode] = {}
        self.input_ports: dict[str, int] = {}   # port_name -> width (1 if single-bit)
        self.output_ports: dict[str, int] = {}  # port_name -> width
        self.output_sinks: list[OutputSink] = []
        # Track output-to-output (direct passthrough) connections
        self.direct_outputs: dict[str, WireRef] = {}  # "portname_bit" -> source

    @classmethod
    def from_component(cls, comp: Component) -> "ConnectionGraph":
        """Build graph from a flattened Component (expanded AST types)."""
        graph = cls()

        # Collect port widths
        input_names = set()
        for p in comp.inputs:
            w = p.width if p.width else 1
            graph.input_ports[p.name] = w
            input_names.add(p.name)

        output_names = set()
        for p in comp.outputs:
            w = p.width if p.width else 1
            graph.output_ports[p.name] = w
            output_names.add(p.name)

        # Collect gate instances
        for node in comp.instances:
            if isinstance(node, Instance):
                graph.gates[node.name] = GateNode(
                    name=node.name,
                    primitive=node.component_type,
                )

        # Process connections
        if comp.connect_block:
            for node in comp.connect_block.statements:
                if isinstance(node, Connection):
                    graph._process_connection(node, input_names, output_names)

        return graph

    def _process_connection(self, conn: Connection, input_names: set, output_names: set):
        """Process a single Connection node."""
        src = conn.source
        dst = conn.destination

        src_ref = self._signal_to_wireref(src, input_names, is_source=True)
        if src_ref is None:
            return

        # Destination is a gate input
        if dst.instance and dst.instance in self.gates:
            self.gates[dst.instance].inputs[dst.name] = src_ref

        # Destination is a component output port
        elif dst.instance is None and dst.name in output_names:
            bit_idx = self._get_bit_index(dst)
            self.output_sinks.append(OutputSink(
                port_name=dst.name,
                bit_index=bit_idx,
                source=src_ref,
            ))

    def _signal_to_wireref(self, sig: Signal, input_names: set, is_source: bool) -> Optional[WireRef]:
        """Convert a Signal AST node to a WireRef."""
        if sig.instance is None:
            # Component port
            if sig.name in input_names:
                bit_idx = self._get_bit_index(sig)
                return WireRef(kind="port_input", name=sig.name, bit_index=bit_idx)
            # Could be an output port used as source (passthrough) - rare
            return WireRef(kind="port_input", name=sig.name, bit_index=self._get_bit_index(sig))

        if sig.instance in self.gates:
            gate = self.gates[sig.instance]
            if is_source and sig.name == "O":
                # Gate output
                if gate.primitive == "__VCC__":
                    return WireRef(kind="constant", name="VCC", bit_index=1)
                elif gate.primitive == "__GND__":
                    return WireRef(kind="constant", name="GND", bit_index=0)
                return WireRef(kind="gate_output", name=sig.instance, bit_index=0)

        return None

    @staticmethod
    def _get_bit_index(sig: Signal) -> int:
        """Extract 1-based bit index from a Signal, defaulting to 1."""
        if sig.index and sig.index.start and isinstance(sig.index.start, NumberLiteral):
            return sig.index.start.value
        return 1
