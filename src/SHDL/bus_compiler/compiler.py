"""
Bus Compiler Orchestration.

Pipeline: Flattened Component -> ConnectionGraph -> BusAnalyzer -> BusCodeGenerator -> clang
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..compiler.compiler import CompileResult
from .graph import ConnectionGraph
from .analyzer import BusAnalyzer
from .codegen import BusCodeGenerator
from .debug_codegen import BusDebugCodeGenerator
from .debug_info_gen import BusDebugInfoBuilder


class BusCompiler:
    """Compiles a flattened Component to C using bus-width operations."""

    def compile(self, component) -> str:
        """Generate C code from a flattened Component (expanded AST)."""
        graph = ConnectionGraph.from_component(component)
        analysis = BusAnalyzer(graph).analyze()
        return BusCodeGenerator(analysis).generate()

    def compile_debug(self, component) -> str:
        """Generate C code with debug API from a flattened Component."""
        graph = ConnectionGraph.from_component(component)
        analysis = BusAnalyzer(graph).analyze()
        return BusDebugCodeGenerator(analysis).generate()

    def _analyze(self, component):
        """Run the analysis pipeline, returning the AnalysisResult."""
        graph = ConnectionGraph.from_component(component)
        return BusAnalyzer(graph).analyze()

    def compile_to_library(
        self,
        component,
        output_path: str,
        cc: str = "clang",
        cflags: Optional[list[str]] = None,
    ) -> CompileResult:
        """Compile a flattened Component to a shared library."""
        c_code = self.compile(component)

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.c', delete=False
        ) as f:
            f.write(c_code)
            c_path = f.name

        try:
            default_flags = ["-O3", "-shared", "-fPIC"]
            all_flags = default_flags + (cflags or [])
            cmd = [cc] + all_flags + ["-o", output_path, c_path]

            proc = subprocess.run(cmd, capture_output=True, text=True)

            if proc.returncode != 0:
                return CompileResult(
                    success=False,
                    c_code=c_code,
                    errors=[f"C compilation failed: {proc.stderr}"],
                )

            return CompileResult(
                success=True,
                c_code=c_code,
                library_path=output_path,
            )
        finally:
            os.unlink(c_path)

    def compile_to_library_debug(
        self,
        component,
        output_path: str,
        component_name: str = "",
        source_path: str = "",
        cc: str = "clang",
        cflags: Optional[list[str]] = None,
        generate_shdb: bool = True,
    ) -> CompileResult:
        """Compile a flattened Component to a shared library with debug support.

        Produces:
        - A shared library with peek_gate, peek_gate_previous, get_cycle
        - A .shdb file with gate names, ports, hierarchy info
        """
        analysis = self._analyze(component)
        c_code = BusDebugCodeGenerator(analysis).generate()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.c', delete=False
        ) as f:
            f.write(c_code)
            c_path = f.name

        debug_info_path = None

        try:
            # Generate .shdb if requested
            if generate_shdb:
                lib_path = Path(output_path)
                shdb_path = lib_path.with_suffix('.shdb')
                builder = BusDebugInfoBuilder(analysis, source_file=source_path)
                builder.set_component_name(component_name)
                builder.save(str(shdb_path))
                debug_info_path = str(shdb_path)

            # Compile with -g for C debug symbols, -O1 for debug builds
            default_flags = ["-g", "-O1", "-shared", "-fPIC"]
            all_flags = default_flags + (cflags or [])
            cmd = [cc] + all_flags + ["-o", output_path, c_path]

            proc = subprocess.run(cmd, capture_output=True, text=True)

            if proc.returncode != 0:
                return CompileResult(
                    success=False,
                    c_code=c_code,
                    errors=[f"C compilation failed: {proc.stderr}"],
                )

            return CompileResult(
                success=True,
                c_code=c_code,
                library_path=output_path,
                debug_info_path=debug_info_path,
            )
        finally:
            os.unlink(c_path)
