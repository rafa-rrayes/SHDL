"""
Semantic Analyzer for Base SHDL

Validates Base SHDL after parsing to ensure:
- All instance references are valid
- All port references are valid
- Bit indices are in bounds
- No duplicate instance names
- All inputs are connected (warning)
- No multiple drivers to same signal (error)
"""

from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

from .ast import (
    Module, Component, Port, Instance, Connection, SignalRef,
    PrimitiveType
)


@dataclass
class DiagnosticMessage:
    """A diagnostic message (error or warning)."""
    message: str
    line: int
    column: int
    is_error: bool = True
    
    def __str__(self) -> str:
        level = "Error" if self.is_error else "Warning"
        return f"{level} at line {self.line}: {self.message}"


@dataclass
class PortInfo:
    """Information about a resolved port."""
    name: str
    width: int  # 1 for single-bit
    is_input: bool
    is_output: bool


@dataclass
class GateInfo:
    """Information about a gate for code generation."""
    instance_name: str
    primitive: PrimitiveType
    # Lane assignment (computed during analysis)
    chunk: int = 0      # Which 64-bit chunk
    lane: int = 0       # Bit position within chunk (0-63)
    
    @property
    def lane_mask(self) -> int:
        """Get the bit mask for this lane."""
        return 1 << self.lane


@dataclass
class SignalInfo:
    """Information about a resolved signal reference."""
    # Source information
    signal: SignalRef
    
    # Resolved location
    is_component_port: bool = False
    is_instance_port: bool = False
    
    # For component ports
    port_name: Optional[str] = None
    bit_index: Optional[int] = None  # 0-based for internal use
    
    # For instance ports  
    instance_name: Optional[str] = None
    instance_port: Optional[str] = None  # A, B, or O


@dataclass
class ConnectionInfo:
    """Analyzed connection information."""
    source: SignalInfo
    destination: SignalInfo
    connection: Connection


@dataclass
class AnalysisResult:
    """Results of semantic analysis."""
    component: Component
    
    # Diagnostics
    errors: list[DiagnosticMessage] = field(default_factory=list)
    warnings: list[DiagnosticMessage] = field(default_factory=list)
    
    # Symbol tables
    instances: dict[str, Instance] = field(default_factory=dict)
    input_ports: dict[str, Port] = field(default_factory=dict)
    output_ports: dict[str, Port] = field(default_factory=dict)
    
    # Gate organization (by type)
    gates_by_type: dict[PrimitiveType, list[GateInfo]] = field(default_factory=dict)
    gate_info: dict[str, GateInfo] = field(default_factory=dict)  # name -> info
    
    # Analyzed connections
    analyzed_connections: list[ConnectionInfo] = field(default_factory=list)
    
    # Driver tracking (which signals drive which destinations)
    drivers: dict[str, list[SignalInfo]] = field(default_factory=lambda: defaultdict(list))
    
    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    @property
    def all_diagnostics(self) -> list[DiagnosticMessage]:
        """Get all diagnostic messages (errors first, then warnings)."""
        return self.errors + self.warnings
    
    def get_chunks_for_type(self, ptype: PrimitiveType) -> int:
        """Get the number of 64-bit chunks needed for a primitive type."""
        gates = self.gates_by_type.get(ptype, [])
        if not gates:
            return 0
        max_chunk = max(g.chunk for g in gates)
        return max_chunk + 1


class SemanticAnalyzer:
    """
    Performs semantic analysis on a Base SHDL component.
    
    Validates:
    1. All instance declarations are unique
    2. All instance references in connections exist
    3. All port references are valid for the primitive type
    4. Bit indices are within bounds for component ports
    5. All instance inputs are connected
    6. No signal has multiple drivers
    
    Computes:
    1. Lane assignments for bit-packing
    2. Connection resolution
    """
    
    def __init__(self, component: Component):
        self.component = component
        self.result = AnalysisResult(component=component)
    
    def analyze(self) -> AnalysisResult:
        """Perform full semantic analysis."""
        self._build_symbol_tables()
        self._validate_instances()
        self._assign_lanes()
        self._analyze_connections()
        self._check_unconnected_inputs()
        return self.result
    
    def _error(self, message: str, line: int, column: int) -> None:
        """Add an error diagnostic."""
        self.result.errors.append(DiagnosticMessage(
            message=message,
            line=line,
            column=column,
            is_error=True
        ))
    
    def _warning(self, message: str, line: int, column: int) -> None:
        """Add a warning diagnostic."""
        self.result.warnings.append(DiagnosticMessage(
            message=message,
            line=line,
            column=column,
            is_error=False
        ))
    
    def _build_symbol_tables(self) -> None:
        """Build symbol tables for ports and instances."""
        # Input ports
        for port in self.component.inputs:
            if port.name in self.result.input_ports:
                self._error(
                    f"Duplicate input port '{port.name}'",
                    port.line, port.column
                )
            else:
                self.result.input_ports[port.name] = port
        
        # Output ports
        for port in self.component.outputs:
            if port.name in self.result.output_ports:
                self._error(
                    f"Duplicate output port '{port.name}'",
                    port.line, port.column
                )
            elif port.name in self.result.input_ports:
                self._error(
                    f"Port '{port.name}' declared as both input and output",
                    port.line, port.column
                )
            else:
                self.result.output_ports[port.name] = port
        
        # Instances
        for inst in self.component.instances:
            if inst.name in self.result.instances:
                prev = self.result.instances[inst.name]
                self._error(
                    f"Instance '{inst.name}' already declared at line {prev.line}",
                    inst.line, inst.column
                )
            else:
                self.result.instances[inst.name] = inst
    
    def _validate_instances(self) -> None:
        """Validate that all instance types are primitives."""
        for inst in self.component.instances:
            # All instances should already be primitives in Base SHDL
            # This is just a sanity check
            pass
    
    def _assign_lanes(self) -> None:
        """Assign lane positions to each gate for bit-packing."""
        # Group instances by type
        by_type: dict[PrimitiveType, list[Instance]] = defaultdict(list)
        for inst in self.component.instances:
            by_type[inst.primitive].append(inst)
        
        # Assign lanes (64 per chunk)
        for ptype, instances in by_type.items():
            gates = []
            for i, inst in enumerate(instances):
                chunk = i // 64
                lane = i % 64
                gate_info = GateInfo(
                    instance_name=inst.name,
                    primitive=ptype,
                    chunk=chunk,
                    lane=lane
                )
                gates.append(gate_info)
                self.result.gate_info[inst.name] = gate_info
            
            self.result.gates_by_type[ptype] = gates
    
    def _analyze_connections(self) -> None:
        """Analyze all connections."""
        for conn in self.component.connections:
            src_info = self._resolve_signal(conn.source, is_source=True)
            dst_info = self._resolve_signal(conn.destination, is_source=False)
            
            if src_info and dst_info:
                conn_info = ConnectionInfo(
                    source=src_info,
                    destination=dst_info,
                    connection=conn
                )
                self.result.analyzed_connections.append(conn_info)
                
                # Track drivers
                dst_key = self._signal_key(dst_info)
                self.result.drivers[dst_key].append(src_info)
                
                # Check for multiple drivers
                if len(self.result.drivers[dst_key]) > 1:
                    self._error(
                        f"Signal '{dst_key}' has multiple drivers",
                        conn.line, conn.column
                    )
    
    def _signal_key(self, info: SignalInfo) -> str:
        """Create a unique key for a signal."""
        if info.is_component_port:
            if info.bit_index is not None:
                return f"{info.port_name}[{info.bit_index + 1}]"
            return info.port_name
        else:
            return f"{info.instance_name}.{info.instance_port}"
    
    def _resolve_signal(self, signal: SignalRef, is_source: bool) -> Optional[SignalInfo]:
        """Resolve a signal reference to full information."""
        if signal.instance is not None:
            # Instance port reference
            return self._resolve_instance_port(signal, is_source)
        else:
            # Component port reference
            return self._resolve_component_port(signal, is_source)
    
    def _resolve_component_port(self, signal: SignalRef, is_source: bool) -> Optional[SignalInfo]:
        """Resolve a component port reference."""
        name = signal.name
        index = signal.index  # 1-based
        
        # Find the port
        port = None
        is_input = False
        is_output = False
        
        if name in self.result.input_ports:
            port = self.result.input_ports[name]
            is_input = True
        elif name in self.result.output_ports:
            port = self.result.output_ports[name]
            is_output = True
        else:
            self._error(
                f"Unknown port '{name}'",
                signal.line, signal.column
            )
            return None
        
        # Validate direction
        if is_source and is_output:
            self._error(
                f"Output port '{name}' cannot be used as a source",
                signal.line, signal.column
            )
            return None
        
        if not is_source and is_input:
            self._error(
                f"Input port '{name}' cannot be used as a destination",
                signal.line, signal.column
            )
            return None
        
        # Validate index
        bit_index = None
        if index is not None:
            if port.width is None:
                self._error(
                    f"Port '{name}' is single-bit but indexed with [{index}]",
                    signal.line, signal.column
                )
                return None
            
            if index < 1 or index > port.width:
                self._error(
                    f"Bit index {index} out of range for port '{name}[{port.width}]' (valid range: 1-{port.width})",
                    signal.line, signal.column
                )
                return None
            
            bit_index = index - 1  # Convert to 0-based
        elif port.width is not None:
            # Multi-bit port without index - could be an error or a default
            # For now, treat as accessing bit 1 with a warning
            self._warning(
                f"Multi-bit port '{name}[{port.width}]' used without index, assuming bit 1",
                signal.line, signal.column
            )
            bit_index = 0
        
        return SignalInfo(
            signal=signal,
            is_component_port=True,
            port_name=name,
            bit_index=bit_index
        )
    
    def _resolve_instance_port(self, signal: SignalRef, is_source: bool) -> Optional[SignalInfo]:
        """Resolve an instance port reference."""
        inst_name = signal.instance
        port_name = signal.name
        
        # Find the instance
        if inst_name not in self.result.instances:
            self._error(
                f"Unknown instance '{inst_name}'",
                signal.line, signal.column
            )
            return None
        
        inst = self.result.instances[inst_name]
        prim = inst.primitive
        
        # Validate port name
        valid_inputs = prim.input_ports
        valid_outputs = prim.output_ports
        
        if port_name in valid_outputs:
            if not is_source:
                self._error(
                    f"Output port '{inst_name}.{port_name}' cannot be used as a destination",
                    signal.line, signal.column
                )
                return None
        elif port_name in valid_inputs:
            if is_source:
                self._error(
                    f"Input port '{inst_name}.{port_name}' cannot be used as a source",
                    signal.line, signal.column
                )
                return None
        else:
            all_ports = valid_inputs + valid_outputs
            self._error(
                f"Port '{port_name}' does not exist on primitive '{prim.to_string()}' (valid ports: {', '.join(all_ports)})",
                signal.line, signal.column
            )
            return None
        
        return SignalInfo(
            signal=signal,
            is_instance_port=True,
            instance_name=inst_name,
            instance_port=port_name
        )
    
    def _check_unconnected_inputs(self) -> None:
        """Check for unconnected gate inputs."""
        # Track which instance inputs are connected
        connected_inputs: set[str] = set()
        
        for conn_info in self.result.analyzed_connections:
            dst = conn_info.destination
            if dst.is_instance_port:
                key = f"{dst.instance_name}.{dst.instance_port}"
                connected_inputs.add(key)
        
        # Check each instance
        for inst_name, inst in self.result.instances.items():
            prim = inst.primitive
            for port in prim.input_ports:
                key = f"{inst_name}.{port}"
                if key not in connected_inputs:
                    self._warning(
                        f"Input '{key}' is not connected",
                        inst.line, inst.column
                    )


def analyze(component: Component) -> AnalysisResult:
    """Analyze a component and return the result."""
    analyzer = SemanticAnalyzer(component)
    return analyzer.analyze()


def analyze_module(module: Module) -> list[AnalysisResult]:
    """Analyze all components in a module."""
    results = []
    for comp in module.components:
        results.append(analyze(comp))
    return results
