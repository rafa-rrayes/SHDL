"""
Symbol Table Management

Provides symbol resolution for signals, gates, and hierarchy navigation.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Union

from .debuginfo import DebugInfo, GateInfo, PortInfo


class SignalType(Enum):
    """Type of signal reference."""
    INPUT_PORT = auto()       # Component input port
    OUTPUT_PORT = auto()      # Component output port
    GATE_OUTPUT = auto()      # Primitive gate output
    GATE_INPUT = auto()       # Primitive gate input (A or B)
    INSTANCE_PORT = auto()    # Hierarchical instance port
    CONSTANT_BIT = auto()     # Materialized constant bit
    UNKNOWN = auto()


@dataclass
class SignalRef:
    """
    A resolved signal reference.
    
    Can represent:
    - Component ports: A, Sum, A[4], Sum[1:8]
    - Gate ports: fa1_x1.O, fa1_x1.A
    - Hierarchical refs: fa1.x1.O, fa1.Sum
    """
    name: str                         # Base name
    signal_type: SignalType
    bit_index: Optional[int] = None   # Single bit index (1-based)
    bit_start: Optional[int] = None   # Range start (1-based)  
    bit_end: Optional[int] = None     # Range end (1-based, inclusive)
    width: int = 1                    # Signal width
    
    # For gate references
    gate_name: Optional[str] = None   # Flattened gate name
    gate_port: Optional[str] = None   # A, B, or O
    
    # For hierarchical references
    instance_path: Optional[str] = None  # e.g., "fa1/x1"
    
    @property
    def is_single_bit(self) -> bool:
        """Check if this references a single bit."""
        return self.bit_index is not None or self.width == 1
    
    @property
    def is_range(self) -> bool:
        """Check if this references a bit range."""
        return self.bit_start is not None and self.bit_end is not None
    
    @property
    def is_gate(self) -> bool:
        """Check if this references a gate."""
        return self.signal_type in (SignalType.GATE_OUTPUT, SignalType.GATE_INPUT)
    
    @property
    def is_port(self) -> bool:
        """Check if this references a component port."""
        return self.signal_type in (SignalType.INPUT_PORT, SignalType.OUTPUT_PORT)
    
    def __str__(self) -> str:
        result = self.name
        if self.instance_path:
            result = f"{self.instance_path}/{result}"
        if self.gate_port:
            result = f"{result}.{self.gate_port}"
        if self.bit_index is not None:
            result = f"{result}[{self.bit_index}]"
        elif self.is_range:
            result = f"{result}[{self.bit_start}:{self.bit_end}]"
        return result


class SymbolTable:
    """
    Symbol table for resolving signal references.
    
    Provides:
    - Name resolution (signal names -> SignalRef)
    - Scope management (current hierarchy position)
    - Wildcard pattern matching
    - Tab completion candidates
    """
    
    def __init__(self, debug_info: DebugInfo):
        self.debug_info = debug_info
        self._current_scope: list[str] = []  # Stack of instance names
        
        # Build lookup tables
        self._input_names: set[str] = {p.name for p in debug_info.inputs}
        self._output_names: set[str] = {p.name for p in debug_info.outputs}
        self._gate_names: set[str] = set(debug_info.gates.keys())
        self._constant_names: set[str] = set(debug_info.constants.keys())
    
    @property
    def current_scope(self) -> str:
        """Get current scope as a path string."""
        if not self._current_scope:
            return self.debug_info.component
        return "/".join([self.debug_info.component] + self._current_scope)
    
    @property
    def scope_prefix(self) -> str:
        """Get the flattened prefix for current scope."""
        if not self._current_scope:
            return ""
        return "_".join(self._current_scope) + "_"
    
    def enter_scope(self, instance: str) -> bool:
        """
        Enter an instance scope.
        
        Args:
            instance: Instance name to enter (relative to current scope)
        
        Returns:
            True if successful, False if instance not found
        """
        # Check if this instance exists
        test_prefix = self.scope_prefix + instance + "_"
        has_children = any(
            name.startswith(test_prefix) for name in self._gate_names
        )
        
        if has_children or instance in self._get_current_instances():
            self._current_scope.append(instance)
            return True
        return False
    
    def exit_scope(self) -> bool:
        """
        Exit the current scope (go up one level).
        
        Returns:
            True if successful, False if already at root
        """
        if self._current_scope:
            self._current_scope.pop()
            return True
        return False
    
    def reset_scope(self) -> None:
        """Reset to root scope."""
        self._current_scope.clear()
    
    def set_scope(self, path: str) -> bool:
        """
        Set scope to a specific path.
        
        Args:
            path: Path like "fa1/x1" or "/" for root
        
        Returns:
            True if successful
        """
        if path == "/" or path == "":
            self.reset_scope()
            return True
        
        # Try to navigate to the path
        self.reset_scope()
        parts = path.strip("/").split("/")
        
        # Skip component name if present
        if parts and parts[0] == self.debug_info.component:
            parts = parts[1:]
        
        for part in parts:
            if not self.enter_scope(part):
                self.reset_scope()
                return False
        return True
    
    def resolve(self, name: str) -> Optional[SignalRef]:
        """
        Resolve a signal name to a SignalRef.
        
        Supports various formats:
        - "A" - input/output port
        - "A[4]" - bit index
        - "A[1:8]" - bit range
        - "fa1_x1" or "fa1_x1.O" - gate reference
        - "fa1.x1.O" - hierarchical reference
        - "x1.O" - relative to current scope
        
        Returns:
            SignalRef if resolved, None if not found
        """
        # Parse the name
        base_name, bit_index, bit_start, bit_end = self._parse_signal_name(name)
        
        # Check for gate port access (name.port)
        gate_port = None
        if "." in base_name:
            parts = base_name.rsplit(".", 1)
            if parts[1] in ("A", "B", "O"):
                base_name = parts[0]
                gate_port = parts[1]
        
        # Try to resolve in order of priority
        
        # 1. Check input ports
        if base_name in self._input_names:
            port = self.debug_info.get_input(base_name)
            return SignalRef(
                name=base_name,
                signal_type=SignalType.INPUT_PORT,
                bit_index=bit_index,
                bit_start=bit_start,
                bit_end=bit_end,
                width=port.width if port else 1,
            )
        
        # 2. Check output ports
        if base_name in self._output_names:
            port = self.debug_info.get_output(base_name)
            return SignalRef(
                name=base_name,
                signal_type=SignalType.OUTPUT_PORT,
                bit_index=bit_index,
                bit_start=bit_start,
                bit_end=bit_end,
                width=port.width if port else 1,
            )
        
        # 3. Check gate names (with scope prefix)
        gate_name = self._resolve_gate_name(base_name)
        if gate_name:
            gate = self.debug_info.get_gate(gate_name)
            signal_type = SignalType.GATE_OUTPUT
            if gate_port in ("A", "B"):
                signal_type = SignalType.GATE_INPUT
            return SignalRef(
                name=base_name,
                signal_type=signal_type,
                gate_name=gate_name,
                gate_port=gate_port or "O",
                width=1,
            )
        
        # 4. Check hierarchical path (fa1.x1.O style)
        if "." in name or "/" in name:
            resolved = self._resolve_hierarchical(name)
            if resolved:
                return resolved
        
        # 5. Check constants
        const_name = base_name.split("_bit")[0] if "_bit" in base_name else base_name
        if const_name in self._constant_names:
            return SignalRef(
                name=base_name,
                signal_type=SignalType.CONSTANT_BIT,
                bit_index=bit_index,
                width=self.debug_info.constants[const_name].width,
            )
        
        return None
    
    def _parse_signal_name(self, name: str) -> tuple[str, Optional[int], Optional[int], Optional[int]]:
        """
        Parse a signal name with optional bit index/range.
        
        Returns:
            (base_name, bit_index, bit_start, bit_end)
        """
        bit_index = None
        bit_start = None
        bit_end = None
        
        if "[" in name and name.endswith("]"):
            bracket_pos = name.index("[")
            base_name = name[:bracket_pos]
            index_str = name[bracket_pos + 1:-1]
            
            if ":" in index_str:
                # Range
                parts = index_str.split(":")
                if parts[0]:
                    bit_start = int(parts[0])
                if parts[1]:
                    bit_end = int(parts[1])
            else:
                # Single index
                bit_index = int(index_str)
        else:
            base_name = name
        
        return base_name, bit_index, bit_start, bit_end
    
    def _resolve_gate_name(self, name: str) -> Optional[str]:
        """
        Resolve a gate name, considering current scope.
        
        Tries:
        1. Exact match
        2. With scope prefix
        3. Hierarchical path converted to flattened name
        """
        # Replace . and / with _ for flattened name
        flattened = name.replace(".", "_").replace("/", "_")
        
        # Try exact match
        if flattened in self._gate_names:
            return flattened
        
        # Try with scope prefix
        prefixed = self.scope_prefix + flattened
        if prefixed in self._gate_names:
            return prefixed
        
        return None
    
    def _resolve_hierarchical(self, name: str) -> Optional[SignalRef]:
        """Resolve a hierarchical path like fa1.x1.O or fa1/x1/O."""
        # Normalize separators
        normalized = name.replace("/", ".")
        parts = normalized.split(".")
        
        # Last part might be a port
        port = None
        if parts[-1] in ("A", "B", "O"):
            port = parts[-1]
            parts = parts[:-1]
        
        # Convert to flattened name
        flattened = "_".join(parts)
        
        # Try with scope prefix
        gate_name = self._resolve_gate_name(flattened)
        if gate_name:
            return SignalRef(
                name=flattened,
                signal_type=SignalType.GATE_OUTPUT if port == "O" or port is None else SignalType.GATE_INPUT,
                gate_name=gate_name,
                gate_port=port or "O",
                instance_path="/".join(parts[:-1]) if len(parts) > 1 else None,
                width=1,
            )
        
        return None
    
    def _get_current_instances(self) -> set[str]:
        """Get instance names visible at current scope."""
        instances: set[str] = set()
        prefix = self.scope_prefix
        
        for gate_name in self._gate_names:
            if gate_name.startswith(prefix):
                # Extract the next component of the path
                suffix = gate_name[len(prefix):]
                if "_" in suffix:
                    instance = suffix.split("_")[0]
                    instances.add(instance)
        
        return instances
    
    def get_completions(self, prefix: str) -> list[str]:
        """
        Get tab completion candidates for a prefix.
        
        Returns:
            List of matching signal/gate names
        """
        candidates: list[str] = []
        
        # Input/output ports
        for name in self._input_names | self._output_names:
            if name.startswith(prefix):
                candidates.append(name)
        
        # Gates in current scope
        scope_prefix = self.scope_prefix
        for gate_name in self._gate_names:
            if gate_name.startswith(scope_prefix):
                relative = gate_name[len(scope_prefix):]
                if relative.startswith(prefix):
                    candidates.append(relative)
        
        # Also match full gate names
        for gate_name in self._gate_names:
            if gate_name.startswith(prefix):
                candidates.append(gate_name)
        
        return sorted(set(candidates))
    
    def get_all_signals(self) -> list[str]:
        """Get all signal names (inputs, outputs, gates)."""
        signals: list[str] = []
        signals.extend(self._input_names)
        signals.extend(self._output_names)
        signals.extend(self._gate_names)
        return sorted(signals)
    
    def get_hierarchy_tree(self) -> dict:
        """
        Build a hierarchy tree from gate names.
        
        Returns a nested dict representing the instance hierarchy.
        """
        tree: dict = {}
        
        for gate_name, gate_info in self.debug_info.gates.items():
            parts = gate_name.split("_")
            current = tree
            
            # Navigate/create path
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {"__gates__": [], "__children__": {}}
                current = current[part]["__children__"]
            
            # Add gate to leaf
            leaf_name = parts[-1] if len(parts) > 1 else gate_name
            parent_path = "_".join(parts[:-1]) if len(parts) > 1 else ""
            
            if parent_path:
                parent = tree
                for part in parts[:-1]:
                    if part in parent:
                        parent = parent[part]["__children__"]
                if "__gates__" not in tree.get(parts[0], {}):
                    tree[parts[0]] = {"__gates__": [], "__children__": {}}
                # Navigate to correct parent
                current = tree
                for part in parts[:-1]:
                    current = current[part]["__children__"]
                if "__gates__" not in current.get(parts[-2] if len(parts) > 1 else parts[0], {}):
                    pass  # Gate is at this level
        
        return tree
