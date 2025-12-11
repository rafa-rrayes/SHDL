"""
SHDL Connection Checking

Validates connection completeness and correctness:
- All input ports connected
- All output ports driven  
- No multiply-driven signals
- No undriven signals
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, Tuple
from collections import defaultdict

from ..flattener.ast import (
    Component, Connection, Signal, Generator, ConnectBlock, Node
)
from ..source_map import SourceSpan
from ..errors import (
    ErrorCode, DiagnosticCollection,
    Annotation, Suggestion, RelatedInfo
)
from .resolver import SymbolTable, InstanceInfo, SignalInfo


@dataclass
class ConnectionInfo:
    """Information about a connection endpoint."""
    span: SourceSpan
    full_name: str  # e.g., "inst.A" or "PortName[3]"


class ConnectionChecker:
    """
    Checks connection completeness and correctness.
    
    Validates:
    - Every instance input port is connected
    - Every component output port is driven
    - No signal is driven by multiple sources
    - Warns about unconnected instance outputs
    """
    
    def __init__(
        self,
        diagnostics: DiagnosticCollection,
        symbol_table: SymbolTable
    ):
        self.diagnostics = diagnostics
        self.table = symbol_table
        
        # Track what drives each signal/port
        # Key: normalized signal name, Value: list of drivers
        self._drivers: Dict[str, List[ConnectionInfo]] = defaultdict(list)
        
        # Track what each signal is connected to (as destination)
        self._connections: Dict[str, List[ConnectionInfo]] = defaultdict(list)
        
        # Track which instance ports have been connected
        self._connected_instance_inputs: Set[str] = set()  # "inst.port"
        self._connected_instance_outputs: Set[str] = set()  # "inst.port"
        
        # Track which component output ports are driven
        self._driven_outputs: Set[str] = set()
    
    def check_component(self, component: Component) -> None:
        """Check all connections in a component."""
        # First pass: collect all connections
        if component.connect_block:
            self._collect_connections(component.connect_block, {})
        
        # Check for multiply-driven signals
        self._check_multiply_driven()
        
        # Check that all instance inputs are connected
        self._check_instance_inputs()
        
        # Check that all component outputs are driven
        self._check_output_ports(component)
        
        # Warn about unconnected instance outputs
        self._warn_unconnected_outputs()
    
    def _collect_connections(
        self,
        block: ConnectBlock,
        gen_vars: Dict[str, int]
    ) -> None:
        """Collect all connections from a connect block."""
        for node in block.statements:
            if isinstance(node, Connection):
                self._record_connection(node, gen_vars)
            elif isinstance(node, Generator):
                self._collect_generator_connections(node, gen_vars)
    
    def _collect_generator_connections(
        self,
        gen: Generator,
        outer_vars: Dict[str, int]
    ) -> None:
        """Collect connections from a generator."""
        from ..flattener.flattener import expand_range
        
        try:
            values = expand_range(gen.range_spec)
        except Exception:
            return  # Error already reported
        
        for val in values:
            new_vars = dict(outer_vars)
            new_vars[gen.variable] = val
            
            for node in gen.body:
                if isinstance(node, Connection):
                    self._record_connection(node, new_vars)
                elif isinstance(node, Generator):
                    self._collect_generator_connections(node, new_vars)
    
    def _record_connection(
        self,
        conn: Connection,
        gen_vars: Dict[str, int]
    ) -> None:
        """Record a single connection."""
        src_name = self._normalize_signal(conn.source, gen_vars)
        dst_name = self._normalize_signal(conn.destination, gen_vars)
        
        if src_name is None or dst_name is None:
            return  # Error already reported
        
        src_info = ConnectionInfo(span=conn.source.span, full_name=src_name)
        dst_info = ConnectionInfo(span=conn.destination.span, full_name=dst_name)
        
        # Record that dst is driven by src
        self._drivers[dst_name].append(src_info)
        self._connections[src_name].append(dst_info)
        
        # Track instance port connections
        if "." in dst_name:
            base = dst_name.split("[")[0]  # Remove index if present
            self._connected_instance_inputs.add(base)
        
        if "." in src_name:
            base = src_name.split("[")[0]
            self._connected_instance_outputs.add(base)
        
        # Track component output driving
        dst_base = dst_name.split("[")[0]
        if dst_base in self.table.output_ports:
            self._driven_outputs.add(dst_base)
    
    def _normalize_signal(
        self,
        signal: Signal,
        gen_vars: Dict[str, int]
    ) -> Optional[str]:
        """
        Create a normalized string name for a signal.
        
        Returns: "name", "name[idx]", "inst.port", or "inst.port[idx]"
        """
        from ..flattener.flattener import substitute_name, evaluate_expr
        
        name = substitute_name(signal.name, gen_vars)
        instance = substitute_name(signal.instance, gen_vars) if signal.instance else None
        
        if instance:
            base = f"{instance}.{name}"
        else:
            base = name
        
        if signal.index and not signal.index.is_slice:
            if signal.index.start is not None:
                try:
                    idx = evaluate_expr(signal.index.start, gen_vars)
                    return f"{base}[{idx}]"
                except Exception:
                    return None
        
        return base
    
    def _check_multiply_driven(self) -> None:
        """Check for signals driven by multiple sources."""
        for signal_name, drivers in self._drivers.items():
            if len(drivers) > 1:
                primary = drivers[0]
                related = [
                    RelatedInfo(
                        span=d.span,
                        message="also driven here"
                    )
                    for d in drivers[1:]
                ]
                
                self.diagnostics.error(
                    code=ErrorCode.E0503,
                    message=f"Signal '{signal_name}' is driven by multiple sources",
                    span=primary.span,
                    annotations=[Annotation(
                        span=primary.span,
                        label="first driver"
                    )],
                    related=related
                )
    
    def _check_instance_inputs(self) -> None:
        """Check that all instance input ports are connected."""
        for inst_name, inst_info in self.table.instances.items():
            if inst_info.component is None:
                continue  # Component not resolved
            
            for port in inst_info.component.inputs:
                full_name = f"{inst_name}.{port.name}"
                
                if port.width:
                    # Vector port - check each bit
                    all_connected = True
                    for i in range(1, port.width + 1):
                        bit_name = f"{full_name}[{i}]"
                        if bit_name not in self._connected_instance_inputs and full_name not in self._connected_instance_inputs:
                            all_connected = False
                            break
                    
                    if not all_connected and full_name not in self._connected_instance_inputs:
                        self.diagnostics.error(
                            code=ErrorCode.E0501,
                            message=f"Missing connection to input port '{port.name}' of instance '{inst_name}'",
                            span=inst_info.span,
                            suggestions=[Suggestion(
                                message=f"add connection: ... -> {full_name};"
                            )]
                        )
                else:
                    # Single-bit port
                    if full_name not in self._connected_instance_inputs:
                        self.diagnostics.error(
                            code=ErrorCode.E0501,
                            message=f"Missing connection to input port '{port.name}' of instance '{inst_name}'",
                            span=inst_info.span,
                            suggestions=[Suggestion(
                                message=f"add connection: ... -> {full_name};"
                            )]
                        )
    
    def _check_output_ports(self, component: Component) -> None:
        """Check that all component output ports are driven."""
        for port in component.outputs:
            if port.name not in self._driven_outputs:
                # Check if any bits are driven for vector ports
                if port.width:
                    any_driven = False
                    for i in range(1, port.width + 1):
                        if f"{port.name}[{i}]" in self._drivers:
                            any_driven = True
                            break
                    if any_driven:
                        continue
                
                self.diagnostics.error(
                    code=ErrorCode.E0502,
                    message=f"Output port '{port.name}' is never driven",
                    span=port.span,
                    suggestions=[Suggestion(
                        message=f"add connection: ... -> {port.name};"
                    )]
                )
    
    def _warn_unconnected_outputs(self) -> None:
        """Warn about unconnected instance outputs (potential dead code)."""
        for inst_name, inst_info in self.table.instances.items():
            if inst_info.component is None:
                continue
            
            for port in inst_info.component.outputs:
                full_name = f"{inst_name}.{port.name}"
                
                if full_name not in self._connected_instance_outputs:
                    # Check individual bits for vector outputs
                    any_connected = False
                    if port.width:
                        for i in range(1, port.width + 1):
                            if f"{full_name}[{i}]" in self._connections:
                                any_connected = True
                                break
                    
                    if not any_connected:
                        self.diagnostics.warning(
                            code=ErrorCode.W0107,
                            message=f"Output '{port.name}' of instance '{inst_name}' is not connected",
                            span=inst_info.span,
                            notes=["this may indicate dead code"]
                        )
