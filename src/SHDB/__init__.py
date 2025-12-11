"""
SHDB - Simple Hardware Debugger

This module provides a convenient alias for the SHDL debugger.
Import this module to access the debugger API:

    import shdb
    
    with shdb.Circuit("adder16.shdl") as c:
        c.poke("A", 42)
        c.poke("B", 17)
        c.step()
        print(c.peek("Sum"))  # 59

Or use the shdb command-line tool:

    $ shdb adder16.shdl
"""

# Re-export everything from SHDL.debugger
from SHDL.debugger import (
    # High-level API (primary interface)
    Circuit,
    StopResult,
    WaveformSample,
    Breakpoint,
    Watchpoint,
    
    # Low-level debug info
    DebugInfo,
    PortInfo,
    GateInfo,
    InstanceInfo,
    SourceLocation,
    ConnectionInfo,
    ConstantInfo,
    HierarchyNode,
    
    # Symbol resolution
    SymbolTable,
    SignalRef,
    SignalType,
    
    # Source mapping
    SourceMap,
    
    # Controller (lower-level API)
    DebugController,
    StopReason,
    StopInfo,
    BreakpointType,
)

__version__ = "1.0.0"

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
