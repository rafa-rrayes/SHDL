"""PySHDL — the Python driver for SHDL circuits.

The user-facing layer of the SHDL toolchain: compile a circuit (from a
``.shdl`` file, SHDL source text, a Base SHDL artifact, or a prebuilt
shared library) and drive the simulation through an ergonomic interface::

    from pyshdl import Circuit

    with Circuit("examples/adder8.shdl") as c:
        c["A"] = 100
        c["B"] = 55
        c.settle()
        print(c["Sum"])  # 155

Everything runs in-process: the flattener lowers SHDL to Base SHDL, shdlc
generates C, the host C compiler builds a shared library, and ctypes loads
a private copy of it. See ``docs/pyshdl.md`` for the user guide.
"""

from __future__ import annotations

__version__ = "1.0.0"

from .circuit import Circuit
from .errors import (
    BuildError,
    ClosedCircuitError,
    CompilationError,
    CompileError,
    FlattenError,
    MetadataUnavailableError,
    PortValueError,
    PySHDLError,
    SettleRefusedError,
    SignalNotFoundError,
    SimulationError,
)
from .info import CircuitInfo, PortInfo, TimingInfo

__all__ = [
    "BuildError",
    "Circuit",
    "CircuitInfo",
    "ClosedCircuitError",
    "CompilationError",
    "CompileError",
    "FlattenError",
    "MetadataUnavailableError",
    "PortInfo",
    "PortValueError",
    "PySHDLError",
    "SettleRefusedError",
    "SignalNotFoundError",
    "SimulationError",
    "TimingInfo",
    "__version__",
]
