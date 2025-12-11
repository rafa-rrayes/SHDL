"""
Debug Information Management

Parses and provides access to .shdb debug info files.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import json


@dataclass
class PortInfo:
    """Information about a circuit port."""
    name: str
    width: int
    source_line: int = 0
    source_column: int = 0
    
    @property
    def is_vector(self) -> bool:
        """Check if this is a multi-bit port."""
        return self.width > 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "width": self.width,
            "source_line": self.source_line,
            "source_column": self.source_column,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PortInfo":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            width=data["width"],
            source_line=data.get("source_line", 0),
            source_column=data.get("source_column", 0),
        )


@dataclass
class SourceLocation:
    """A location in source code."""
    file: str
    line: int
    column: int = 0
    
    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SourceLocation":
        return cls(
            file=data["file"],
            line=data["line"],
            column=data.get("column", 0),
        )
    
    def __str__(self) -> str:
        if self.column:
            return f"{self.file}:{self.line}:{self.column}"
        return f"{self.file}:{self.line}"


@dataclass
class GateInfo:
    """Information about a primitive gate."""
    name: str                    # Flattened name (e.g., "fa1_x1")
    gate_type: str               # XOR, AND, OR, NOT, __VCC__, __GND__
    lane: int                    # Bit position in chunk (0-63)
    chunk: int                   # Chunk index
    hierarchy_path: str          # e.g., "Adder16/fa1/x1"
    original_name: str           # Original name in source (e.g., "x1")
    parent_instance: str         # Parent instance (e.g., "fa1")
    source: Optional[SourceLocation] = None
    
    @property
    def lane_mask(self) -> int:
        """Get the bit mask for this lane."""
        return 1 << self.lane
    
    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "type": self.gate_type,
            "lane": self.lane,
            "chunk": self.chunk,
            "hierarchy_path": self.hierarchy_path,
            "original_name": self.original_name,
            "parent_instance": self.parent_instance,
        }
        if self.source:
            result["source"] = self.source.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, name: str, data: dict) -> "GateInfo":
        source = None
        if "source" in data:
            source = SourceLocation.from_dict(data["source"])
        return cls(
            name=name,
            gate_type=data["type"],
            lane=data["lane"],
            chunk=data["chunk"],
            hierarchy_path=data.get("hierarchy_path", ""),
            original_name=data.get("original_name", name),
            parent_instance=data.get("parent_instance", ""),
            source=source,
        )


@dataclass
class InstanceInfo:
    """Information about a component instance."""
    name: str                    # Instance name (e.g., "fa1")
    component_type: str          # Component type (e.g., "FullAdder")
    source_line: int
    flattened_prefix: str        # Prefix for flattened names (e.g., "fa1_")
    children: dict[str, "InstanceInfo"] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        result = {
            "type": self.component_type,
            "source_line": self.source_line,
            "flattened_prefix": self.flattened_prefix,
        }
        if self.children:
            result["children"] = {
                name: child.to_dict() 
                for name, child in self.children.items()
            }
        return result
    
    @classmethod
    def from_dict(cls, name: str, data: dict) -> "InstanceInfo":
        children = {}
        if "children" in data:
            for child_name, child_data in data["children"].items():
                children[child_name] = cls.from_dict(child_name, child_data)
        return cls(
            name=name,
            component_type=data["type"],
            source_line=data.get("source_line", 0),
            flattened_prefix=data.get("flattened_prefix", f"{name}_"),
            children=children,
        )


@dataclass
class ConnectionInfo:
    """Information about a connection."""
    source: str
    destination: str
    source_line: int = 0
    
    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "destination": self.destination,
            "source_line": self.source_line,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ConnectionInfo":
        return cls(
            source=data["source"],
            destination=data["destination"],
            source_line=data.get("source_line", 0),
        )


@dataclass
class ConstantInfo:
    """Information about a materialized constant."""
    name: str
    value: int
    width: int
    bits: list[str]  # Gate names for each bit
    
    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "width": self.width,
            "bits": self.bits,
        }
    
    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ConstantInfo":
        return cls(
            name=name,
            value=data["value"],
            width=data["width"],
            bits=data.get("bits", []),
        )


@dataclass
class HierarchyNode:
    """A node in the component hierarchy."""
    name: str
    source_file: str
    source_line: int
    instances: dict[str, InstanceInfo] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "source_line": self.source_line,
            "instances": {
                name: inst.to_dict() 
                for name, inst in self.instances.items()
            },
        }
    
    @classmethod
    def from_dict(cls, name: str, data: dict) -> "HierarchyNode":
        instances = {}
        if "instances" in data:
            for inst_name, inst_data in data["instances"].items():
                instances[inst_name] = InstanceInfo.from_dict(inst_name, inst_data)
        return cls(
            name=name,
            source_file=data.get("source_file", ""),
            source_line=data.get("source_line", 0),
            instances=instances,
        )


class DebugInfo:
    """
    Container for all debug information about a compiled circuit.
    
    Loads from .shdb JSON files or can be constructed programmatically
    during compilation.
    """
    
    VERSION = "1.0"
    
    def __init__(self):
        self.version: str = self.VERSION
        self.component: str = ""
        self.source_file: str = ""
        
        # Ports
        self.inputs: list[PortInfo] = []
        self.outputs: list[PortInfo] = []
        
        # Hierarchy
        self.hierarchy: dict[str, HierarchyNode] = {}
        
        # Gates (flattened name -> info)
        self.gates: dict[str, GateInfo] = {}
        
        # Connections
        self.connections: list[ConnectionInfo] = []
        
        # Constants
        self.constants: dict[str, ConstantInfo] = {}
        
        # Source map: file -> line -> list of gate names
        self.source_map: dict[str, dict[int, list[str]]] = {}
    
    @property
    def num_gates(self) -> int:
        """Total number of gates."""
        return len(self.gates)
    
    @property
    def gate_counts(self) -> dict[str, int]:
        """Count of gates by type."""
        counts: dict[str, int] = {}
        for gate in self.gates.values():
            counts[gate.gate_type] = counts.get(gate.gate_type, 0) + 1
        return counts
    
    def get_gate(self, name: str) -> Optional[GateInfo]:
        """Get gate info by flattened name."""
        return self.gates.get(name)
    
    def get_gates_by_pattern(self, pattern: str) -> list[GateInfo]:
        """Get gates matching a pattern (supports * wildcard)."""
        import fnmatch
        return [
            gate for name, gate in self.gates.items()
            if fnmatch.fnmatch(name, pattern)
        ]
    
    def get_gates_at_line(self, file: str, line: int) -> list[str]:
        """Get gate names that originated from a source line."""
        if file in self.source_map:
            return self.source_map[file].get(line, [])
        return []
    
    def get_instance(self, path: str) -> Optional[InstanceInfo]:
        """
        Get instance info by path (e.g., "fa1" or "fa1/x1").
        """
        parts = path.split("/")
        
        # Find the top-level hierarchy node
        for node in self.hierarchy.values():
            if parts[0] in node.instances:
                current = node.instances[parts[0]]
                for part in parts[1:]:
                    if part in current.children:
                        current = current.children[part]
                    else:
                        return None
                return current
        return None
    
    def get_input(self, name: str) -> Optional[PortInfo]:
        """Get input port by name."""
        for port in self.inputs:
            if port.name == name:
                return port
        return None
    
    def get_output(self, name: str) -> Optional[PortInfo]:
        """Get output port by name."""
        for port in self.outputs:
            if port.name == name:
                return port
        return None
    
    def get_port(self, name: str) -> Optional[PortInfo]:
        """Get any port by name."""
        return self.get_input(name) or self.get_output(name)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "component": self.component,
            "source_file": self.source_file,
            "ports": {
                "inputs": [p.to_dict() for p in self.inputs],
                "outputs": [p.to_dict() for p in self.outputs],
            },
            "hierarchy": {
                name: node.to_dict() 
                for name, node in self.hierarchy.items()
            },
            "gates": {
                name: gate.to_dict() 
                for name, gate in self.gates.items()
            },
            "connections": [c.to_dict() for c in self.connections],
            "constants": {
                name: const.to_dict() 
                for name, const in self.constants.items()
            },
            "source_map": self.source_map,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
    
    def save(self, path: Path | str) -> None:
        """Save to a .shdb file."""
        path = Path(path)
        with open(path, "w") as f:
            f.write(self.to_json())
    
    @classmethod
    def from_dict(cls, data: dict) -> "DebugInfo":
        """Create from dictionary."""
        info = cls()
        info.version = data.get("version", cls.VERSION)
        info.component = data.get("component", "")
        info.source_file = data.get("source_file", "")
        
        # Ports
        ports = data.get("ports", {})
        info.inputs = [
            PortInfo.from_dict(p) for p in ports.get("inputs", [])
        ]
        info.outputs = [
            PortInfo.from_dict(p) for p in ports.get("outputs", [])
        ]
        
        # Hierarchy
        for name, node_data in data.get("hierarchy", {}).items():
            info.hierarchy[name] = HierarchyNode.from_dict(name, node_data)
        
        # Gates
        for name, gate_data in data.get("gates", {}).items():
            info.gates[name] = GateInfo.from_dict(name, gate_data)
        
        # Connections
        info.connections = [
            ConnectionInfo.from_dict(c) for c in data.get("connections", [])
        ]
        
        # Constants
        for name, const_data in data.get("constants", {}).items():
            info.constants[name] = ConstantInfo.from_dict(name, const_data)
        
        # Source map
        info.source_map = data.get("source_map", {})
        # Convert string keys back to int for line numbers
        for file in info.source_map:
            info.source_map[file] = {
                int(line): gates 
                for line, gates in info.source_map[file].items()
            }
        
        return info
    
    @classmethod
    def load(cls, path: Path | str) -> "DebugInfo":
        """Load from a .shdb file."""
        path = Path(path)
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def __repr__(self) -> str:
        return (
            f"DebugInfo({self.component}, "
            f"{len(self.inputs)} inputs, "
            f"{len(self.outputs)} outputs, "
            f"{self.num_gates} gates)"
        )
