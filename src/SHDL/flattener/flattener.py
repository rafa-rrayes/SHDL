"""
SHDL Flattener

Transforms Expanded SHDL into Base SHDL through a multi-phase process:
1. Generator Expansion
2. Expander Expansion  
3. Constant Materialization
4. Hierarchy Flattening
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from copy import deepcopy
import re

from .ast import (
    Module, Component, Port, Instance, Constant, Connection,
    Signal, IndexExpr, ArithmeticExpr, NumberLiteral, VariableRef, BinaryOp,
    Generator, RangeSpec, SimpleRange, StartEndRange, MultiRange,
    Import, ConnectBlock, Node
)
from .parser import parse, parse_file
from ..errors import FlattenerError


# =============================================================================
# Primitive Gates
# =============================================================================

PRIMITIVE_GATES = {"AND", "OR", "NOT", "XOR", "__VCC__", "__GND__"}


def is_primitive(component_type: str) -> bool:
    """Check if a component type is a primitive gate."""
    return component_type in PRIMITIVE_GATES


# =============================================================================
# Arithmetic Expression Evaluation
# =============================================================================

def evaluate_expr(expr: ArithmeticExpr, variables: dict[str, int]) -> int:
    """Evaluate an arithmetic expression with the given variable bindings."""
    if isinstance(expr, NumberLiteral):
        return expr.value
    
    if isinstance(expr, VariableRef):
        if expr.name not in variables:
            raise FlattenerError(f"Undefined variable: {expr.name}")
        return variables[expr.name]
    
    if isinstance(expr, BinaryOp):
        left = evaluate_expr(expr.left, variables)
        right = evaluate_expr(expr.right, variables)
        
        if expr.operator == "+":
            return left + right
        elif expr.operator == "-":
            return left - right
        elif expr.operator == "*":
            return left * right
        elif expr.operator == "/":
            return left // right
        else:
            raise FlattenerError(f"Unknown operator: {expr.operator}")
    
    raise FlattenerError(f"Unknown expression type: {type(expr)}")


# =============================================================================
# Range Expansion
# =============================================================================

def expand_range(spec: RangeSpec, max_value: Optional[int] = None) -> list[int]:
    """Expand a range specification into a list of integer values."""
    if isinstance(spec, SimpleRange):
        return list(range(1, spec.end + 1))
    
    if isinstance(spec, StartEndRange):
        start = spec.start if spec.start is not None else 1
        end = spec.end if spec.end is not None else max_value
        if end is None:
            raise FlattenerError("Open-ended range requires context for max value")
        return list(range(start, end + 1))
    
    if isinstance(spec, MultiRange):
        result: list[int] = []
        for r in spec.ranges:
            result.extend(expand_range(r, max_value))
        return result
    
    raise FlattenerError(f"Unknown range type: {type(spec)}")


# =============================================================================
# Name Substitution
# =============================================================================

def substitute_name(name: str, variables: dict[str, int]) -> str:
    """
    Substitute variable references in a name using eval.
    
    Example: "gate{i}" with i=3 -> "gate3"
             "cell{i}_{j}" with i=2, j=4 -> "cell2_4"
             "bit{i+1}" with i=3 -> "bit4"
    """
    pattern = re.compile(r'\{([^}]+)\}')
    
    def replace_expr(match: re.Match) -> str:
        expr_str = match.group(1)
        try:
            # Evaluate the expression with the given variables
            result = eval(expr_str, {"__builtins__": {}}, variables)
            return str(result)
        except Exception:
            # If eval fails, return as-is
            return match.group(0)
    
    return pattern.sub(replace_expr, name)


def substitute_signal(signal: Signal, variables: dict[str, int]) -> Signal:
    """Substitute variables in a signal reference."""
    new_name = substitute_name(signal.name, variables)
    new_instance = substitute_name(signal.instance, variables) if signal.instance else None
    
    new_index: Optional[IndexExpr] = None
    if signal.index:
        new_start = None
        new_end = None
        
        if signal.index.start is not None:
            if isinstance(signal.index.start, NumberLiteral):
                new_start = signal.index.start
            else:
                new_start = NumberLiteral(value=evaluate_expr(signal.index.start, variables))
        
        if signal.index.end is not None:
            if isinstance(signal.index.end, NumberLiteral):
                new_end = signal.index.end
            else:
                new_end = NumberLiteral(value=evaluate_expr(signal.index.end, variables))
        
        new_index = IndexExpr(start=new_start, end=new_end, is_slice=signal.index.is_slice)
    
    return Signal(name=new_name, instance=new_instance, index=new_index)


# =============================================================================
# Phase 2: Generator Expansion
# =============================================================================

def expand_generators_in_list(nodes: list[Node], variables: dict[str, int] = None) -> list[Node]:
    """Expand all generators in a list of nodes."""
    if variables is None:
        variables = {}
    
    result: list[Node] = []
    
    for node in nodes:
        if isinstance(node, Generator):
            expanded = expand_generator(node, variables)
            result.extend(expanded)
        elif isinstance(node, Instance):
            # Substitute variables in instance name
            new_name = substitute_name(node.name, variables)
            result.append(Instance(
                name=new_name,
                component_type=node.component_type,
                line=node.line,
                column=node.column
            ))
        elif isinstance(node, Constant):
            new_name = substitute_name(node.name, variables)
            result.append(Constant(
                name=new_name,
                value=node.value,
                width=node.width,
                line=node.line,
                column=node.column
            ))
        elif isinstance(node, Connection):
            new_source = substitute_signal(node.source, variables)
            new_dest = substitute_signal(node.destination, variables)
            result.append(Connection(source=new_source, destination=new_dest))
        else:
            result.append(node)
    
    return result


def expand_generator(gen: Generator, outer_variables: dict[str, int]) -> list[Node]:
    """Expand a single generator into its constituent nodes."""
    values = expand_range(gen.range_spec)
    result: list[Node] = []
    
    for value in values:
        # Create new variable scope
        variables = dict(outer_variables)
        variables[gen.variable] = value
        
        # Recursively expand the body
        expanded = expand_generators_in_list(gen.body, variables)
        result.extend(expanded)
    
    return result


# =============================================================================
# Phase 3: Expander Expansion
# =============================================================================

def expand_expanders_in_connections(connections: list[Node]) -> list[Node]:
    """Expand all slice notation in connections to individual bit connections."""
    result: list[Node] = []
    
    for node in connections:
        if isinstance(node, Connection):
            expanded = expand_connection_slices(node)
            result.extend(expanded)
        else:
            result.append(node)
    
    return result


def expand_connection_slices(conn: Connection) -> list[Connection]:
    """Expand a connection with slices into individual bit connections."""
    src = conn.source
    dst = conn.destination
    
    # Check if either side has a slice
    src_is_slice = src.index and src.index.is_slice
    dst_is_slice = dst.index and dst.index.is_slice
    
    if not src_is_slice and not dst_is_slice:
        return [conn]
    
    # Determine the range
    if src_is_slice and src.index:
        start = evaluate_expr(src.index.start, {}) if src.index.start else 1
        end = evaluate_expr(src.index.end, {}) if src.index.end else None
        if end is None:
            raise FlattenerError("Cannot expand open-ended slice without context")
    elif dst_is_slice and dst.index:
        start = evaluate_expr(dst.index.start, {}) if dst.index.start else 1
        end = evaluate_expr(dst.index.end, {}) if dst.index.end else None
        if end is None:
            raise FlattenerError("Cannot expand open-ended slice without context")
    else:
        return [conn]
    
    # Generate individual connections
    result: list[Connection] = []
    
    src_start = start
    dst_start = start
    
    if src_is_slice and src.index:
        src_start = evaluate_expr(src.index.start, {}) if src.index.start else 1
    if dst_is_slice and dst.index:
        dst_start = evaluate_expr(dst.index.start, {}) if dst.index.start else 1
    
    width = end - start + 1
    
    for i in range(width):
        new_src = Signal(
            name=src.name,
            instance=src.instance,
            index=IndexExpr(start=NumberLiteral(value=src_start + i), is_slice=False) if src_is_slice else src.index
        )
        new_dst = Signal(
            name=dst.name,
            instance=dst.instance,
            index=IndexExpr(start=NumberLiteral(value=dst_start + i), is_slice=False) if dst_is_slice else dst.index
        )
        result.append(Connection(source=new_src, destination=new_dst))
    
    return result


# =============================================================================
# Phase 4: Constant Materialization
# =============================================================================

def materialize_constants(component: Component) -> Component:
    """Convert named constants to __VCC__ and __GND__ instances."""
    new_instances: list[Node] = []
    constants: dict[str, int] = {}
    
    # First pass: collect constants and create power pin instances
    for node in component.instances:
        if isinstance(node, Constant):
            constants[node.name] = node.value
            # Determine bit width: use explicit width if provided, otherwise infer from value
            value = node.value
            if node.width is not None:
                bit_width = node.width
            elif value == 0:
                bit_width = 1
            else:
                bit_width = value.bit_length()
            
            # Create __VCC__ or __GND__ instances for each bit
            for bit in range(1, bit_width + 1):
                bit_value = (value >> (bit - 1)) & 1
                pin_type = "__VCC__" if bit_value else "__GND__"
                new_instances.append(Instance(
                    name=f"{node.name}_bit{bit}",
                    component_type=pin_type,
                    line=node.line,
                    column=node.column
                ))
        else:
            new_instances.append(node)
    
    # Second pass: update connections to use the materialized constants
    new_connections: list[Node] = []
    
    if component.connect_block:
        for node in component.connect_block.statements:
            if isinstance(node, Connection):
                new_conn = rewrite_constant_refs(node, constants)
                new_connections.append(new_conn)
            else:
                new_connections.append(node)
    
    return Component(
        name=component.name,
        inputs=component.inputs,
        outputs=component.outputs,
        instances=new_instances,
        connect_block=ConnectBlock(statements=new_connections) if new_connections else None,
        line=component.line,
        column=component.column
    )


def rewrite_constant_refs(conn: Connection, constants: dict[str, int]) -> Connection:
    """Rewrite constant references in a connection to use power pin instances."""
    new_source = rewrite_signal_constant(conn.source, constants)
    new_dest = rewrite_signal_constant(conn.destination, constants)
    return Connection(source=new_source, destination=new_dest)


def rewrite_signal_constant(signal: Signal, constants: dict[str, int]) -> Signal:
    """Rewrite a signal if it references a constant."""
    if signal.instance is None and signal.name in constants:
        # This is a constant reference
        if signal.index and signal.index.start:
            bit = evaluate_expr(signal.index.start, {})
        else:
            # No index specified - default to bit 1 (for single-bit constants like ZERO, ONE)
            bit = 1
        # The constant bit is materialized as an instance (e.g., Hundred_bit1: __VCC__)
        # So we need to access its output port: Hundred_bit1.O
        return Signal(
            name="O",  # Output port of __VCC__/__GND__
            instance=f"{signal.name}_bit{bit}",
            index=None
        )
    return signal


# =============================================================================
# Phase 5: Hierarchy Flattening
# =============================================================================

@dataclass
class ComponentLibrary:
    """A collection of component definitions for resolving references."""
    
    components: dict[str, Component] = field(default_factory=dict)
    search_paths: list[Path] = field(default_factory=list)
    _loaded_modules: set[str] = field(default_factory=set)  # Track loaded module files
    
    def add(self, component: Component) -> None:
        """Add a component to the library."""
        self.components[component.name] = component
    
    def get(self, name: str) -> Optional[Component]:
        """Get a component by name."""
        return self.components.get(name)
    
    def load_module(self, module_name: str) -> bool:
        """
        Load a module file by its module name (as used in 'use' statements).
        Returns True if the module was found and loaded.
        """
        if module_name in self._loaded_modules:
            return True
        
        for path in self.search_paths:
            # Module name maps directly to filename: use foo::{Bar} -> foo.shdl
            file_path = path / f"{module_name}.shdl"
            if file_path.exists():
                module = parse_file(str(file_path))
                for comp in module.components:
                    self.add(comp)
                # Process imports in the loaded module
                for imp in module.imports:
                    self.load_module(imp.module)
                self._loaded_modules.add(module_name)
                return True
        
        return False
    
    def resolve(self, name: str) -> Component:
        """Resolve a component by name. It must already be loaded via imports."""
        if name in self.components:
            return self.components[name]
        
        raise FlattenerError(f"Cannot resolve component: {name}. Make sure it is imported via 'use' statement.")


@dataclass
class PortMapping:
    """
    Port mapping information for a flattened instance.
    
    For input ports: maps port name to list of internal destinations (fan-out)
    For output ports: maps port name to the single internal source
    """
    input_mappings: dict[str, list[str]] = field(default_factory=dict)  # port -> [internal destinations]
    output_mappings: dict[str, str] = field(default_factory=dict)  # port -> internal source


def flatten_hierarchy(component: Component, library: ComponentLibrary, prefix: str = "") -> Component:
    """Flatten a component by inlining all subcomponent instances."""
    new_instances: list[Instance] = []
    new_connections: list[Connection] = []
    
    # Collect port mappings for each instance
    # Maps: instance_name -> PortMapping
    port_mappings: dict[str, PortMapping] = {}
    
    for node in component.instances:
        if isinstance(node, Instance):
            if is_primitive(node.component_type):
                # Keep primitive instances, but apply prefix
                new_name = f"{prefix}{node.name}" if prefix else node.name
                new_instances.append(Instance(
                    name=new_name,
                    component_type=node.component_type,
                    line=node.line,
                    column=node.column
                ))
            else:
                # Resolve and flatten the subcomponent
                sub_component = library.resolve(node.component_type)
                
                # First, flatten the subcomponent itself (recursively)
                sub_prefix = f"{prefix}{node.name}_"
                flattened_sub = flatten_component_full(sub_component, library, sub_prefix)
                
                # Add all instances from the flattened subcomponent
                for sub_inst in flattened_sub.instances:
                    if isinstance(sub_inst, Instance):
                        new_instances.append(sub_inst)
                
                # Build port mapping for this instance
                port_mappings[node.name] = build_port_mapping(sub_component, flattened_sub, sub_prefix)
                
                # Add internal connections from the flattened subcomponent
                # But SKIP connections that involve ports (those are handled by parent rewiring)
                if flattened_sub.connect_block:
                    for conn in flattened_sub.connect_block.statements:
                        if isinstance(conn, Connection):
                            src_is_in, src_is_out = is_port_signal(conn.source, sub_component)
                            dst_is_in, dst_is_out = is_port_signal(conn.destination, sub_component)
                            
                            # Skip connections FROM input ports (handled by parent rewiring)
                            if src_is_in:
                                continue
                            # Skip connections TO output ports (handled by parent rewiring)
                            if dst_is_out:
                                continue
                            # These are internal connections - keep them
                            new_connections.append(conn)
    
    # Process connections from the parent, rewiring through port mappings
    if component.connect_block:
        for node in component.connect_block.statements:
            if isinstance(node, Connection):
                rewired = rewire_connection(node, port_mappings, prefix, component)
                new_connections.extend(rewired)
    
    return Component(
        name=component.name,
        inputs=component.inputs,
        outputs=component.outputs,
        instances=new_instances,
        connect_block=ConnectBlock(statements=new_connections) if new_connections else None,
        line=component.line,
        column=component.column
    )


def is_input_port(name: str, component: Component) -> bool:
    """Check if a name matches an input port of the component (ignoring indices)."""
    for port in component.inputs:
        if port.name == name:
            return True
    return False


def is_output_port(name: str, component: Component) -> bool:
    """Check if a name matches an output port of the component (ignoring indices)."""
    for port in component.outputs:
        if port.name == name:
            return True
    return False


def is_port_signal(signal: Signal, component: Component) -> tuple[bool, bool]:
    """
    Check if a signal references a port (input or output) of the component.
    Returns (is_input, is_output).
    A signal references a port if it has no instance and its name matches a port name.
    """
    if signal.instance is not None:
        return (False, False)
    
    is_in = any(p.name == signal.name for p in component.inputs)
    is_out = any(p.name == signal.name for p in component.outputs)
    return (is_in, is_out)


def build_port_mapping(original: Component, flattened: Component, prefix: str) -> PortMapping:
    """
    Build a mapping from port names to the internal signals that drive/receive them.
    
    For output ports: find what drives the port (single source)
    For input ports: find ALL destinations that receive from the port (fan-out)
    
    Special case - wire-through (input port -> output port):
    The output port is added to the input port's fan-out list, so when the parent
    writes to the input, it also writes to the output.
    """
    mapping = PortMapping()
    
    # First, scan the ORIGINAL component for wire-through connections
    # These are filtered out during flattening, so we need to capture them here
    if original.connect_block:
        for conn in original.connect_block.statements:
            if isinstance(conn, Connection):
                src_is_in, _ = is_port_signal(conn.source, original)
                _, dst_is_out = is_port_signal(conn.destination, original)
                
                # Wire-through: input -> output
                if src_is_in and dst_is_out:
                    src = conn.source
                    dst = conn.destination
                    
                    # Build input port key
                    if src.index and src.index.start:
                        idx = evaluate_expr(src.index.start, {})
                        input_key = f"{src.name}[{idx}]"
                    else:
                        input_key = src.name
                    
                    # Build output marker
                    if dst.index and dst.index.start:
                        dst_idx = evaluate_expr(dst.index.start, {})
                        output_marker = f"@OUTPUT:{dst.name}[{dst_idx}]"
                    else:
                        output_marker = f"@OUTPUT:{dst.name}"
                    
                    if input_key not in mapping.input_mappings:
                        mapping.input_mappings[input_key] = []
                    mapping.input_mappings[input_key].append(output_marker)
    
    # Then scan the flattened component for regular port connections
    if flattened.connect_block:
        for conn in flattened.connect_block.statements:
            if isinstance(conn, Connection):
                src_is_in, _ = is_port_signal(conn.source, original)
                _, dst_is_out = is_port_signal(conn.destination, original)
                
                # Check if source is an input port (input port -> something)
                if src_is_in:
                    port_name = conn.source.name
                    # Build the port key including index if present
                    if conn.source.index and conn.source.index.start:
                        idx = evaluate_expr(conn.source.index.start, {})
                        port_key = f"{port_name}[{idx}]"
                    else:
                        port_key = port_name
                    
                    # The destination - could be internal gate or output port (wire-through)
                    dst = conn.destination
                    if dst.instance:
                        internal_signal = f"{dst.instance}.{dst.name}"
                    elif dst_is_out:
                        # Wire-through: input -> output
                        # Mark with special prefix so we know it's an output port
                        if dst.index and dst.index.start:
                            dst_idx = evaluate_expr(dst.index.start, {})
                            internal_signal = f"@OUTPUT:{dst.name}[{dst_idx}]"
                        else:
                            internal_signal = f"@OUTPUT:{dst.name}"
                    else:
                        internal_signal = dst.name
                    
                    # Add to the list of destinations for this input port
                    if port_key not in mapping.input_mappings:
                        mapping.input_mappings[port_key] = []
                    mapping.input_mappings[port_key].append(internal_signal)
                
                # Check if destination is an output port (internal gate -> output port)
                # Skip wire-through here since it's handled above
                if dst_is_out and not src_is_in:
                    port_name = conn.destination.name
                    # Build the port key including index if present
                    if conn.destination.index and conn.destination.index.start:
                        idx = evaluate_expr(conn.destination.index.start, {})
                        port_key = f"{port_name}[{idx}]"
                    else:
                        port_key = port_name
                    
                    # The source is the internal signal
                    src = conn.source
                    if src.instance:
                        internal_signal = f"{src.instance}.{src.name}"
                    else:
                        internal_signal = src.name
                    mapping.output_mappings[port_key] = internal_signal
    
    return mapping


def rewire_connection(conn: Connection, port_mappings: dict[str, PortMapping], 
                      prefix: str, component: Component) -> list[Connection]:
    """Rewire a connection, replacing instance.port references with internal signals.
    
    Returns a list of connections because input port fan-out may require
    one parent connection to become multiple connections.
    """
    src = conn.source
    dst = conn.destination
    
    # Skip connections from input port to output port (wire-through)
    # These are handled via port mappings, not as actual connections
    src_is_in, _ = is_port_signal(src, component)
    _, dst_is_out = is_port_signal(dst, component)
    if src_is_in and dst_is_out:
        return []
    
    # Helper to build port key from signal
    def get_port_key(signal: Signal) -> str:
        if signal.index and signal.index.start:
            idx = evaluate_expr(signal.index.start, {})
            return f"{signal.name}[{idx}]"
        return signal.name
    
    # Check if destination is an instance port that was flattened (instance.port)
    if dst.instance and dst.instance in port_mappings:
        mapping = port_mappings[dst.instance]
        port_key = get_port_key(dst)
        
        # Check if this is an input port with fan-out
        if port_key in mapping.input_mappings:
            # Create one connection for each internal destination
            result = []
            for internal_dest in mapping.input_mappings[port_key]:
                # Check for wire-through marker (@OUTPUT:portname)
                if internal_dest.startswith("@OUTPUT:"):
                    # This is a wire-through to an output port
                    # Connect source directly to the parent's output port
                    output_ref = internal_dest[8:]  # Remove "@OUTPUT:" prefix
                    # Parse potential index like "N" or "Y[5]"
                    if "[" in output_ref:
                        out_name, idx_part = output_ref.split("[", 1)
                        out_idx = int(idx_part.rstrip("]"))
                        new_dst = Signal(name=out_name, instance=None, 
                                        index=IndexExpr(start=NumberLiteral(value=out_idx), is_slice=False))
                    else:
                        new_dst = Signal(name=output_ref, instance=None, index=None)
                elif "." in internal_dest:
                    # Parse internal_dest like "fa1_x1.A"
                    parts = internal_dest.split(".", 1)
                    new_dst = Signal(name=parts[1], instance=parts[0], index=None)
                else:
                    new_dst = Signal(name=internal_dest, instance=None, index=None)
                
                # Preserve the source signal (with its index!)
                new_src = rewire_signal_for_source(src, port_mappings, prefix, component)
                if new_src:
                    result.append(Connection(source=new_src, destination=new_dst))
            return result
    
    # Check if source is an instance port that was flattened (instance.port)
    if src.instance and src.instance in port_mappings:
        mapping = port_mappings[src.instance]
        port_key = get_port_key(src)
        
        # Check if this is an output port with a known driver
        if port_key in mapping.output_mappings:
            internal_src = mapping.output_mappings[port_key]
            # Parse internal_src like "fa1_x2.O"
            if "." in internal_src:
                parts = internal_src.split(".", 1)
                new_src = Signal(name=parts[1], instance=parts[0], index=None)
            else:
                new_src = Signal(name=internal_src, instance=None, index=None)
            
            # Preserve the destination signal (with its index!)
            new_dst = rewire_signal_for_dest(dst, port_mappings, prefix, component)
            if new_dst:
                return [Connection(source=new_src, destination=new_dst)]
            return []
        
        # Check if this is a wire-through output (driven by an input port)
        # In this case, the connection is already handled via input_mappings
        # when the parent writes to the corresponding input port
        for input_key, destinations in mapping.input_mappings.items():
            for dest in destinations:
                if dest.startswith("@OUTPUT:"):
                    output_ref = dest[8:]
                    # Check if this matches the port we're looking for
                    if output_ref == port_key or output_ref.startswith(f"{src.name}["):
                        # This output is a wire-through, skip it
                        return []
    
    # No port mapping needed - just apply prefix to primitive instance references
    new_src = rewire_signal_for_source(src, port_mappings, prefix, component)
    new_dst = rewire_signal_for_dest(dst, port_mappings, prefix, component)
    
    if new_src and new_dst:
        return [Connection(source=new_src, destination=new_dst)]
    return []


def rewire_signal_for_source(signal: Signal, port_mappings: dict[str, PortMapping], 
                             prefix: str, component: Component) -> Optional[Signal]:
    """Rewire a source signal reference, preserving indices."""
    
    if signal.instance is None:
        # It's a port reference of the current component - keep as is WITH its index
        return Signal(name=signal.name, instance=None, index=signal.index)
    
    # It's an instance.port reference
    if signal.instance in port_mappings:
        # This is a reference to a non-primitive instance that was flattened
        mapping = port_mappings[signal.instance]
        
        # Build the port key including index if present (output mappings use indexed keys)
        if signal.index and signal.index.start:
            idx = evaluate_expr(signal.index.start, {})
            port_key = f"{signal.name}[{idx}]"
        else:
            port_key = signal.name
        
        # For source, we need output port mapping
        if port_key in mapping.output_mappings:
            internal = mapping.output_mappings[port_key]
            if "." in internal:
                parts = internal.split(".", 1)
                return Signal(name=parts[1], instance=parts[0], index=None)
            else:
                return Signal(name=internal, instance=None, index=signal.index)
    
    # It's a reference to a primitive instance - apply prefix
    new_instance = f"{prefix}{signal.instance}" if prefix else signal.instance
    return Signal(name=signal.name, instance=new_instance, index=signal.index)


def rewire_signal_for_dest(signal: Signal, port_mappings: dict[str, PortMapping], 
                           prefix: str, component: Component) -> Optional[Signal]:
    """Rewire a destination signal reference, preserving indices."""
    
    if signal.instance is None:
        # It's a port reference of the current component - keep as is WITH its index
        return Signal(name=signal.name, instance=None, index=signal.index)
    
    # It's an instance.port reference
    if signal.instance in port_mappings:
        # This is a reference to a non-primitive instance that was flattened
        mapping = port_mappings[signal.instance]
        
        # Build the port key including index if present (input mappings use indexed keys)
        if signal.index and signal.index.start:
            idx = evaluate_expr(signal.index.start, {})
            port_key = f"{signal.name}[{idx}]"
        else:
            port_key = signal.name
        
        # For destination, we need input port mapping (but this is handled in rewire_connection)
        # If we get here, something is wrong
        if port_key in mapping.input_mappings:
            # Take the first one (this shouldn't really happen as fan-out is handled above)
            internal = mapping.input_mappings[port_key][0]
            if "." in internal:
                parts = internal.split(".", 1)
                return Signal(name=parts[1], instance=parts[0], index=None)
            else:
                return Signal(name=internal, instance=None, index=signal.index)
    
    # It's a reference to a primitive instance - apply prefix
    new_instance = f"{prefix}{signal.instance}" if prefix else signal.instance
    return Signal(name=signal.name, instance=new_instance, index=signal.index)


# =============================================================================
# Full Flattening Pipeline
# =============================================================================

def flatten_component_full(component: Component, library: ComponentLibrary, prefix: str = "") -> Component:
    """Apply all flattening phases to a component."""
    
    # Phase 2: Expand generators in instances
    expanded_instances = expand_generators_in_list(component.instances)
    
    # Phase 2: Expand generators in connections
    expanded_connections: list[Node] = []
    if component.connect_block:
        expanded_connections = expand_generators_in_list(component.connect_block.statements)
    
    # Phase 3: Expand expanders (slices) in connections
    expanded_connections = expand_expanders_in_connections(expanded_connections)
    
    # Create intermediate component
    intermediate = Component(
        name=component.name,
        inputs=component.inputs,
        outputs=component.outputs,
        instances=expanded_instances,
        connect_block=ConnectBlock(statements=expanded_connections) if expanded_connections else None,
        line=component.line,
        column=component.column
    )
    
    # Phase 4: Materialize constants
    intermediate = materialize_constants(intermediate)
    
    # Phase 5: Flatten hierarchy
    flattened = flatten_hierarchy(intermediate, library, prefix)
    
    return flattened


# =============================================================================
# Public API
# =============================================================================

@dataclass
class Flattener:
    """Main flattener class for transforming SHDL."""
    
    search_paths: list[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        self._library = ComponentLibrary(
            search_paths=[Path(p) for p in self.search_paths]
        )
    
    def add_component(self, component: Component) -> None:
        """Add a component to the library."""
        self._library.add(component)
    
    def load_file(self, path: str) -> Module:
        """Load and parse an SHDL file, adding its components to the library."""
        module = parse_file(path)
        
        # Process imports first - load all referenced modules
        for imp in module.imports:
            if not self._library.load_module(imp.module):
                raise FlattenerError(f"Cannot find module: {imp.module}")
        
        # Then add components from this file
        for comp in module.components:
            self._library.add(comp)
        
        return module
    
    def load_source(self, source: str) -> Module:
        """Load and parse SHDL source code, adding its components to the library."""
        module = parse(source)
        for comp in module.components:
            self._library.add(comp)
        return module
    
    def flatten(self, component_name: str) -> Component:
        """Flatten a component by name."""
        component = self._library.resolve(component_name)
        return flatten_component_full(component, self._library)
    
    def flatten_to_base_shdl(self, component_name: str) -> str:
        """Flatten a component and return Base SHDL source code."""
        flattened = self.flatten(component_name)
        return format_base_shdl(flattened)


def format_base_shdl(component: Component) -> str:
    """Format a flattened component as Base SHDL source code."""
    lines: list[str] = []
    
    # Component header
    inputs = ", ".join(format_port(p) for p in component.inputs)
    outputs = ", ".join(format_port(p) for p in component.outputs)
    lines.append(f"component {component.name}({inputs}) -> ({outputs}) {{")
    
    # Instances
    for node in component.instances:
        if isinstance(node, Instance):
            lines.append(f"    {node.name}: {node.component_type};")
    
    # Connect block
    if component.connect_block and component.connect_block.statements:
        lines.append("")
        lines.append("    connect {")
        for node in component.connect_block.statements:
            if isinstance(node, Connection):
                src = format_signal(node.source)
                dst = format_signal(node.destination)
                lines.append(f"        {src} -> {dst};")
        lines.append("    }")
    
    lines.append("}")
    
    return "\n".join(lines)


def format_port(port: Port) -> str:
    """Format a port declaration."""
    if port.width:
        return f"{port.name}[{port.width}]"
    return port.name


def format_signal(signal: Signal) -> str:
    """Format a signal reference."""
    result = ""
    if signal.instance:
        result = f"{signal.instance}."
    result += signal.name
    
    if signal.index and signal.index.start:
        if isinstance(signal.index.start, NumberLiteral):
            result += f"[{signal.index.start.value}]"
    
    return result


def flatten_file(path: str, search_paths: list[str] = None) -> str:
    """
    Convenience function to flatten the main component in an SHDL file.
    
    Returns Base SHDL source code.
    """
    flattener = Flattener(search_paths=search_paths or [])
    
    # Add the file's directory to search paths
    file_path = Path(path)
    if file_path.parent not in [Path(p) for p in flattener.search_paths]:
        flattener._library.search_paths.insert(0, file_path.parent)
    
    module = flattener.load_file(path)
    
    if not module.components:
        raise FlattenerError("No components found in file")
    
    # Flatten the last component (typically the main one)
    main_component = module.components[-1]
    return flattener.flatten_to_base_shdl(main_component.name)
