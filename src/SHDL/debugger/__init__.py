"""
SHDB - Simple Hardware Debugger

A professional interactive debugger for SHDL circuits.

Usage:
    # Python API
    from SHDL.debugger import Circuit
    
    with Circuit("adder16.shdl") as c:
        c.poke("A", 42)
        c.poke("B", 17)
        c.step()
        print(c.peek("Sum"))  # 59
    
    # Or use the shdb command:
    #   $ shdb adder16.shdl
"""

# High-level API (primary interface)
from .circuit import (
    Circuit,
    PortInfo as CircuitPortInfo,
    GateInfo as CircuitGateInfo,
    SourceLocation as CircuitSourceLocation,
    StopResult,
    WaveformSample,
    Breakpoint,
    Watchpoint,
)

# Low-level debug info
from .debuginfo import (
    DebugInfo,
    PortInfo,
    GateInfo,
    InstanceInfo,
    SourceLocation,
    ConnectionInfo,
    ConstantInfo,
    HierarchyNode,
)

# Symbol resolution
from .symbols import SymbolTable, SignalRef, SignalType

# Source mapping
from .sourcemap import SourceMap

# Controller (lower-level API)
from .controller import (
    DebugController,
    StopReason,
    StopInfo,
    BreakpointType,
    Breakpoint as ControllerBreakpoint,
    Watchpoint as ControllerWatchpoint,
)

__all__ = [
    # High-level API (recommended)
    "Circuit",
    "StopResult",
    "WaveformSample",
    "Breakpoint",
    "Watchpoint",
    
    # Debug info
    "DebugInfo",
    "PortInfo", 
    "GateInfo",
    "InstanceInfo",
    "SourceLocation",
    "ConnectionInfo",
    "ConstantInfo",
    "HierarchyNode",
    
    # Symbols
    "SymbolTable",
    "SignalRef",
    "SignalType",
    
    # Source mapping
    "SourceMap",
    
    # Controller (lower-level)
    "DebugController",
    "StopReason",
    "StopInfo",
    "BreakpointType",
]
