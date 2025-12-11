"""
PySHDL - Python Driver for SHDL Circuits

A minimal module for compiling and driving SHDL circuits from Python.
Provides a clean, Pythonic API for circuit simulation.

Example:
    >>> from SHDL import Circuit
    >>> 
    >>> # Load and compile a circuit
    >>> circuit = Circuit("adder16.shdl")
    >>> 
    >>> # Set inputs
    >>> circuit.poke("A", 42)
    >>> circuit.poke("B", 17)
    >>> 
    >>> # Run simulation
    >>> circuit.step(1)
    >>> 
    >>> # Read outputs
    >>> print(circuit.peek("Sum"))
"""

from .circuit import Circuit, PortInfo, CircuitInfo
from .exceptions import (
    SHDLDriverError,
    CompilationError,
    SimulationError,
    SignalNotFoundError,
)

__all__ = [
    "Circuit",
    "PortInfo",
    "CircuitInfo",
    "SHDLDriverError",
    "CompilationError",
    "SimulationError",
    "SignalNotFoundError",
]
