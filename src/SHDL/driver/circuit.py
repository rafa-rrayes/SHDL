"""
SHDLCircuit - Main circuit driver class

Provides a clean, Pythonic interface for compiling and simulating SHDL circuits.
"""

import ctypes
import tempfile
import os
import platform
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass, field

from .exceptions import CompilationError, SimulationError, SignalNotFoundError


def _get_library_extension() -> str:
    """Get the shared library extension for the current platform."""
    system = platform.system()
    if system == "Darwin":
        return ".dylib"
    elif system == "Windows":
        return ".dll"
    else:
        return ".so"


@dataclass
class PortInfo:
    """Information about a circuit port."""
    name: str
    width: int  # Number of bits (1 for single-bit)
    is_input: bool
    
    @property
    def max_value(self) -> int:
        """Maximum value this port can hold."""
        return (1 << self.width) - 1


@dataclass
class CircuitInfo:
    """Information about a compiled circuit."""
    name: str
    inputs: list[PortInfo] = field(default_factory=list)
    outputs: list[PortInfo] = field(default_factory=list)
    
    @property
    def all_ports(self) -> list[PortInfo]:
        """All ports (inputs + outputs)."""
        return self.inputs + self.outputs
    
    def get_port(self, name: str) -> Optional[PortInfo]:
        """Get a port by name."""
        for port in self.all_ports:
            if port.name == name:
                return port
        return None


class SHDLCircuit:
    """
    A compiled SHDL circuit that can be simulated.
    
    This class provides a clean Python interface for:
    - Loading and compiling SHDL source files
    - Setting input values (poke)
    - Reading output values (peek)
    - Advancing simulation time (step)
    
    Example:
        >>> circuit = SHDLCircuit("adder16.shdl")
        >>> circuit.poke("A", 42)
        >>> circuit.poke("B", 17)
        >>> circuit.step(1)
        >>> print(circuit.peek("Sum"))
        59
    
    The circuit can also be used as a context manager:
        >>> with SHDLCircuit("adder16.shdl") as circuit:
        ...     circuit["A"] = 42
        ...     circuit["B"] = 17
        ...     circuit.step()
        ...     print(circuit["Sum"])
    """
    
    def __init__(
        self,
        source: Union[str, Path],
        component: Optional[str] = None,
        *,
        flatten: bool = True,
        keep_library: bool = False,
        library_dir: Optional[Union[str, Path]] = None,
        cc: str = "clang",
        optimize: int = 3,
        include_paths: Optional[list[Union[str, Path]]] = None,
    ):
        """
        Create a new SHDL circuit from a source file or string.
        
        Args:
            source: Path to .shdl file or SHDL source code string
            component: Component name to compile (default: last component)
            flatten: If True, flatten Expanded SHDL to Base SHDL first
            keep_library: If True, don't delete the compiled library on cleanup
            library_dir: Directory for compiled library (default: temp dir)
            cc: C compiler to use
            optimize: Optimization level (0-3)
            include_paths: Additional directories to search for imported modules
        """
        self._lib: Optional[ctypes.CDLL] = None
        self._lib_path: Optional[Path] = None
        self._keep_library = keep_library
        self._info: Optional[CircuitInfo] = None
        self._include_paths = [str(p) for p in include_paths] if include_paths else []
        
        # Determine if source is a file path or source code
        source_path = Path(source) if not isinstance(source, Path) else source
        
        if source_path.exists() and source_path.is_file():
            self._compile_file(
                source_path,
                component=component,
                flatten=flatten,
                library_dir=library_dir,
                cc=cc,
                optimize=optimize,
            )
        else:
            # Treat as source code string
            self._compile_source(
                str(source),
                component=component,
                flatten=flatten,
                library_dir=library_dir,
                cc=cc,
                optimize=optimize,
            )
    
    def _compile_file(
        self,
        path: Path,
        component: Optional[str],
        flatten: bool,
        library_dir: Optional[Union[str, Path]],
        cc: str,
        optimize: int,
    ) -> None:
        """Compile an SHDL file to a shared library."""
        from ..flattener import Flattener
        from ..compiler import SHDLCompiler
        
        # Determine output path
        if library_dir:
            lib_dir = Path(library_dir)
            lib_dir.mkdir(parents=True, exist_ok=True)
        else:
            lib_dir = Path(tempfile.mkdtemp(prefix="shdl_"))
        
        # Get component name
        if flatten:
            # Build search paths: file's directory + user-provided include paths
            search_paths = [str(path.parent)] + self._include_paths
            flattener = Flattener(search_paths=search_paths)
            flattener.load_file(str(path))
            
            if component:
                comp_name = component
            else:
                # Use the last component
                comp_name = list(flattener._library.components.keys())[-1]
            
            # Extract port info before flattening
            original_comp = flattener._library.components[comp_name]
            self._info = CircuitInfo(
                name=comp_name,
                inputs=[
                    PortInfo(p.name, p.width or 1, is_input=True)
                    for p in original_comp.inputs
                ],
                outputs=[
                    PortInfo(p.name, p.width or 1, is_input=False)
                    for p in original_comp.outputs
                ],
            )
            
            # Flatten to Base SHDL
            base_shdl = flattener.flatten_to_base_shdl(comp_name)
        else:
            # Read file directly as Base SHDL
            with open(path, 'r') as f:
                base_shdl = f.read()
            comp_name = component
        
        # Compile to library
        lib_name = f"lib{comp_name or 'circuit'}{_get_library_extension()}"
        self._lib_path = lib_dir / lib_name
        
        compiler = SHDLCompiler()
        result = compiler.compile_to_library(
            base_shdl,
            str(self._lib_path),
            component_name=comp_name,
            cc=cc,
            cflags=[f"-O{optimize}"],
        )
        
        if not result.success:
            errors_str = "\n".join(result.errors) if result.errors else "Unknown error"
            raise CompilationError(
                f"Failed to compile {path}:\n{errors_str}",
                errors=result.errors
            )
        
        # Load the library
        self._load_library()
    
    def _compile_source(
        self,
        source: str,
        component: Optional[str],
        flatten: bool,
        library_dir: Optional[Union[str, Path]],
        cc: str,
        optimize: int,
    ) -> None:
        """Compile SHDL source code to a shared library."""
        from ..flattener import Flattener
        from ..compiler import SHDLCompiler
        
        # Determine output path
        if library_dir:
            lib_dir = Path(library_dir)
            lib_dir.mkdir(parents=True, exist_ok=True)
        else:
            lib_dir = Path(tempfile.mkdtemp(prefix="shdl_"))
        
        if flatten:
            flattener = Flattener(search_paths=self._include_paths)
            flattener.load_source(source)
            
            if component:
                comp_name = component
            else:
                comp_name = list(flattener._library.components.keys())[-1]
            
            # Extract port info
            original_comp = flattener._library.components[comp_name]
            self._info = CircuitInfo(
                name=comp_name,
                inputs=[
                    PortInfo(p.name, p.width or 1, is_input=True)
                    for p in original_comp.inputs
                ],
                outputs=[
                    PortInfo(p.name, p.width or 1, is_input=False)
                    for p in original_comp.outputs
                ],
            )
            
            base_shdl = flattener.flatten_to_base_shdl(comp_name)
        else:
            base_shdl = source
            comp_name = component
        
        # Compile
        lib_name = f"lib{comp_name or 'circuit'}{_get_library_extension()}"
        self._lib_path = lib_dir / lib_name
        
        compiler = SHDLCompiler()
        result = compiler.compile_to_library(
            base_shdl,
            str(self._lib_path),
            component_name=comp_name,
            cc=cc,
            cflags=[f"-O{optimize}"],
        )
        
        if not result.success:
            raise CompilationError(
                "Failed to compile source",
                errors=result.errors
            )
        
        self._load_library()
    
    def _load_library(self) -> None:
        """Load the compiled shared library."""
        if self._lib_path is None or not self._lib_path.exists():
            raise SimulationError("Library not found")
        
        self._lib = ctypes.CDLL(str(self._lib_path))
        
        # Set up function signatures
        self._lib.reset.argtypes = []
        self._lib.reset.restype = None
        
        self._lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
        self._lib.poke.restype = None
        
        self._lib.peek.argtypes = [ctypes.c_char_p]
        self._lib.peek.restype = ctypes.c_uint64
        
        self._lib.step.argtypes = [ctypes.c_int]
        self._lib.step.restype = None
        
        # Initialize
        self._lib.reset()
    
    def reset(self) -> None:
        """Reset the circuit to its initial state."""
        if self._lib is None:
            raise SimulationError("Circuit not loaded")
        self._lib.reset()
    
    def poke(self, signal: str, value: int) -> None:
        """
        Set an input signal to a value.
        
        Args:
            signal: Name of the input signal
            value: Value to set (will be masked to signal width)
        """
        if self._lib is None:
            raise SimulationError("Circuit not loaded")
        self._lib.poke(signal.encode('utf-8'), value)
    
    def peek(self, signal: str) -> int:
        """
        Read the current value of a signal.
        
        Args:
            signal: Name of the signal (input or output)
        
        Returns:
            Current value of the signal
        """
        if self._lib is None:
            raise SimulationError("Circuit not loaded")
        return self._lib.peek(signal.encode('utf-8'))
    
    def step(self, cycles: int = 1) -> None:
        """
        Advance the simulation by a number of cycles.
        
        Args:
            cycles: Number of cycles to advance (default: 1)
        """
        if self._lib is None:
            raise SimulationError("Circuit not loaded")
        self._lib.step(cycles)
    
    # Pythonic dict-like interface
    
    def __getitem__(self, signal: str) -> int:
        """Read a signal value: circuit["Sum"]"""
        return self.peek(signal)
    
    def __setitem__(self, signal: str, value: int) -> None:
        """Set an input value: circuit["A"] = 42"""
        self.poke(signal, value)
    
    # Context manager support
    
    def __enter__(self) -> "SHDLCircuit":
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and clean up."""
        self.close()
    
    def close(self) -> None:
        """Clean up resources."""
        self._lib = None
        
        if not self._keep_library and self._lib_path:
            try:
                if self._lib_path.exists():
                    os.unlink(self._lib_path)
                # Also try to remove the temp directory if empty
                if self._lib_path.parent.exists():
                    try:
                        self._lib_path.parent.rmdir()
                    except OSError:
                        pass  # Directory not empty
            except Exception:
                pass  # Ignore cleanup errors
    
    def __del__(self) -> None:
        """Destructor - clean up if not already done."""
        try:
            self.close()
        except Exception:
            pass
    
    # Properties
    
    @property
    def info(self) -> Optional[CircuitInfo]:
        """Get information about the circuit."""
        return self._info
    
    @property
    def name(self) -> str:
        """Get the circuit name."""
        return self._info.name if self._info else "unknown"
    
    @property
    def inputs(self) -> list[str]:
        """Get list of input port names."""
        if self._info:
            return [p.name for p in self._info.inputs]
        return []
    
    @property
    def outputs(self) -> list[str]:
        """Get list of output port names."""
        if self._info:
            return [p.name for p in self._info.outputs]
        return []
    
    def __repr__(self) -> str:
        """String representation."""
        if self._info:
            ins = ", ".join(self.inputs)
            outs = ", ".join(self.outputs)
            return f"SHDLCircuit({self.name}, inputs=[{ins}], outputs=[{outs}])"
        return "SHDLCircuit(unloaded)"
