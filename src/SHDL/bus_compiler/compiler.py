"""
Bus Compiler Orchestration.

Pipeline: Flattened Component -> ConnectionGraph -> BusAnalyzer -> BusCodeGenerator -> clang
"""

import os
import subprocess
import tempfile
from typing import Optional

from ..compiler.compiler import CompileResult
from .graph import ConnectionGraph
from .analyzer import BusAnalyzer
from .codegen import BusCodeGenerator


class BusCompiler:
    """Compiles a flattened Component to C using bus-width operations."""

    def compile(self, component) -> str:
        """Generate C code from a flattened Component (expanded AST)."""
        graph = ConnectionGraph.from_component(component)
        analysis = BusAnalyzer(graph).analyze()
        return BusCodeGenerator(analysis).generate()

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
