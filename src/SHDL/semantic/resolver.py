"""
SHDL Symbol Resolution

Handles name resolution for components, signals, and instances.
Provides "did you mean?" suggestions for typos.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set
from pathlib import Path

from ..flattener.ast import (
    Module, Component, Port, Instance, Constant, Connection,
    Signal, Generator, Import, ConnectBlock, Node
)
from ..source_map import SourceSpan
from ..errors import (
    ErrorCode, Diagnostic, DiagnosticCollection, 
    Annotation, Suggestion, RelatedInfo,
    find_similar
)


# Primitive gates built into SHDL
PRIMITIVE_GATES = {"AND", "OR", "NOT", "XOR", "__VCC__", "__GND__"}


@dataclass
class ComponentInfo:
    """Information about a component type."""
    name: str
    inputs: List[Port]
    outputs: List[Port]
    span: SourceSpan
    is_primitive: bool = False
    source_file: str = "<builtin>"
    
    @classmethod
    def from_primitive(cls, name: str) -> "ComponentInfo":
        """Create ComponentInfo for a primitive gate."""
        if name == "NOT":
            inputs = [Port(name="A", width=None)]
            outputs = [Port(name="O", width=None)]
        elif name in ("__VCC__", "__GND__"):
            inputs = []
            outputs = [Port(name="O", width=None)]
        else:  # AND, OR, XOR
            inputs = [Port(name="A", width=None), Port(name="B", width=None)]
            outputs = [Port(name="O", width=None)]
        
        return cls(
            name=name,
            inputs=inputs,
            outputs=outputs,
            span=SourceSpan(file_path="<builtin>"),
            is_primitive=True,
            source_file="<builtin>"
        )
    
    @classmethod
    def from_component(cls, comp: Component) -> "ComponentInfo":
        """Create ComponentInfo from an AST Component."""
        return cls(
            name=comp.name,
            inputs=comp.inputs,
            outputs=comp.outputs,
            span=comp.span,
            is_primitive=False,
            source_file=comp.file_path
        )
    
    def get_port(self, name: str) -> Optional[Port]:
        """Get a port by name."""
        for p in self.inputs + self.outputs:
            if p.name == name:
                return p
        return None
    
    def is_input_port(self, name: str) -> bool:
        """Check if a port name is an input port."""
        return any(p.name == name for p in self.inputs)
    
    def is_output_port(self, name: str) -> bool:
        """Check if a port name is an output port."""
        return any(p.name == name for p in self.outputs)


@dataclass
class InstanceInfo:
    """Information about an instance."""
    name: str
    component_type: str
    component: Optional[ComponentInfo]
    span: SourceSpan
    
    def get_port(self, name: str) -> Optional[Port]:
        """Get a port from the instance's component."""
        if self.component:
            return self.component.get_port(name)
        return None


@dataclass
class SignalInfo:
    """Information about a signal (port or internal wire)."""
    name: str
    width: Optional[int]  # None = 1 bit
    is_input: bool
    is_output: bool
    span: SourceSpan
    
    @property
    def bit_count(self) -> int:
        return self.width if self.width is not None else 1


@dataclass
class ConstantInfo:
    """Information about a constant."""
    name: str
    value: int
    width: Optional[int]
    span: SourceSpan


@dataclass
class SymbolTable:
    """
    Symbol table for a single component scope.
    
    Tracks all defined signals, instances, constants, and their properties.
    """
    component_name: str
    
    # Defined symbols
    signals: Dict[str, SignalInfo] = field(default_factory=dict)
    instances: Dict[str, InstanceInfo] = field(default_factory=dict)
    constants: Dict[str, ConstantInfo] = field(default_factory=dict)
    
    # Port names for quick lookup
    input_ports: Set[str] = field(default_factory=set)
    output_ports: Set[str] = field(default_factory=set)
    
    def add_port(self, port: Port, is_input: bool) -> None:
        """Add a port to the symbol table."""
        info = SignalInfo(
            name=port.name,
            width=port.width,
            is_input=is_input,
            is_output=not is_input,
            span=port.span
        )
        self.signals[port.name] = info
        if is_input:
            self.input_ports.add(port.name)
        else:
            self.output_ports.add(port.name)
    
    def add_instance(
        self,
        instance: Instance,
        component: Optional[ComponentInfo]
    ) -> None:
        """Add an instance to the symbol table."""
        info = InstanceInfo(
            name=instance.name,
            component_type=instance.component_type,
            component=component,
            span=instance.span
        )
        self.instances[instance.name] = info
    
    def add_constant(self, const: Constant) -> None:
        """Add a constant to the symbol table."""
        info = ConstantInfo(
            name=const.name,
            value=const.value,
            width=const.width,
            span=const.span
        )
        self.constants[const.name] = info
    
    def lookup_signal(self, name: str) -> Optional[SignalInfo]:
        """Look up a signal by name."""
        return self.signals.get(name)
    
    def lookup_instance(self, name: str) -> Optional[InstanceInfo]:
        """Look up an instance by name."""
        return self.instances.get(name)
    
    def lookup_constant(self, name: str) -> Optional[ConstantInfo]:
        """Look up a constant by name."""
        return self.constants.get(name)
    
    def all_signal_names(self) -> List[str]:
        """Get all signal names."""
        return list(self.signals.keys())
    
    def all_instance_names(self) -> List[str]:
        """Get all instance names."""
        return list(self.instances.keys())


class ComponentResolver:
    """
    Resolves component references and handles imports.
    
    Maintains a library of known components from imports and 
    the current module.
    """
    
    def __init__(
        self,
        diagnostics: DiagnosticCollection,
        search_paths: List[str] = None
    ):
        self.diagnostics = diagnostics
        self.search_paths = search_paths or ["."]
        
        # Known components: name -> ComponentInfo
        self._components: Dict[str, ComponentInfo] = {}
        
        # Track imports for circular import detection
        self._import_stack: List[str] = []
        self._imported_files: Set[str] = set()
        
        # Add primitive gates
        for name in PRIMITIVE_GATES:
            self._components[name] = ComponentInfo.from_primitive(name)
    
    def register_component(self, comp: Component) -> None:
        """Register a component from the AST."""
        if comp.name in self._components:
            existing = self._components[comp.name]
            if not existing.is_primitive:
                self.diagnostics.error(
                    code=ErrorCode.E0307,
                    message=f"Duplicate component name '{comp.name}'",
                    span=comp.span,
                    related=[RelatedInfo(
                        span=existing.span,
                        message="first defined here"
                    )]
                )
                return
        
        self._components[comp.name] = ComponentInfo.from_component(comp)
    
    def resolve(self, name: str, span: SourceSpan) -> Optional[ComponentInfo]:
        """
        Resolve a component type name.
        
        Returns ComponentInfo if found, or None if not found.
        Reports an error with suggestions if not found.
        """
        if name in self._components:
            return self._components[name]
        
        # Component not found - suggest similar names
        available = list(self._components.keys())
        similar = find_similar(name, available, max_distance=2)
        
        suggestions = []
        notes = [f"available components: {', '.join(sorted(available)[:10])}"]
        
        if similar:
            suggestions.append(Suggestion(
                message=f"did you mean '{similar[0]}'?"
            ))
        
        # Maybe they need an import?
        suggestions.append(Suggestion(
            message="did you mean to import it?"
        ))
        
        self.diagnostics.error(
            code=ErrorCode.E0301,
            message=f"Unknown component type '{name}'",
            span=span,
            annotations=[Annotation(span=span, label="component not found")],
            suggestions=suggestions,
            notes=notes
        )
        
        return None
    
    def process_import(self, imp: Import) -> None:
        """
        Process an import statement.
        
        Loads the module file and extracts the requested components.
        """
        # Find the module file
        module_path = self._find_module(imp.module)
        
        if module_path is None:
            self.diagnostics.error(
                code=ErrorCode.E0701,
                message=f"Module not found: '{imp.module}'",
                span=imp.span,
                notes=[f"searched in: {', '.join(self.search_paths)}"]
            )
            return
        
        # Check for circular imports
        if module_path in self._import_stack:
            cycle = " -> ".join(self._import_stack + [module_path])
            self.diagnostics.error(
                code=ErrorCode.E0703,
                message=f"Circular import detected: {cycle}",
                span=imp.span
            )
            return
        
        # Load the module (avoid re-loading)
        if module_path not in self._imported_files:
            self._import_stack.append(module_path)
            try:
                self._load_module(module_path, imp)
            finally:
                self._import_stack.pop()
            self._imported_files.add(module_path)
        
        # Check that requested components exist
        for comp_name in imp.components:
            if comp_name not in self._components:
                self.diagnostics.error(
                    code=ErrorCode.E0702,
                    message=f"Component '{comp_name}' not found in module '{imp.module}'",
                    span=imp.span
                )
    
    def _find_module(self, module_name: str) -> Optional[str]:
        """Find a module file in the search paths."""
        filename = f"{module_name}.shdl"
        
        for search_path in self.search_paths:
            path = Path(search_path) / filename
            if path.exists():
                return str(path.resolve())
        
        return None
    
    def _load_module(self, path: str, imp: Import) -> None:
        """Load components from a module file."""
        from ..flattener.parser import parse_file
        
        try:
            module = parse_file(path)
            
            # Only register the components that were imported
            for comp in module.components:
                if comp.name in imp.components:
                    self.register_component(comp)
                    
        except Exception as e:
            self.diagnostics.error(
                code=ErrorCode.E0704,
                message=f"Error loading module '{imp.module}': {e}",
                span=imp.span
            )
    
    @property
    def available_components(self) -> List[str]:
        """Get list of all available component names."""
        return list(self._components.keys())
    
    def get_component(self, name: str) -> Optional[ComponentInfo]:
        """Get component info without reporting errors."""
        return self._components.get(name)


def build_symbol_table(
    component: Component,
    resolver: ComponentResolver,
    diagnostics: DiagnosticCollection
) -> SymbolTable:
    """
    Build a symbol table for a component.
    
    Registers all ports, instances, and constants.
    Reports errors for duplicates and unresolved references.
    """
    table = SymbolTable(component_name=component.name)
    
    # Add input ports
    for port in component.inputs:
        if port.name in table.signals:
            diagnostics.error(
                code=ErrorCode.E0305,
                message=f"Duplicate port name '{port.name}'",
                span=port.span,
                related=[RelatedInfo(
                    span=table.signals[port.name].span,
                    message="first defined here"
                )]
            )
        else:
            table.add_port(port, is_input=True)
    
    # Add output ports
    for port in component.outputs:
        if port.name in table.signals:
            diagnostics.error(
                code=ErrorCode.E0305,
                message=f"Duplicate port name '{port.name}'",
                span=port.span,
                related=[RelatedInfo(
                    span=table.signals[port.name].span,
                    message="first defined here"
                )]
            )
        else:
            table.add_port(port, is_input=False)
    
    # Process instances and constants (including from generators)
    _process_declarations(component.instances, table, resolver, diagnostics, {})
    
    return table


def _process_declarations(
    nodes: List[Node],
    table: SymbolTable,
    resolver: ComponentResolver,
    diagnostics: DiagnosticCollection,
    gen_vars: Dict[str, int]
) -> None:
    """Process declarations recursively (handling generators)."""
    for node in nodes:
        if isinstance(node, Instance):
            _process_instance(node, table, resolver, diagnostics, gen_vars)
        elif isinstance(node, Constant):
            _process_constant(node, table, diagnostics, gen_vars)
        elif isinstance(node, Generator):
            # Validate generator range
            from ..flattener.flattener import expand_range
            try:
                values = expand_range(node.range_spec)
                if not values:
                    diagnostics.error(
                        code=ErrorCode.E0605,
                        message=f"Empty generator range",
                        span=node.span
                    )
                    continue
                
                # Check for shadowing
                if node.variable in gen_vars:
                    diagnostics.error(
                        code=ErrorCode.E0606,
                        message=f"Generator variable '{node.variable}' shadows outer variable",
                        span=node.span
                    )
                
                # Process body for each value
                for val in values:
                    new_vars = dict(gen_vars)
                    new_vars[node.variable] = val
                    _process_declarations(node.body, table, resolver, diagnostics, new_vars)
                    
            except Exception as e:
                diagnostics.error(
                    code=ErrorCode.E0601,
                    message=f"Invalid generator range: {e}",
                    span=node.span
                )


def _process_instance(
    inst: Instance,
    table: SymbolTable,
    resolver: ComponentResolver,
    diagnostics: DiagnosticCollection,
    gen_vars: Dict[str, int]
) -> None:
    """Process a single instance declaration."""
    # Substitute generator variables in name
    from ..flattener.flattener import substitute_name
    name = substitute_name(inst.name, gen_vars)
    
    # Check for duplicate
    if name in table.instances:
        diagnostics.error(
            code=ErrorCode.E0305,
            message=f"Duplicate instance name '{name}'",
            span=inst.span,
            related=[RelatedInfo(
                span=table.instances[name].span,
                message="first defined here"
            )]
        )
        return
    
    # Check for shadowing a port
    if name in table.signals:
        diagnostics.error(
            code=ErrorCode.E0310,
            message=f"Instance name '{name}' shadows port",
            span=inst.span,
            related=[RelatedInfo(
                span=table.signals[name].span,
                message="port defined here"
            )]
        )
    
    # Resolve component type
    comp_info = resolver.resolve(inst.component_type, inst.span)
    
    # Create modified instance with resolved name
    resolved_inst = Instance(
        name=name,
        component_type=inst.component_type,
        line=inst.line,
        column=inst.column,
        end_line=inst.end_line,
        end_column=inst.end_column,
        file_path=inst.file_path
    )
    
    table.add_instance(resolved_inst, comp_info)


def _process_constant(
    const: Constant,
    table: SymbolTable,
    diagnostics: DiagnosticCollection,
    gen_vars: Dict[str, int]
) -> None:
    """Process a single constant declaration."""
    from ..flattener.flattener import substitute_name
    name = substitute_name(const.name, gen_vars)
    
    # Check for duplicate
    if name in table.constants:
        diagnostics.error(
            code=ErrorCode.E0306,
            message=f"Duplicate constant name '{name}'",
            span=const.span,
            related=[RelatedInfo(
                span=table.constants[name].span,
                message="first defined here"
            )]
        )
        return
    
    # Check for shadowing a signal
    if name in table.signals:
        diagnostics.error(
            code=ErrorCode.E0309,
            message=f"Constant name '{name}' shadows port",
            span=const.span,
            related=[RelatedInfo(
                span=table.signals[name].span,
                message="port defined here"
            )]
        )
    
    # Validate constant value
    if const.value < 0:
        diagnostics.error(
            code=ErrorCode.E0803,
            message=f"Negative constant value: {const.value}",
            span=const.span
        )
        return
    
    if const.width is not None:
        max_val = (1 << const.width) - 1
        if const.value > max_val:
            diagnostics.error(
                code=ErrorCode.E0801,
                message=f"Constant value {const.value} overflows {const.width}-bit width (max {max_val})",
                span=const.span
            )
    
    # Create modified constant with resolved name
    resolved_const = Constant(
        name=name,
        value=const.value,
        width=const.width,
        line=const.line,
        column=const.column,
        end_line=const.end_line,
        end_column=const.end_column,
        file_path=const.file_path
    )
    
    table.add_constant(resolved_const)
