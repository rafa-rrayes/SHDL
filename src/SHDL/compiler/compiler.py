"""
SHDL Compiler Main Module

Provides the main compilation pipeline:
1. Parse Base SHDL (or use flattener for Expanded SHDL)
2. Semantic analysis
3. Code generation
4. Optional: Compile to shared library

Debug builds add:
- Gate name table for runtime lookup
- peek_gate() function
- Cycle counter
- .shdb debug info file
"""

import os
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from .parser import BaseSHDLParser, parse, parse_file
from .analyzer import SemanticAnalyzer, AnalysisResult, analyze
from .codegen import CodeGenerator, generate
from .debug_codegen import DebugCodeGenerator, DebugCodeGenOptions, generate_debug
from .debug_info_gen import DebugInfoBuilder, generate_debug_info


@dataclass
class CompileResult:
    """Result of compilation."""
    success: bool
    c_code: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    library_path: Optional[str] = None
    debug_info_path: Optional[str] = None  # Path to .shdb file if debug build


class SHDLCompiler:
    """
    Main compiler class for SHDL.
    
    Usage:
        compiler = SHDLCompiler()
        result = compiler.compile_file("adder.shdl")
        if result.success:
            print(result.c_code)
    """
    
    def __init__(self, include_paths: list[str] = None):
        """
        Initialize the compiler.
        
        Args:
            include_paths: Directories to search for imported components
        """
        self.include_paths = include_paths or []
    
    def compile_source(self, source: str, component_name: str = None) -> CompileResult:
        """
        Compile Base SHDL source code.
        
        Args:
            source: Base SHDL source code
            component_name: Name of component to compile (default: last component)
        
        Returns:
            CompileResult with generated C code
        """
        # Parse
        try:
            module = parse(source)
        except Exception as e:
            return CompileResult(success=False, errors=[str(e)])
        
        if not module.components:
            return CompileResult(success=False, errors=["No components found"])
        
        # Select component
        if component_name:
            component = module.get_component(component_name)
            if not component:
                return CompileResult(
                    success=False,
                    errors=[f"Component '{component_name}' not found"]
                )
        else:
            component = module.components[-1]
        
        # Analyze
        analysis = analyze(component)
        
        if analysis.has_errors:
            return CompileResult(
                success=False,
                errors=[str(e) for e in analysis.errors],
                warnings=[str(w) for w in analysis.warnings]
            )
        
        # Generate
        c_code = generate(analysis)
        
        return CompileResult(
            success=True,
            c_code=c_code,
            warnings=[str(w) for w in analysis.warnings]
        )
    
    def compile_file(self, path: str, component_name: str = None) -> CompileResult:
        """
        Compile a Base SHDL file.
        
        Args:
            path: Path to the SHDL file
            component_name: Name of component to compile (default: last component)
        
        Returns:
            CompileResult with generated C code
        """
        try:
            with open(path, 'r') as f:
                source = f.read()
        except Exception as e:
            return CompileResult(success=False, errors=[f"Cannot read file: {e}"])
        
        return self.compile_source(source, component_name)
    
    def compile_to_library(
        self,
        source: str,
        output_path: str,
        component_name: str = None,
        cc: str = "clang",
        cflags: list[str] = None
    ) -> CompileResult:
        """
        Compile SHDL source to a shared library.
        
        Args:
            source: Base SHDL source code
            output_path: Path for the output library (.dylib, .so, .dll)
            component_name: Name of component to compile
            cc: C compiler to use
            cflags: Additional compiler flags
        
        Returns:
            CompileResult with library path on success
        """
        # First compile to C
        result = self.compile_source(source, component_name)
        if not result.success:
            return result
        
        # Write C to temp file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.c',
            delete=False
        ) as f:
            f.write(result.c_code)
            c_path = f.name
        
        try:
            # Compile to shared library
            default_flags = ["-O3", "-shared", "-fPIC"]
            all_flags = default_flags + (cflags or [])
            
            cmd = [cc] + all_flags + ["-o", output_path, c_path]
            
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if proc.returncode != 0:
                return CompileResult(
                    success=False,
                    c_code=result.c_code,
                    errors=[f"C compilation failed: {proc.stderr}"],
                    warnings=result.warnings
                )
            
            return CompileResult(
                success=True,
                c_code=result.c_code,
                warnings=result.warnings,
                library_path=output_path
            )
        
        finally:
            # Clean up temp file
            os.unlink(c_path)
    
    def compile_source_debug(
        self,
        source: str,
        component_name: str = None,
        source_path: str = None,
        debug_level: int = 2,
        emit_gate_table: bool = True,
        emit_peek_gate: bool = True,
        emit_cycle_counter: bool = True
    ) -> CompileResult:
        """
        Compile Base SHDL source code with debug information.
        
        Args:
            source: Base SHDL source code
            component_name: Name of component to compile (default: last component)
            source_path: Original source file path for source mapping
            debug_level: Debug level 1-3 (higher = more info)
            emit_gate_table: Include gate name table in output
            emit_peek_gate: Include peek_gate() function
            emit_cycle_counter: Include cycle counter
        
        Returns:
            CompileResult with generated C code (debug version)
        """
        # Parse
        try:
            module = parse(source)
        except Exception as e:
            return CompileResult(success=False, errors=[str(e)])
        
        if not module.components:
            return CompileResult(success=False, errors=["No components found"])
        
        # Select component
        if component_name:
            component = module.get_component(component_name)
            if not component:
                return CompileResult(
                    success=False,
                    errors=[f"Component '{component_name}' not found"]
                )
        else:
            component = module.components[-1]
        
        # Analyze
        analysis = analyze(component)
        
        if analysis.has_errors:
            return CompileResult(
                success=False,
                errors=[str(e) for e in analysis.errors],
                warnings=[str(w) for w in analysis.warnings]
            )
        
        # Generate debug code
        options = DebugCodeGenOptions(
            generate_gate_table=emit_gate_table,
            generate_peek_gate=emit_peek_gate,
            generate_cycle_counter=emit_cycle_counter
        )
        c_code = generate_debug(analysis, options)
        
        return CompileResult(
            success=True,
            c_code=c_code,
            warnings=[str(w) for w in analysis.warnings]
        )
    
    def compile_to_library_debug(
        self,
        source: str,
        output_path: str,
        component_name: str = None,
        source_path: str = None,
        cc: str = "clang",
        cflags: list[str] = None,
        debug_level: int = 2,
        emit_gate_table: bool = True,
        emit_peek_gate: bool = True,
        emit_cycle_counter: bool = True,
        generate_shdb: bool = True
    ) -> CompileResult:
        """
        Compile SHDL source to a shared library with debug support.
        
        This produces:
        - A shared library with debug symbols and introspection APIs
        - A .shdb file with symbol tables and source mappings
        
        Args:
            source: Base SHDL source code
            output_path: Path for the output library (.dylib, .so, .dll)
            component_name: Name of component to compile
            source_path: Original source file path for source mapping
            cc: C compiler to use
            cflags: Additional compiler flags
            debug_level: Debug level 1-3
            emit_gate_table: Include gate name table
            emit_peek_gate: Include peek_gate() function
            emit_cycle_counter: Include cycle counter
            generate_shdb: Generate .shdb debug info file
        
        Returns:
            CompileResult with library path and debug_info_path on success
        """
        # Parse and analyze first (needed for both C and debug info)
        try:
            module = parse(source)
        except Exception as e:
            return CompileResult(success=False, errors=[str(e)])
        
        if not module.components:
            return CompileResult(success=False, errors=["No components found"])
        
        # Select component
        if component_name:
            component = module.get_component(component_name)
            if not component:
                return CompileResult(
                    success=False,
                    errors=[f"Component '{component_name}' not found"]
                )
        else:
            component = module.components[-1]
        
        # Analyze
        analysis = analyze(component)
        
        if analysis.has_errors:
            return CompileResult(
                success=False,
                errors=[str(e) for e in analysis.errors],
                warnings=[str(w) for w in analysis.warnings]
            )
        
        # Generate debug C code
        options = DebugCodeGenOptions(
            generate_gate_table=emit_gate_table,
            generate_peek_gate=emit_peek_gate,
            generate_cycle_counter=emit_cycle_counter
        )
        c_code = generate_debug(analysis, options)
        
        # Write C to temp file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.c',
            delete=False
        ) as f:
            f.write(c_code)
            c_path = f.name
        
        debug_info_path = None
        
        try:
            # Generate .shdb file if requested
            if generate_shdb:
                # Compute .shdb path from library path
                lib_path = Path(output_path)
                shdb_path = lib_path.with_suffix('.shdb')
                
                # Generate debug info and save it
                builder = generate_debug_info(analysis, source_path or "")
                builder.save(str(shdb_path))
                debug_info_path = str(shdb_path)
            
            # Compile to shared library with debug info
            # Use -g for C debug symbols, no -O3 for debug builds
            default_flags = ["-g", "-O1", "-shared", "-fPIC"]
            all_flags = default_flags + (cflags or [])
            
            cmd = [cc] + all_flags + ["-o", output_path, c_path]
            
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if proc.returncode != 0:
                return CompileResult(
                    success=False,
                    c_code=c_code,
                    errors=[f"C compilation failed: {proc.stderr}"],
                    warnings=[str(w) for w in analysis.warnings]
                )
            
            return CompileResult(
                success=True,
                c_code=c_code,
                warnings=[str(w) for w in analysis.warnings],
                library_path=output_path,
                debug_info_path=debug_info_path
            )
        
        finally:
            # Clean up temp file
            os.unlink(c_path)


def compile_base_shdl(source: str, component_name: str = None) -> CompileResult:
    """
    Convenience function to compile Base SHDL source.
    
    Args:
        source: Base SHDL source code
        component_name: Optional component name
    
    Returns:
        CompileResult
    """
    compiler = SHDLCompiler()
    return compiler.compile_source(source, component_name)


def compile_shdl_file(path: str, component_name: str = None) -> CompileResult:
    """
    Convenience function to compile a Base SHDL file.
    
    Args:
        path: Path to SHDL file
        component_name: Optional component name
    
    Returns:
        CompileResult
    """
    compiler = SHDLCompiler()
    return compiler.compile_file(path, component_name)


def compile_to_library(
    source: str,
    output_path: str,
    component_name: str = None
) -> CompileResult:
    """
    Convenience function to compile SHDL to a shared library.
    
    Args:
        source: Base SHDL source code
        output_path: Path for output library
        component_name: Optional component name
    
    Returns:
        CompileResult
    """
    compiler = SHDLCompiler()
    return compiler.compile_to_library(source, output_path, component_name)
