"""
SHDL Driver - Simple Python interface for SHDL circuits
========================================================

A minimal module for compiling and driving SHDL circuits from Python.
Provides a clean, Pythonic API for circuit simulation.

Usage:
    from shdl_driver import SHDLCircuit
    
    # Load and compile a circuit
    circuit = SHDLCircuit("adder16.shdl")
    
    # Set inputs
    circuit.poke("A", 42)
    circuit.poke("B", 17)
    circuit.poke("Cin", 1)
    
    # Read outputs
    result = circuit.peek("Sum")
    print(f"42 + 17 + 1 = {result}")
    
    # Advance simulation time
    circuit.step(1)
"""

import ctypes
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Union


class Circuit:
    """
    Interface for driving SHDL circuits from Python.
    
    Compiles SHDL to C, builds a shared library, and provides
    Python wrappers for the circuit API.
    """
    
    def __init__(self, shdl_file: Union[str, Path], search_paths: Optional[list] = None):
        """
        Load and compile a SHDL circuit.
        
        Args:
            shdl_file: Path to the .shdl file
            search_paths: Optional list of directories to search for imports
        """
        self.shdl_file = Path(shdl_file)
        if not self.shdl_file.exists():
            raise FileNotFoundError(f"SHDL file not found: {shdl_file}")
        
        # Default search path includes SHDL_components if it exists
        if search_paths is None:
            search_paths = []
            component_dir = self.shdl_file.parent / "SHDL_components"
            if component_dir.exists():
                search_paths.append(str(component_dir))
        
        self.search_paths = search_paths
        self._lib = None
        self._compile_and_load()
    
    def _compile_and_load(self):
        """Compile SHDL to C and load the shared library."""
        # Generate C code
        c_file = self.shdl_file.with_suffix('.c')
        self._compile_shdl_to_c(c_file)
        
        # Build shared library
        so_file = self._build_shared_library(c_file)
        
        # Load library
        self._lib = ctypes.CDLL(str(so_file))
        
        # Set up function signatures
        self._lib.reset.argtypes = []
        self._lib.reset.restype = None
        
        self._lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
        self._lib.poke.restype = None
        
        self._lib.peek.argtypes = [ctypes.c_char_p]
        self._lib.peek.restype = ctypes.c_uint64
        
        self._lib.step.argtypes = [ctypes.c_int]
        self._lib.step.restype = None
        
        # Initialize circuit
        self.reset()
    
    def _compile_shdl_to_c(self, output_file: Path):
        """Compile SHDL file to C using shdlc compiler."""
        # Look for shdlc in the same directory as the SHDL file
        from .shdlc import generate_c_code, SHDLParser
        shdl_parser = SHDLParser(self.search_paths)
        component = shdl_parser.parse_file(self.shdl_file)
        component = shdl_parser.flatten_all_levels(component)
        c_code = generate_c_code(component)
        with open(output_file, 'w') as f:
            f.write(c_code)
            
    def _build_shared_library(self, c_file: Path) -> Path:
        """Build a shared library from C code."""
        so_file = c_file.with_suffix('.so')
        
        cmd = [
            "gcc",
            "-shared",
            "-fPIC",
            "-O2",
            "-o", str(so_file),
            "-xc", str(c_file)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to build shared library:\n{e.stderr}"
            )
        
        return so_file
    
    def reset(self):
        """Reset all circuit state to zero."""
        self._lib.reset()
    
    def poke(self, signal: str, value: int):
        """
        Set an input signal to a specific value.
        
        Args:
            signal: Name of the input signal
            value: Integer value to set
        """
        self._lib.poke(signal.encode('utf-8'), value)
    
    def peek(self, signal: str) -> int:
        """
        Read the current value of a signal.
        
        Args:
            signal: Name of the signal (input or output)
            
        Returns:
            Current value as an integer
        """
        return self._lib.peek(signal.encode('utf-8'))
    
    def step(self, cycles: int = 1):
        """
        Advance simulation by the specified number of cycles.
        
        Args:
            cycles: Number of clock cycles to advance (default: 1)
        """
        self._lib.step(cycles)

    
    def test(self, inputs: Dict[str, int], steps: int) -> Dict[str, int]:
        """
        Convenience method: set inputs and return all outputs.
        
        Args:
            inputs: Dictionary mapping signal names to values
            
        Returns:
            Dictionary with the same keys containing output values
        """
        # Set all inputs
        for signal, value in inputs.items():
            self.poke(signal, value)
        
        self.step(steps)
        
        # Read back the same signals
        return {signal: self.peek(signal) for signal in inputs.keys()}