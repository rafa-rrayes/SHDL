"""
SHDL - Simple Hardware Description Language

A Python library for parsing, flattening, and compiling SHDL circuits.
"""

# Errors (shared across packages)
from .errors import (
    SHDLError, LexerError, ParseError, FlattenerError, ValidationError,
    SemanticError, ImportError_,
    ErrorCode, Severity, Diagnostic, DiagnosticCollection,
    Annotation, Suggestion, RelatedInfo,
    find_similar, suggest_component,
)

# Source mapping
from .source_map import (
    SourceSpan, SourceOrigin, SourceFile, GeneratorContext,
    highlight_span,
)

# Flattener (Expanded SHDL -> Base SHDL)
from .flattener import (
    Token, TokenType,
    Lexer,
    Module, Component, Port, Instance, Constant, Connection,
    Signal, IndexExpr, Generator, Import, ConnectBlock,
    Parser, parse, parse_file,
    Flattener, flatten_file, format_base_shdl,
)

# Semantic Analysis
from .semantic import (
    SemanticAnalyzer as SHDLSemanticAnalyzer,
    analyze as semantic_analyze,
    analyze_file as semantic_analyze_file,
    ComponentResolver,
    SymbolTable,
    TypeChecker,
    ConnectionChecker,
    WarningChecker,
)

# Compiler (Base SHDL -> C)
from .compiler import (
    compile_base_shdl,
    compile_shdl_file,
    CodeGenerator,
    SemanticAnalyzer,  # This is the Base SHDL analyzer
    AnalysisResult,
    BaseSHDLParser,
    BaseSHDLLexer,
)

# Driver (Python interface to compiled circuits)
from .driver import (
    SHDLCircuit,
    SHDLDriverError,
    CompilationError,
    SimulationError,
    SignalNotFoundError,
    PortInfo,
    CircuitInfo,
)

# Debugger (SHDB - Simple Hardware Debugger)
from .debugger import (
    # High-level API
    Circuit,
    StopResult,
    WaveformSample,
    Breakpoint,
    Watchpoint,
    # Low-level
    DebugController,
    DebugInfo,
    SymbolTable,
    SignalRef,
    SourceMap,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    
    # Tokens
    "Token",
    "TokenType",
    
    # Lexer
    "Lexer",
    
    # AST Nodes
    "Module",
    "Component", 
    "Port",
    "Instance",
    "Constant",
    "Connection",
    "Signal",
    "IndexExpr",
    "Generator",
    "Import",
    "ConnectBlock",
    
    # Parser
    "Parser",
    "parse",
    "parse_file",
    
    # Flattener
    "Flattener",
    "flatten_file",
    "format_base_shdl",
    
    # Compiler
    "compile_base_shdl",
    "compile_shdl_file",
    "CodeGenerator",
    "SemanticAnalyzer",
    "AnalysisResult",
    "BaseSHDLParser",
    "BaseSHDLLexer",
    
    # Semantic Analysis
    "SHDLSemanticAnalyzer",
    "semantic_analyze",
    "semantic_analyze_file",
    "ComponentResolver",
    "SymbolTable",
    "TypeChecker",
    "ConnectionChecker",
    "WarningChecker",
    
    # Driver
    "SHDLCircuit",
    "SHDLDriverError",
    "CompilationError",
    "SimulationError",
    "SignalNotFoundError",
    "PortInfo",
    "CircuitInfo",
    
    # Debugger (SHDB)
    "Circuit",
    "StopResult",
    "WaveformSample",
    "Breakpoint",
    "Watchpoint",
    "DebugController",
    "DebugInfo",
    "SymbolTable",
    "SignalRef",
    "SourceMap",
    
    # Errors
    "SHDLError",
    "LexerError", 
    "ParseError",
    "FlattenerError",
    "ValidationError",
    "SemanticError",
    "ImportError_",
    "ErrorCode",
    "Severity",
    "Diagnostic",
    "DiagnosticCollection",
    "Annotation",
    "Suggestion",
    "RelatedInfo",
    "find_similar",
    "suggest_component",
    
    # Source mapping
    "SourceSpan",
    "SourceOrigin",
    "SourceFile",
    "GeneratorContext",
    "highlight_span",
]
