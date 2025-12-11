"""
Debug Info Generator

Generates .shdb debug info files during compilation.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from .ast import Component, Port, Instance, PrimitiveType
from .analyzer import AnalysisResult, GateInfo


@dataclass
class DebugInfoBuilder:
    """
    Builds debug information during compilation.
    
    Collects:
    - Port information
    - Gate info (lane/chunk assignments, names)
    - Hierarchy information (if available from flattening)
    - Source locations (if available)
    """
    
    component_name: str = ""
    source_file: str = ""
    
    # Ports
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    
    # Gates
    gates: dict[str, dict] = field(default_factory=dict)
    
    # Hierarchy (set during flattening)
    hierarchy: dict[str, dict] = field(default_factory=dict)
    
    # Connections
    connections: list[dict] = field(default_factory=list)
    
    # Constants
    constants: dict[str, dict] = field(default_factory=dict)
    
    # Source map
    source_map: dict[str, dict[int, list[str]]] = field(default_factory=dict)
    
    def from_analysis(self, analysis: AnalysisResult) -> "DebugInfoBuilder":
        """
        Populate debug info from compiler analysis result.
        
        This captures gate assignments and port info.
        """
        self.component_name = analysis.component.name
        
        # Ports
        for port in analysis.component.inputs:
            self.inputs.append({
                "name": port.name,
                "width": port.width if port.width else 1,
                "source_line": port.line,
                "source_column": port.column,
            })
        
        for port in analysis.component.outputs:
            self.outputs.append({
                "name": port.name,
                "width": port.width if port.width else 1,
                "source_line": port.line,
                "source_column": port.column,
            })
        
        # Gates
        for name, gate_info in analysis.gate_info.items():
            self.gates[name] = {
                "type": gate_info.primitive.to_string(),
                "lane": gate_info.lane,
                "chunk": gate_info.chunk,
                "hierarchy_path": self._infer_hierarchy_path(name),
                "original_name": self._extract_original_name(name),
                "parent_instance": self._extract_parent_instance(name),
            }
        
        return self
    
    def set_source_file(self, path: str) -> "DebugInfoBuilder":
        """Set the main source file."""
        self.source_file = path
        return self
    
    def add_hierarchy(self, component: str, instances: dict) -> "DebugInfoBuilder":
        """Add hierarchy information for a component."""
        self.hierarchy[component] = instances
        return self
    
    def add_source_location(self, gate_name: str, file: str, line: int, column: int = 0) -> "DebugInfoBuilder":
        """Add source location for a gate."""
        if gate_name in self.gates:
            self.gates[gate_name]["source"] = {
                "file": file,
                "line": line,
                "column": column,
            }
            
            # Update source map
            if file not in self.source_map:
                self.source_map[file] = {}
            if line not in self.source_map[file]:
                self.source_map[file][line] = []
            if gate_name not in self.source_map[file][line]:
                self.source_map[file][line].append(gate_name)
        
        return self
    
    def add_connection(self, source: str, destination: str, source_line: int = 0) -> "DebugInfoBuilder":
        """Add a connection."""
        self.connections.append({
            "source": source,
            "destination": destination,
            "source_line": source_line,
        })
        return self
    
    def add_constant(self, name: str, value: int, width: int, bits: list[str]) -> "DebugInfoBuilder":
        """Add constant information."""
        self.constants[name] = {
            "value": value,
            "width": width,
            "bits": bits,
        }
        return self
    
    def _infer_hierarchy_path(self, gate_name: str) -> str:
        """
        Infer hierarchy path from flattened gate name.
        
        e.g., "fa1_x1" -> "component/fa1/x1"
        """
        if "_" in gate_name:
            parts = gate_name.split("_")
            return f"{self.component_name}/" + "/".join(parts)
        return f"{self.component_name}/{gate_name}"
    
    def _extract_original_name(self, gate_name: str) -> str:
        """Extract the original gate name from flattened name."""
        if "_" in gate_name:
            return gate_name.split("_")[-1]
        return gate_name
    
    def _extract_parent_instance(self, gate_name: str) -> str:
        """Extract the parent instance name from flattened name."""
        if "_" in gate_name:
            parts = gate_name.split("_")
            if len(parts) > 1:
                return "_".join(parts[:-1])
        return ""
    
    def build(self) -> dict:
        """Build the final debug info dictionary."""
        return {
            "version": "1.0",
            "component": self.component_name,
            "source_file": self.source_file,
            "ports": {
                "inputs": self.inputs,
                "outputs": self.outputs,
            },
            "hierarchy": self.hierarchy,
            "gates": self.gates,
            "connections": self.connections,
            "constants": self.constants,
            "source_map": {
                file: {str(line): gates for line, gates in lines.items()}
                for file, lines in self.source_map.items()
            },
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.build(), indent=indent)
    
    def save(self, path: Path | str) -> None:
        """Save to a .shdb file."""
        path = Path(path)
        with open(path, "w") as f:
            f.write(self.to_json())


def generate_debug_info(analysis: AnalysisResult, source_file: str = "") -> DebugInfoBuilder:
    """
    Generate debug info from analysis result.
    
    Args:
        analysis: Compiler analysis result
        source_file: Original source file path
    
    Returns:
        DebugInfoBuilder that can be saved to .shdb
    """
    builder = DebugInfoBuilder()
    builder.from_analysis(analysis)
    builder.set_source_file(source_file)
    return builder
