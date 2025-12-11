"""
SHDL Type Checking

Handles width validation and type compatibility checking for signals and connections.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

from ..flattener.ast import (
    Component, Port, Connection, Signal, IndexExpr,
    ArithmeticExpr, NumberLiteral, VariableRef, BinaryOp,
    Generator, ConnectBlock, Node
)
from ..source_map import SourceSpan
from ..errors import (
    ErrorCode, Diagnostic, DiagnosticCollection,
    Annotation, Suggestion, RelatedInfo
)
from .resolver import SymbolTable, ComponentInfo, InstanceInfo, SignalInfo


@dataclass
class WidthInfo:
    """Information about the width of a signal reference."""
    width: int  # Number of bits
    is_single_bit: bool  # True if accessing a single bit via subscript
    span: SourceSpan
    
    @classmethod
    def single_bit(cls, span: SourceSpan) -> "WidthInfo":
        return cls(width=1, is_single_bit=True, span=span)
    
    @classmethod
    def multi_bit(cls, width: int, span: SourceSpan) -> "WidthInfo":
        return cls(width=width, is_single_bit=False, span=span)


class TypeChecker:
    """
    Performs type/width checking on SHDL components.
    
    Validates:
    - Signal widths match in connections
    - Subscript indices are within range
    - Slice ranges are valid
    - Port references are valid
    """
    
    def __init__(
        self,
        diagnostics: DiagnosticCollection,
        symbol_table: SymbolTable
    ):
        self.diagnostics = diagnostics
        self.table = symbol_table
    
    def check_component(self, component: Component) -> None:
        """Check all connections in a component."""
        if component.connect_block:
            self._check_connect_block(component.connect_block, {})
    
    def _check_connect_block(
        self,
        block: ConnectBlock,
        gen_vars: Dict[str, int]
    ) -> None:
        """Check all connections in a connect block."""
        for node in block.statements:
            if isinstance(node, Connection):
                self._check_connection(node, gen_vars)
            elif isinstance(node, Generator):
                self._check_generator_connections(node, gen_vars)
    
    def _check_generator_connections(
        self,
        gen: Generator,
        outer_vars: Dict[str, int]
    ) -> None:
        """Check connections inside a generator."""
        from ..flattener.flattener import expand_range
        
        try:
            values = expand_range(gen.range_spec)
        except Exception:
            # Generator error already reported by resolver
            return
        
        for val in values:
            new_vars = dict(outer_vars)
            new_vars[gen.variable] = val
            
            for node in gen.body:
                if isinstance(node, Connection):
                    self._check_connection(node, new_vars)
                elif isinstance(node, Generator):
                    self._check_generator_connections(node, new_vars)
    
    def _check_connection(
        self,
        conn: Connection,
        gen_vars: Dict[str, int]
    ) -> None:
        """Check a single connection."""
        src_width = self._get_signal_width(conn.source, gen_vars)
        dst_width = self._get_signal_width(conn.destination, gen_vars)
        
        if src_width is None or dst_width is None:
            # Error already reported
            return
        
        if src_width.width != dst_width.width:
            self.diagnostics.error(
                code=ErrorCode.E0401,
                message=f"Port width mismatch in connection: {src_width.width} bits vs {dst_width.width} bits",
                span=conn.span,
                annotations=[
                    Annotation(
                        span=src_width.span,
                        label=f"this is {src_width.width} bit(s) wide"
                    )
                ],
                related=[
                    RelatedInfo(
                        span=dst_width.span,
                        message=f"target is {dst_width.width} bit(s) wide"
                    )
                ],
                suggestions=[
                    Suggestion(
                        message="use bit subscript to match widths"
                    )
                ]
            )
    
    def _get_signal_width(
        self,
        signal: Signal,
        gen_vars: Dict[str, int]
    ) -> Optional[WidthInfo]:
        """
        Determine the width of a signal reference.
        
        Returns None if the signal is invalid (error already reported).
        """
        from ..flattener.flattener import substitute_name, evaluate_expr
        
        # Resolve template names
        name = substitute_name(signal.name, gen_vars)
        instance = substitute_name(signal.instance, gen_vars) if signal.instance else None
        
        if instance:
            # Instance port reference: inst.Port
            inst_info = self.table.lookup_instance(instance)
            if inst_info is None:
                self.diagnostics.error(
                    code=ErrorCode.E0303,
                    message=f"Undefined instance '{instance}'",
                    span=signal.span,
                    suggestions=self._suggest_instance(instance)
                )
                return None
            
            if inst_info.component is None:
                # Component not resolved, error already reported
                return None
            
            port = inst_info.component.get_port(name)
            if port is None:
                available_ports = [p.name for p in inst_info.component.inputs + inst_info.component.outputs]
                self.diagnostics.error(
                    code=ErrorCode.E0304,
                    message=f"Unknown port '{name}' on component '{inst_info.component_type}'",
                    span=signal.span,
                    notes=[f"available ports: {', '.join(available_ports)}"]
                )
                return None
            
            base_width = port.width if port.width else 1
            
        else:
            # Component port or constant reference
            sig_info = self.table.lookup_signal(name)
            const_info = self.table.lookup_constant(name)
            
            if sig_info:
                base_width = sig_info.bit_count
            elif const_info:
                # Constants are treated as their declared or inferred width
                if const_info.width:
                    base_width = const_info.width
                else:
                    base_width = max(1, const_info.value.bit_length())
            else:
                self.diagnostics.error(
                    code=ErrorCode.E0302,
                    message=f"Undefined signal '{name}'",
                    span=signal.span,
                    suggestions=self._suggest_signal(name)
                )
                return None
        
        # Handle indexing/slicing
        if signal.index:
            return self._apply_index(signal.index, base_width, signal.span, gen_vars)
        
        return WidthInfo.multi_bit(base_width, signal.span)
    
    def _apply_index(
        self,
        index: IndexExpr,
        base_width: int,
        span: SourceSpan,
        gen_vars: Dict[str, int]
    ) -> Optional[WidthInfo]:
        """Apply an index or slice to a base width."""
        from ..flattener.flattener import evaluate_expr
        
        if index.is_slice:
            # Slice: [start:end]
            start = 1
            end = base_width
            
            if index.start is not None:
                try:
                    start = evaluate_expr(index.start, gen_vars)
                except Exception as e:
                    self.diagnostics.error(
                        code=ErrorCode.E0603,
                        message=f"Invalid slice start expression: {e}",
                        span=span
                    )
                    return None
            
            if index.end is not None:
                try:
                    end = evaluate_expr(index.end, gen_vars)
                except Exception as e:
                    self.diagnostics.error(
                        code=ErrorCode.E0603,
                        message=f"Invalid slice end expression: {e}",
                        span=span
                    )
                    return None
            
            # Validate range
            if start < 1 or end > base_width:
                self.diagnostics.error(
                    code=ErrorCode.E0403,
                    message=f"Slice range [{start}:{end}] out of bounds for {base_width}-bit signal",
                    span=span
                )
                return None
            
            if start > end:
                self.diagnostics.error(
                    code=ErrorCode.E0406,
                    message=f"Invalid slice range: start ({start}) > end ({end})",
                    span=span
                )
                return None
            
            slice_width = end - start + 1
            return WidthInfo.multi_bit(slice_width, span)
        
        else:
            # Single index: [n]
            if index.start is None:
                self.diagnostics.error(
                    code=ErrorCode.E0402,
                    message="Missing index value",
                    span=span
                )
                return None
            
            try:
                idx = evaluate_expr(index.start, gen_vars)
            except Exception as e:
                self.diagnostics.error(
                    code=ErrorCode.E0603,
                    message=f"Invalid index expression: {e}",
                    span=span
                )
                return None
            
            # Validate index
            if idx < 1 or idx > base_width:
                self.diagnostics.error(
                    code=ErrorCode.E0403,
                    message=f"Index {idx} out of bounds for {base_width}-bit signal (valid: 1-{base_width})",
                    span=span
                )
                return None
            
            if base_width == 1 and idx == 1:
                # Subscripting a single-bit signal is technically allowed
                pass
            
            return WidthInfo.single_bit(span)
    
    def _suggest_instance(self, name: str) -> List[Suggestion]:
        """Suggest similar instance names."""
        from ..errors import find_similar
        similar = find_similar(name, self.table.all_instance_names())
        if similar:
            return [Suggestion(message=f"did you mean '{similar[0]}'?")]
        return []
    
    def _suggest_signal(self, name: str) -> List[Suggestion]:
        """Suggest similar signal names."""
        from ..errors import find_similar
        similar = find_similar(name, self.table.all_signal_names())
        if similar:
            return [Suggestion(message=f"did you mean '{similar[0]}'?")]
        return []
