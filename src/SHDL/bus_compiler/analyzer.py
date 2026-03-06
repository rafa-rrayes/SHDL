"""
Bus Pattern Detection and Topological Sorting.

Uses partition refinement to group gates that process corresponding bits
of the same bus, enabling word-width C operations.
"""

from dataclasses import dataclass, field
from collections import defaultdict

from .graph import ConnectionGraph, GateNode, WireRef, OutputSink


@dataclass
class BusSource:
    """Describes how a bus group input is sourced."""
    kind: str               # port_aligned, port_broadcast, bus_group, constant, mixed
    ref: str = ""           # port name or bus group name
    broadcast_bit: int = 0  # for broadcast: which bit (1-based)
    per_bit: list = field(default_factory=list)  # for mixed: list of WireRef per gate
    shift: int = 0          # for port_aligned: right shift amount (0-based)


@dataclass
class BusGroup:
    """A group of gates that can be evaluated as a word-width operation."""
    name: str
    primitive: str
    width: int
    gates: list[GateNode]       # ordered by bit position
    bit_indices: list[int]      # the bit index each gate corresponds to
    input_sources: dict[str, BusSource] = field(default_factory=dict)
    is_feedback: bool = False
    scc_id: int = -1            # which SCC this group belongs to (-1 = none)


@dataclass
class AnalysisResult:
    bus_groups: list[BusGroup]          # topologically sorted
    singleton_gates: list[GateNode]     # gates not in any bus group
    output_sinks: list[OutputSink]
    input_ports: dict[str, int]
    output_ports: dict[str, int]
    # Maps gate instance name -> (group_name, position_in_group)
    gate_to_group: dict[str, tuple[str, int]] = field(default_factory=dict)


class BusAnalyzer:
    """Analyzes a ConnectionGraph to detect bus-width operation patterns."""

    def __init__(self, graph: ConnectionGraph):
        self.graph = graph

    def analyze(self) -> AnalysisResult:
        # Filter out VCC/GND pseudo-gates
        all_gates = [
            g for g in self.graph.gates.values()
            if g.primitive not in ("__VCC__", "__GND__")
        ]

        # Step 1: Partition refinement to find bus groups
        group_of = self._partition_refinement(all_gates)

        # Step 2: Assign bit positions
        positions = self._assign_positions(all_gates)

        # Step 3: Build BusGroup objects from partition results
        groups_by_id: dict[str, list[GateNode]] = defaultdict(list)
        for gate in all_gates:
            groups_by_id[group_of[gate.name]].append(gate)

        bus_groups: list[BusGroup] = []
        grouped_gates: set[str] = set()
        gate_group_map: dict[str, str] = {}  # gate_name -> group_name
        group_counter = 0

        for gid, gates in groups_by_id.items():
            if len(gates) < 2:
                continue  # singleton

            # Sort by bit position
            gate_bits = []
            for gate in gates:
                bit = positions.get(gate.name, 1)
                gate_bits.append((bit, gate))
            gate_bits.sort(key=lambda x: x[0])

            # Deduplicate bit positions
            seen_bits: set[int] = set()
            deduped = []
            for bit, gate in gate_bits:
                if bit not in seen_bits:
                    seen_bits.add(bit)
                    deduped.append((bit, gate))
            gate_bits = deduped

            if len(gate_bits) < 2:
                continue

            group_counter += 1
            prim = gates[0].primitive
            name = f"bus_{prim.lower()}_{group_counter}"

            group = BusGroup(
                name=name,
                primitive=prim,
                width=len(gate_bits),
                gates=[g for _, g in gate_bits],
                bit_indices=[b for b, _ in gate_bits],
            )
            bus_groups.append(group)

            for gate in group.gates:
                grouped_gates.add(gate.name)
                gate_group_map[gate.name] = name

        # Singletons
        singletons = [g for g in all_gates if g.name not in grouped_gates]

        # Step 4: Classify sources for each bus group
        for group in bus_groups:
            self._classify_sources(group, gate_group_map)

        # Step 5: SCC detection
        scc_map = self._detect_feedback(bus_groups)

        # Step 6: Topological sort
        sorted_groups = self._topological_sort(bus_groups, scc_map)

        # Build gate_to_group map
        gate_to_group = {}
        for group in sorted_groups:
            for i, gate in enumerate(group.gates):
                gate_to_group[gate.name] = (group.name, i)

        return AnalysisResult(
            bus_groups=sorted_groups,
            singleton_gates=singletons,
            output_sinks=self.graph.output_sinks,
            input_ports=self.graph.input_ports,
            output_ports=self.graph.output_ports,
            gate_to_group=gate_to_group,
        )

    def _partition_refinement(self, all_gates: list[GateNode]) -> dict[str, str]:
        """Global partition refinement using group IDs instead of primitive types."""
        # Round 0: group by primitive type
        group_of: dict[str, str] = {}
        for gate in all_gates:
            group_of[gate.name] = gate.primitive

        for _ in range(100):  # safety bound
            fingerprints: dict[str, tuple] = {}
            for gate in all_gates:
                fp = [gate.primitive]
                for port in sorted(gate.inputs.keys()):
                    wire = gate.inputs[port]
                    if wire.kind == "port_input":
                        fp.append(("port", wire.name))
                    elif wire.kind == "gate_output":
                        fp.append(("gate", group_of.get(wire.name, "?")))
                    elif wire.kind == "constant":
                        fp.append(("const", wire.name))
                fingerprints[gate.name] = tuple(fp)

            new_group_of: dict[str, str] = {}
            fp_to_id: dict[tuple, str] = {}
            for gate in all_gates:
                fp = fingerprints[gate.name]
                if fp not in fp_to_id:
                    fp_to_id[fp] = f"G{len(fp_to_id)}"
                new_group_of[gate.name] = fp_to_id[fp]

            if new_group_of == group_of:
                break  # converged
            group_of = new_group_of

        return group_of

    def _assign_positions(self, all_gates: list[GateNode]) -> dict[str, int]:
        """Iterative bit position assignment with cycle safety.

        Only uses multi-bit port inputs for position info (single-bit ports
        like 'clk' are broadcasts and don't carry position).
        """
        positions: dict[str, int] = {}

        # Direct: gates with multi-bit port_input wires get position from bit_index
        for gate in all_gates:
            for wire in gate.inputs.values():
                if wire.kind == "port_input" and self.graph.input_ports.get(wire.name, 1) > 1:
                    positions[gate.name] = wire.bit_index
                    break

        # Propagate: inherit from already-assigned source gates
        changed = True
        while changed:
            changed = False
            for gate in all_gates:
                if gate.name in positions:
                    continue
                for wire in gate.inputs.values():
                    if wire.kind == "gate_output" and wire.name in positions:
                        positions[gate.name] = positions[wire.name]
                        changed = True
                        break

        # Fallback: gates with only single-bit port inputs get position 1
        for gate in all_gates:
            if gate.name not in positions:
                for wire in gate.inputs.values():
                    if wire.kind == "port_input":
                        positions[gate.name] = wire.bit_index
                        break

        return positions

    def _classify_sources(self, group: BusGroup, gate_group_map: dict[str, str]):
        """Classify each input port source for a bus group."""
        input_port_names = ["A", "B"] if group.primitive != "NOT" else ["A"]

        for port_name in input_port_names:
            wires = []
            for gate in group.gates:
                wire = gate.inputs.get(port_name)
                wires.append(wire)

            if not wires or wires[0] is None:
                continue

            source = self._classify_wire_list(wires, group.bit_indices, gate_group_map)
            group.input_sources[port_name] = source

    def _classify_wire_list(
        self, wires: list[WireRef], bit_indices: list[int],
        gate_group_map: dict[str, str]
    ) -> BusSource:
        """Classify a list of wires (one per gate in the group)."""
        if not wires or wires[0] is None:
            return BusSource(kind="mixed", per_bit=wires)

        # Check: all constant?
        if all(w and w.kind == "constant" for w in wires):
            val = wires[0].name
            if all(w.name == val for w in wires):
                return BusSource(kind="constant", ref=val)

        # Check: all from same port?
        if all(w and w.kind == "port_input" for w in wires):
            port_name = wires[0].name
            if all(w.name == port_name for w in wires):
                if all(w.bit_index == bi for w, bi in zip(wires, bit_indices)):
                    # Check contiguity: bit_indices must be consecutive
                    contiguous = all(
                        bit_indices[i+1] == bit_indices[i] + 1
                        for i in range(len(bit_indices) - 1)
                    )
                    if contiguous:
                        shift = bit_indices[0] - 1  # 1-based to 0-based
                        return BusSource(kind="port_aligned", ref=port_name, shift=shift)
                    # Non-contiguous: fall through to mixed
                if all(w.bit_index == wires[0].bit_index for w in wires):
                    return BusSource(kind="port_broadcast", ref=port_name,
                                     broadcast_bit=wires[0].bit_index)

        # Check: all from gate outputs in the same group?
        if all(w and w.kind == "gate_output" for w in wires):
            src_groups = set()
            for w in wires:
                grp = gate_group_map.get(w.name)
                if grp:
                    src_groups.add(grp)
                else:
                    src_groups.add(None)

            if len(src_groups) == 1 and None not in src_groups:
                group_name = src_groups.pop()
                return BusSource(kind="bus_group", ref=group_name)

        # Fallback: mixed
        return BusSource(kind="mixed", per_bit=list(wires))

    def _detect_feedback(self, groups: list[BusGroup]) -> dict[str, int]:
        """Detect feedback loops (SCCs). Returns gate_group_name -> scc_id mapping."""
        group_map = {g.name: g for g in groups}
        adj: dict[str, set[str]] = defaultdict(set)

        for group in groups:
            for source in group.input_sources.values():
                if source.kind == "bus_group" and source.ref in group_map:
                    adj[source.ref].add(group.name)

        # Tarjan's SCC
        index_counter = [0]
        stack = []
        on_stack = set()
        indices = {}
        lowlinks = {}
        sccs: list[list[str]] = []

        def strongconnect(v):
            indices[v] = index_counter[0]
            lowlinks[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in adj.get(v, set()):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)

        for name in group_map:
            if name not in indices:
                strongconnect(name)

        # Build SCC map and mark feedback groups
        scc_map: dict[str, int] = {}
        for scc_id, scc in enumerate(sccs):
            if len(scc) > 1:
                for name in scc:
                    if name in group_map:
                        group_map[name].is_feedback = True
                        group_map[name].scc_id = scc_id
                        scc_map[name] = scc_id

        return scc_map

    def _topological_sort(
        self, groups: list[BusGroup], scc_map: dict[str, int]
    ) -> list[BusGroup]:
        """Topologically sort bus groups, removing SCC back-edges."""
        from collections import deque

        group_map = {g.name: g for g in groups}

        # Build forward deps and reverse adjacency
        deps: dict[str, set[str]] = {g.name: set() for g in groups}
        rdeps: dict[str, set[str]] = {g.name: set() for g in groups}
        for group in groups:
            for source in group.input_sources.values():
                if source.kind == "bus_group" and source.ref in group_map:
                    src_name = source.ref
                    if (group.name in scc_map and src_name in scc_map
                            and scc_map[group.name] == scc_map[src_name]):
                        continue
                    deps[group.name].add(src_name)
                    rdeps[src_name].add(group.name)

        # Kahn's algorithm with reverse adjacency
        in_degree = {g.name: len(deps[g.name]) for g in groups}
        queue = deque(name for name, deg in in_degree.items() if deg == 0)
        result = []

        while queue:
            name = queue.popleft()
            result.append(group_map[name])
            for dependent in rdeps.get(name, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Add any remaining
        if len(result) < len(groups):
            visited = {g.name for g in result}
            for g in groups:
                if g.name not in visited:
                    result.append(g)

        return result
