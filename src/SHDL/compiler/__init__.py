"""
SHDL Compiler (shdlc)

Compiles Base SHDL to optimized C code for high-performance circuit simulation.

Debug builds add:
- Gate name table for runtime introspection
- peek_gate() function for querying gate values
- Cycle counter for timing analysis
- .shdb debug info file for symbol tables and source mapping
"""

from .lexer import BaseSHDLLexer, Token, TokenType
from .parser import BaseSHDLParser
from .analyzer import SemanticAnalyzer, AnalysisResult
from .codegen import CodeGenerator
from .debug_codegen import DebugCodeGenerator, DebugCodeGenOptions, generate_debug
from .debug_info_gen import DebugInfoBuilder, generate_debug_info
from .compiler import (
    SHDLCompiler,
    CompileResult,
    compile_base_shdl,
    compile_shdl_file,
    compile_to_library,
)

__all__ = [
    # Lexer
    "BaseSHDLLexer",
    "Token", 
    "TokenType",
    # Parser
    "BaseSHDLParser",
    # Analyzer
    "SemanticAnalyzer",
    "AnalysisResult",
    # Code generation
    "CodeGenerator",
    "DebugCodeGenerator",
    "DebugCodeGenOptions",
    "generate_debug",
    # Debug info
    "DebugInfoBuilder",
    "generate_debug_info",
    # Compiler
    "SHDLCompiler",
    "CompileResult",
    "compile_base_shdl",
    "compile_shdl_file",
    "compile_to_library",
]
