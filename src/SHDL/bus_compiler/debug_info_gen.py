"""
Debug Info Generator for Bus Compiler.

Generates .shdb debug info files from bus compiler AnalysisResult,
matching the format expected by the debugger (DebugInfo).
"""

from pathlib import Path
import json

from .analyzer import AnalysisResult


class BusDebugInfoBuilder:
    """Builds .shdb debug info from bus compiler analysis."""

    def __init__(self, analysis: AnalysisResult, source_file: str = ""):
        self.analysis = analysis
        self.source_file = source_file
        self.component_name = ""

    def set_component_name(self, name: str) -> "BusDebugInfoBuilder":
        self.component_name = name
        return self

    def build(self) -> dict:
        """Build the debug info dictionary."""
        gates = {}

        # Gates from bus groups
        for group in self.analysis.bus_groups:
            for pos, gate in enumerate(group.gates):
                gates[gate.name] = {
                    "type": gate.primitive,
                    "lane": pos,
                    "chunk": 0,  # Bus compiler doesn't use chunk/lane packing
                    "hierarchy_path": self._infer_hierarchy(gate.name),
                    "original_name": self._extract_original(gate.name),
                    "parent_instance": self._extract_parent(gate.name),
                }

        # Singleton gates
        for gate in self.analysis.singleton_gates:
            gates[gate.name] = {
                "type": gate.primitive,
                "lane": 0,
                "chunk": 0,
                "hierarchy_path": self._infer_hierarchy(gate.name),
                "original_name": self._extract_original(gate.name),
                "parent_instance": self._extract_parent(gate.name),
            }

        return {
            "version": "1.0",
            "component": self.component_name,
            "source_file": self.source_file,
            "ports": {
                "inputs": [
                    {"name": name, "width": width, "source_line": 0, "source_column": 0}
                    for name, width in self.analysis.input_ports.items()
                ],
                "outputs": [
                    {"name": name, "width": width, "source_line": 0, "source_column": 0}
                    for name, width in self.analysis.output_ports.items()
                ],
            },
            "hierarchy": {},
            "gates": gates,
            "connections": [],
            "constants": {},
            "source_map": {},
        }

    def save(self, path: str) -> None:
        """Save to a .shdb file."""
        data = self.build()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _infer_hierarchy(self, gate_name: str) -> str:
        if "_" in gate_name:
            parts = gate_name.split("_")
            return f"{self.component_name}/" + "/".join(parts)
        return f"{self.component_name}/{gate_name}"

    def _extract_original(self, gate_name: str) -> str:
        if "_" in gate_name:
            return gate_name.split("_")[-1]
        return gate_name

    def _extract_parent(self, gate_name: str) -> str:
        if "_" in gate_name:
            parts = gate_name.split("_")
            if len(parts) > 1:
                return "_".join(parts[:-1])
        return ""
