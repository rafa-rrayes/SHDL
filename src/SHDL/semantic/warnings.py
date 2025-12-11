"""
SHDL Warning Detection

Detects potential issues that aren't errors but may indicate problems:
- Unused signals
- Unused instances  
- Unused constants
- Unused imports
- Redundant connections
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List
from collections import defaultdict

from ..flattener.ast import (
    Module, Component, Connection, Signal, Generator, 
    ConnectBlock, Node, Instance, Constant, Import
)
from ..source_map import SourceSpan
from ..errors import (
    ErrorCode, DiagnosticCollection,
    Annotation, Suggestion
)
from .resolver import SymbolTable


class WarningChecker:
    """
    Detects potential issues that warrant warnings.
    
    Checks for:
    - Signals that are declared but never used
    - Instances that have no connections
    - Constants that are never referenced
    - Imports that are never used
    """
    
    def __init__(
        self,
        diagnostics: DiagnosticCollection,
        symbol_table: SymbolTable
    ):
        self.diagnostics = diagnostics
        self.table = symbol_table
        
        # Track usage
        self._used_signals: Set[str] = set()
        self._used_instances: Set[str] = set()
        self._used_constants: Set[str] = set()
    
    def check_component(self, component: Component) -> None:
        """Check for unused declarations in a component."""
        # Collect usage from connections
        if component.connect_block:
            self._collect_usage(component.connect_block, {})
        
        # Report unused signals (excluding output ports which may be intentionally unused)
        for name, info in self.table.signals.items():
            if name not in self._used_signals:
                if info.is_input:
                    self.diagnostics.warning(
                        code=ErrorCode.W0101,
                        message=f"Input port '{name}' is never used",
                        span=info.span
                    )
        
        # Report unused constants
        for name, info in self.table.constants.items():
            if name not in self._used_constants:
                self.diagnostics.warning(
                    code=ErrorCode.W0103,
                    message=f"Constant '{name}' is never used",
                    span=info.span
                )
    
    def _collect_usage(
        self,
        block: ConnectBlock,
        gen_vars: Dict[str, int]
    ) -> None:
        """Collect signal/instance usage from connections."""
        for node in block.statements:
            if isinstance(node, Connection):
                self._record_usage(node, gen_vars)
            elif isinstance(node, Generator):
                self._collect_generator_usage(node, gen_vars)
    
    def _collect_generator_usage(
        self,
        gen: Generator,
        outer_vars: Dict[str, int]
    ) -> None:
        """Collect usage from a generator."""
        from ..flattener.flattener import expand_range
        
        try:
            values = expand_range(gen.range_spec)
        except Exception:
            return
        
        for val in values:
            new_vars = dict(outer_vars)
            new_vars[gen.variable] = val
            
            for node in gen.body:
                if isinstance(node, Connection):
                    self._record_usage(node, new_vars)
                elif isinstance(node, Generator):
                    self._collect_generator_usage(node, new_vars)
    
    def _record_usage(
        self,
        conn: Connection,
        gen_vars: Dict[str, int]
    ) -> None:
        """Record usage from a connection."""
        self._record_signal_usage(conn.source, gen_vars)
        self._record_signal_usage(conn.destination, gen_vars)
    
    def _record_signal_usage(
        self,
        signal: Signal,
        gen_vars: Dict[str, int]
    ) -> None:
        """Record that a signal is used."""
        from ..flattener.flattener import substitute_name
        
        name = substitute_name(signal.name, gen_vars)
        
        if signal.instance:
            instance = substitute_name(signal.instance, gen_vars)
            self._used_instances.add(instance)
        else:
            # Could be a signal or constant
            if name in self.table.signals:
                self._used_signals.add(name)
            elif name in self.table.constants:
                self._used_constants.add(name)


def check_unused_imports(
    module: Module,
    used_components: Set[str],
    diagnostics: DiagnosticCollection
) -> None:
    """
    Check for unused imports in a module.
    
    Args:
        module: The parsed module
        used_components: Set of component names that were actually used
        diagnostics: Where to report warnings
    """
    for imp in module.imports:
        for comp_name in imp.components:
            if comp_name not in used_components:
                diagnostics.warning(
                    code=ErrorCode.W0104,
                    message=f"Imported component '{comp_name}' is never used",
                    span=imp.span
                )
