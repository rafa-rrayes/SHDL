"""
SHDL Semantic Analyzer

Main driver for semantic analysis. Runs all checks in the correct order.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Set

from ..flattener.ast import Module, Component
from ..source_map import SourceSpan, SourceFile
from ..errors import (
    DiagnosticCollection, Diagnostic, ValidationError, SemanticError
)
from .resolver import ComponentResolver, SymbolTable, build_symbol_table
from .type_check import TypeChecker
from .connection import ConnectionChecker
from .warnings import WarningChecker, check_unused_imports


@dataclass
class AnalysisResult:
    """Result of semantic analysis."""
    diagnostics: DiagnosticCollection
    symbol_tables: dict  # component_name -> SymbolTable
    resolver: ComponentResolver
    
    @property
    def has_errors(self) -> bool:
        return self.diagnostics.has_errors()
    
    @property
    def has_warnings(self) -> bool:
        return self.diagnostics.has_warnings()
    
    def raise_if_errors(self) -> None:
        """Raise an exception if there are errors."""
        self.diagnostics.raise_if_errors()
    
    def print_diagnostics(self) -> None:
        """Print all diagnostics to stderr."""
        self.diagnostics.print_all()


class SemanticAnalyzer:
    """
    Performs comprehensive semantic analysis on SHDL modules.
    
    Analysis phases:
    1. Process imports and build component library
    2. For each component:
       a. Build symbol table (resolve names)
       b. Type check (validate widths)
       c. Check connections (completeness)
       d. Check for warnings (unused symbols)
    """
    
    def __init__(
        self,
        search_paths: List[str] = None,
        enable_warnings: bool = True
    ):
        self.search_paths = search_paths or ["."]
        self.enable_warnings = enable_warnings
        
        self.diagnostics = DiagnosticCollection()
        self.resolver = ComponentResolver(
            diagnostics=self.diagnostics,
            search_paths=self.search_paths
        )
        self.symbol_tables: dict = {}
        self._used_components: Set[str] = set()
    
    def analyze(self, module: Module) -> AnalysisResult:
        """
        Analyze a complete SHDL module.
        
        Returns an AnalysisResult with diagnostics and symbol tables.
        """
        # Phase 1: Process imports
        for imp in module.imports:
            self.resolver.process_import(imp)
        
        # Phase 2: Register all components in the module
        for comp in module.components:
            self.resolver.register_component(comp)
        
        # Phase 3: Analyze each component
        for comp in module.components:
            self._analyze_component(comp)
        
        # Phase 4: Check for unused imports
        if self.enable_warnings:
            check_unused_imports(module, self._used_components, self.diagnostics)
        
        return AnalysisResult(
            diagnostics=self.diagnostics,
            symbol_tables=self.symbol_tables,
            resolver=self.resolver
        )
    
    def _analyze_component(self, component: Component) -> None:
        """Analyze a single component."""
        # Build symbol table (resolves names, checks duplicates)
        table = build_symbol_table(
            component=component,
            resolver=self.resolver,
            diagnostics=self.diagnostics
        )
        self.symbol_tables[component.name] = table
        
        # Track used components
        for inst in table.instances.values():
            self._used_components.add(inst.component_type)
        
        # Type checking (validate widths)
        type_checker = TypeChecker(
            diagnostics=self.diagnostics,
            symbol_table=table
        )
        type_checker.check_component(component)
        
        # Connection checking (completeness)
        conn_checker = ConnectionChecker(
            diagnostics=self.diagnostics,
            symbol_table=table
        )
        conn_checker.check_component(component)
        
        # Warning detection
        if self.enable_warnings:
            warn_checker = WarningChecker(
                diagnostics=self.diagnostics,
                symbol_table=table
            )
            warn_checker.check_component(component)


def analyze(
    source: str,
    file_path: str = "<string>",
    search_paths: List[str] = None,
    enable_warnings: bool = True
) -> AnalysisResult:
    """
    Analyze SHDL source code.
    
    Args:
        source: SHDL source code
        file_path: Path for error reporting
        search_paths: Directories to search for imports
        enable_warnings: Whether to report warnings
    
    Returns:
        AnalysisResult with diagnostics and symbol information
    """
    from ..flattener.parser import parse
    
    # Register source for error messages
    SourceFile.register(file_path, source)
    
    # Parse
    module = parse(source, file_path=file_path)
    
    # Determine search paths
    paths = search_paths or ["."]
    if file_path != "<string>":
        from pathlib import Path
        file_dir = str(Path(file_path).parent)
        if file_dir not in paths:
            paths = [file_dir] + paths
    
    # Analyze
    analyzer = SemanticAnalyzer(
        search_paths=paths,
        enable_warnings=enable_warnings
    )
    
    return analyzer.analyze(module)


def analyze_file(
    path: str,
    search_paths: List[str] = None,
    enable_warnings: bool = True
) -> AnalysisResult:
    """
    Analyze an SHDL file.
    
    Args:
        path: Path to the SHDL file
        search_paths: Additional directories to search for imports
        enable_warnings: Whether to report warnings
    
    Returns:
        AnalysisResult with diagnostics and symbol information
    """
    with open(path, 'r') as f:
        source = f.read()
    
    return analyze(
        source=source,
        file_path=path,
        search_paths=search_paths,
        enable_warnings=enable_warnings
    )


def validate(
    source: str,
    file_path: str = "<string>",
    search_paths: List[str] = None
) -> None:
    """
    Validate SHDL source code and raise on errors.
    
    This is a convenience function that analyzes and raises
    if there are any errors.
    
    Args:
        source: SHDL source code
        file_path: Path for error reporting
        search_paths: Directories to search for imports
    
    Raises:
        ValidationError: If there are any errors
    """
    result = analyze(source, file_path, search_paths)
    result.raise_if_errors()


def validate_file(
    path: str,
    search_paths: List[str] = None
) -> None:
    """
    Validate an SHDL file and raise on errors.
    
    Args:
        path: Path to the SHDL file
        search_paths: Additional directories to search for imports
    
    Raises:
        ValidationError: If there are any errors
    """
    result = analyze_file(path, search_paths)
    result.raise_if_errors()
