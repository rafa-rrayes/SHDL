"""
Debug Controller

Central controller that manages the debug session, breakpoints, and simulation.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, Any
from pathlib import Path
import ctypes

from .debuginfo import DebugInfo
from .symbols import SymbolTable, SignalRef, SignalType
from .sourcemap import SourceMap


class StopReason(Enum):
    """Reason why execution stopped."""
    NONE = auto()
    STEP = auto()
    BREAKPOINT = auto()
    WATCHPOINT = auto()
    ERROR = auto()
    USER_INTERRUPT = auto()


class BreakpointType(Enum):
    """Type of breakpoint."""
    CHANGE = auto()      # Break on any value change
    VALUE = auto()       # Break when signal equals value
    CONDITION = auto()   # Break when condition is true
    RISING = auto()      # Break on 0->1 transition
    FALLING = auto()     # Break on 1->0 transition


@dataclass
class Breakpoint:
    """A breakpoint on a signal."""
    id: int
    signal: str
    bp_type: BreakpointType
    enabled: bool = True
    temporary: bool = False  # Delete after first hit
    condition: Optional[str] = None  # For CONDITION type
    value: Optional[int] = None  # For VALUE type
    hit_count: int = 0
    
    # Internal state
    _last_value: Optional[int] = None
    
    def __str__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        temp = " (temporary)" if self.temporary else ""
        
        if self.bp_type == BreakpointType.CHANGE:
            desc = f"{self.signal} (any change)"
        elif self.bp_type == BreakpointType.VALUE:
            desc = f"{self.signal} == {self.value}"
        elif self.bp_type == BreakpointType.CONDITION:
            desc = f"{self.signal} if {self.condition}"
        elif self.bp_type == BreakpointType.RISING:
            desc = f"{self.signal} rising edge"
        elif self.bp_type == BreakpointType.FALLING:
            desc = f"{self.signal} falling edge"
        else:
            desc = self.signal
        
        return f"Breakpoint {self.id}: {desc} [{status}]{temp} (hits: {self.hit_count})"


@dataclass
class Watchpoint:
    """A watchpoint that monitors signal changes."""
    id: int
    signal: str
    enabled: bool = True
    hit_count: int = 0
    
    # Internal state
    _last_value: Optional[int] = None
    
    def __str__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"Watchpoint {self.id}: {self.signal} [{status}] (hits: {self.hit_count})"


@dataclass
class StopInfo:
    """Information about why execution stopped."""
    reason: StopReason
    cycle: int = 0
    breakpoint: Optional[Breakpoint] = None
    watchpoint: Optional[Watchpoint] = None
    signal: Optional[str] = None
    old_value: Optional[int] = None
    new_value: Optional[int] = None
    message: str = ""


# Type for signal value change callbacks
WatchCallback = Callable[[str, int, int], bool]  # signal, old, new -> continue?


class DebugController:
    """
    Central debug controller for an SHDL circuit.
    
    Manages:
    - Circuit simulation (via compiled library)
    - Breakpoints and watchpoints
    - Signal value caching
    - Execution control (step, continue, etc.)
    """
    
    def __init__(
        self,
        lib_path: Path | str,
        debug_info: Optional[DebugInfo] = None,
        source_paths: Optional[list[Path]] = None,
    ):
        self.lib_path = Path(lib_path)
        self.debug_info = debug_info
        
        # Load the library
        self._lib = ctypes.CDLL(str(self.lib_path))
        self._setup_library()
        
        # Debug components
        self.symbols: Optional[SymbolTable] = None
        self.source_map: Optional[SourceMap] = None
        
        if debug_info:
            self.symbols = SymbolTable(debug_info)
            self.source_map = SourceMap(debug_info, source_paths)
        
        # State
        self._cycle: int = 0
        self._breakpoints: dict[int, Breakpoint] = {}
        self._watchpoints: dict[int, Watchpoint] = {}
        self._next_bp_id: int = 1
        self._next_wp_id: int = 1
        
        # Signal value cache (for change detection)
        self._signal_cache: dict[str, int] = {}
        
        # Watch callbacks
        self._watch_callbacks: dict[str, list[WatchCallback]] = {}
        
        # Stop state
        self._stop_info: Optional[StopInfo] = None
        self._should_stop: bool = False
    
    def _setup_library(self) -> None:
        """Set up ctypes function signatures."""
        # Standard API
        self._lib.reset.argtypes = []
        self._lib.reset.restype = None
        
        self._lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
        self._lib.poke.restype = None
        
        self._lib.peek.argtypes = [ctypes.c_char_p]
        self._lib.peek.restype = ctypes.c_uint64
        
        self._lib.step.argtypes = [ctypes.c_int]
        self._lib.step.restype = None
        
        # Debug API (optional - check if available)
        self._has_debug_api = hasattr(self._lib, "peek_gate")
        
        if self._has_debug_api:
            self._lib.peek_gate.argtypes = [ctypes.c_char_p]
            self._lib.peek_gate.restype = ctypes.c_uint64
            
            # peek_gate_previous for reading pre-step gate values (breakpoint detection)
            if hasattr(self._lib, "peek_gate_previous"):
                self._lib.peek_gate_previous.argtypes = [ctypes.c_char_p]
                self._lib.peek_gate_previous.restype = ctypes.c_uint64
            
            if hasattr(self._lib, "get_cycle"):
                self._lib.get_cycle.argtypes = []
                self._lib.get_cycle.restype = ctypes.c_uint64
    
    @property
    def cycle(self) -> int:
        """Get current cycle count."""
        if self._has_debug_api and hasattr(self._lib, "get_cycle"):
            return self._lib.get_cycle()
        return self._cycle
    
    @property
    def has_debug_info(self) -> bool:
        """Check if debug info is available."""
        return self.debug_info is not None
    
    # =========================================================================
    # Basic Simulation Control
    # =========================================================================
    
    def reset(self) -> None:
        """Reset the circuit to initial state."""
        self._lib.reset()
        self._cycle = 0
        self._signal_cache.clear()
        self._stop_info = None
        
        # Reset breakpoint/watchpoint last values
        for bp in self._breakpoints.values():
            bp._last_value = None
        for wp in self._watchpoints.values():
            wp._last_value = None
    
    def poke(self, signal: str, value: int) -> None:
        """Set an input signal value."""
        self._lib.poke(signal.encode(), value)
        self._signal_cache[signal] = value
    
    def peek(self, signal: str) -> int:
        """Read a signal value."""
        return self._lib.peek(signal.encode())
    
    def peek_gate(self, gate_name: str) -> int:
        """Read a gate output value (debug builds only)."""
        if not self._has_debug_api:
            raise RuntimeError("Debug API not available (compile with -g)")
        return self._lib.peek_gate(gate_name.encode())
    
    def peek_gate_previous(self, gate_name: str) -> int:
        """Read a gate output value from before the last step (debug builds only).
        
        This is used for breakpoint/watchpoint change detection.
        """
        if not self._has_debug_api:
            raise RuntimeError("Debug API not available (compile with -g)")
        if not hasattr(self._lib, "peek_gate_previous"):
            raise RuntimeError("peek_gate_previous not available (recompile with -g)")
        return self._lib.peek_gate_previous(gate_name.encode())
    
    def step(self, cycles: int = 1) -> StopInfo:
        """
        Step the simulation by a number of cycles.
        
        Checks breakpoints and watchpoints after each cycle.
        
        Returns:
            StopInfo describing why execution stopped
        """
        self._should_stop = False
        self._stop_info = None
        
        for _ in range(cycles):
            # Capture pre-step values for non-gate signals (ports)
            # Gate signals use peek_gate_previous() after step
            self._capture_watched_port_signals()
            
            # Advance one cycle (this saves current -> previous in C code)
            self._lib.step(1)
            self._cycle += 1
            
            # Check for breakpoints/watchpoints
            stop_info = self._check_stop_conditions()
            if stop_info:
                return stop_info
        
        return StopInfo(reason=StopReason.STEP, cycle=self._cycle)
    
    def continue_until_breakpoint(self, max_cycles: int = 1000000) -> StopInfo:
        """
        Continue execution until a breakpoint is hit.
        
        Args:
            max_cycles: Maximum cycles to run before stopping
        
        Returns:
            StopInfo describing why execution stopped
        """
        for _ in range(max_cycles):
            stop_info = self.step(1)
            if stop_info.reason != StopReason.STEP:
                return stop_info
        
        return StopInfo(
            reason=StopReason.STEP,
            cycle=self._cycle,
            message=f"Stopped after {max_cycles} cycles (no breakpoint hit)"
        )
    
    def finish(self, max_cycles: int = 1000) -> StopInfo:
        """
        Run until signals stabilize (for combinational settling).
        
        Detects when no signals change between cycles.
        """
        last_state = self._get_all_signal_values()
        
        for _ in range(max_cycles):
            self._lib.step(1)
            self._cycle += 1
            
            current_state = self._get_all_signal_values()
            if current_state == last_state:
                return StopInfo(
                    reason=StopReason.STEP,
                    cycle=self._cycle,
                    message="Signals stabilized"
                )
            last_state = current_state
        
        return StopInfo(
            reason=StopReason.STEP,
            cycle=self._cycle,
            message=f"Did not stabilize after {max_cycles} cycles"
        )
    
    # =========================================================================
    # Breakpoints
    # =========================================================================
    
    def add_breakpoint(
        self,
        signal: str,
        bp_type: BreakpointType = BreakpointType.CHANGE,
        value: Optional[int] = None,
        condition: Optional[str] = None,
        temporary: bool = False,
    ) -> Breakpoint:
        """
        Add a breakpoint on a signal.
        
        Args:
            signal: Signal name to break on
            bp_type: Type of breakpoint
            value: Value for VALUE type breakpoints
            condition: Condition expression for CONDITION type
            temporary: If True, delete after first hit
        
        Returns:
            The created Breakpoint
        """
        bp = Breakpoint(
            id=self._next_bp_id,
            signal=signal,
            bp_type=bp_type,
            value=value,
            condition=condition,
            temporary=temporary,
        )
        self._breakpoints[bp.id] = bp
        self._next_bp_id += 1
        return bp
    
    def remove_breakpoint(self, bp_id: int) -> bool:
        """Remove a breakpoint by ID."""
        if bp_id in self._breakpoints:
            del self._breakpoints[bp_id]
            return True
        return False
    
    def enable_breakpoint(self, bp_id: int) -> bool:
        """Enable a breakpoint."""
        if bp_id in self._breakpoints:
            self._breakpoints[bp_id].enabled = True
            return True
        return False
    
    def disable_breakpoint(self, bp_id: int) -> bool:
        """Disable a breakpoint."""
        if bp_id in self._breakpoints:
            self._breakpoints[bp_id].enabled = False
            return True
        return False
    
    def clear_breakpoints(self) -> int:
        """Clear all breakpoints. Returns count of removed breakpoints."""
        count = len(self._breakpoints)
        self._breakpoints.clear()
        return count
    
    def get_breakpoints(self) -> list[Breakpoint]:
        """Get all breakpoints."""
        return list(self._breakpoints.values())
    
    # =========================================================================
    # Watchpoints
    # =========================================================================
    
    def add_watchpoint(self, signal: str) -> Watchpoint:
        """Add a watchpoint on a signal."""
        wp = Watchpoint(
            id=self._next_wp_id,
            signal=signal,
        )
        self._watchpoints[wp.id] = wp
        self._next_wp_id += 1
        return wp
    
    def remove_watchpoint(self, wp_id: int) -> bool:
        """Remove a watchpoint by ID."""
        if wp_id in self._watchpoints:
            del self._watchpoints[wp_id]
            return True
        return False
    
    def clear_watchpoints(self) -> int:
        """Clear all watchpoints. Returns count of removed watchpoints."""
        count = len(self._watchpoints)
        self._watchpoints.clear()
        return count
    
    def get_watchpoints(self) -> list[Watchpoint]:
        """Get all watchpoints."""
        return list(self._watchpoints.values())
    
    # =========================================================================
    # Signal Inspection
    # =========================================================================
    
    def get_signal_value(self, signal_ref: SignalRef) -> int:
        """
        Get the value of a resolved signal reference.
        """
        if signal_ref.is_gate:
            if signal_ref.gate_port == "O" and signal_ref.gate_name:
                return self.peek_gate(signal_ref.gate_name)
            else:
                # Gate inputs are not directly readable
                raise ValueError(f"Cannot read gate input: {signal_ref}")
        else:
            value = self.peek(signal_ref.name)
            
            # Handle bit indexing
            if signal_ref.bit_index is not None:
                # Extract single bit (1-based index)
                return (value >> (signal_ref.bit_index - 1)) & 1
            elif signal_ref.is_range:
                # Extract bit range
                start = signal_ref.bit_start or 1
                end = signal_ref.bit_end or signal_ref.width
                mask = (1 << (end - start + 1)) - 1
                return (value >> (start - 1)) & mask
            
            return value
    
    def resolve_and_get(self, name: str) -> tuple[Optional[SignalRef], Optional[int]]:
        """
        Resolve a signal name and get its value.
        
        Returns:
            (SignalRef, value) if successful, (None, None) if not found
        """
        if not self.symbols:
            # No debug info - try direct peek
            try:
                value = self.peek(name)
                return None, value
            except Exception:
                return None, None
        
        ref = self.symbols.resolve(name)
        if ref is None:
            return None, None
        
        try:
            value = self.get_signal_value(ref)
            return ref, value
        except Exception:
            return ref, None
    
    def get_all_inputs(self) -> dict[str, int]:
        """Get all input port values."""
        result = {}
        if self.debug_info:
            for port in self.debug_info.inputs:
                result[port.name] = self.peek(port.name)
        return result
    
    def get_all_outputs(self) -> dict[str, int]:
        """Get all output port values."""
        result = {}
        if self.debug_info:
            for port in self.debug_info.outputs:
                result[port.name] = self.peek(port.name)
        return result
    
    def get_all_gates(self) -> dict[str, int]:
        """Get all gate output values (debug builds only)."""
        if not self._has_debug_api or not self.debug_info:
            return {}
        
        result = {}
        for gate_name in self.debug_info.gates:
            try:
                result[gate_name] = self.peek_gate(gate_name)
            except Exception:
                pass
        return result
    
    # =========================================================================
    # Internal Helpers
    # =========================================================================
    
    def _capture_watched_port_signals(self) -> None:
        """Capture current values of watched port signals for change detection.
        
        Only captures non-gate signals (ports). Gate signals use peek_gate_previous()
        after step() for accurate before/after comparison.
        """
        # Breakpoints on ports only
        for bp in self._breakpoints.values():
            if bp.enabled and not self._is_gate_signal(bp.signal):
                try:
                    bp._last_value = self.peek(bp.signal)
                except Exception:
                    pass
        
        # Watchpoints on ports only
        for wp in self._watchpoints.values():
            if wp.enabled and not self._is_gate_signal(wp.signal):
                try:
                    wp._last_value = self.peek(wp.signal)
                except Exception:
                    pass
    
    def _is_gate_signal(self, signal: str) -> bool:
        """Check if a signal name refers to a gate."""
        if self.debug_info:
            return signal in self.debug_info.gates or signal.replace(".", "_") in self.debug_info.gates
        return "_" in signal and "." not in signal
    
    def _check_stop_conditions(self) -> Optional[StopInfo]:
        """Check breakpoints and watchpoints after a step."""
        # Check breakpoints
        for bp in list(self._breakpoints.values()):
            if not bp.enabled:
                continue
            
            try:
                is_gate = self._is_gate_signal(bp.signal)
                if is_gate:
                    current = self.peek_gate(bp.signal)
                    # For gates, get previous value from C-side saved state
                    previous = self.peek_gate_previous(bp.signal)
                else:
                    current = self.peek(bp.signal)
                    # For ports, we captured the value before step
                    previous = bp._last_value
            except Exception:
                continue
            
            triggered = False
            
            if bp.bp_type == BreakpointType.CHANGE:
                triggered = previous is not None and current != previous
            elif bp.bp_type == BreakpointType.VALUE:
                triggered = current == bp.value
            elif bp.bp_type == BreakpointType.RISING:
                triggered = previous == 0 and current == 1
            elif bp.bp_type == BreakpointType.FALLING:
                triggered = previous == 1 and current == 0
            elif bp.bp_type == BreakpointType.CONDITION:
                # TODO: Implement condition evaluation
                pass
            
            if triggered:
                bp.hit_count += 1
                stop_info = StopInfo(
                    reason=StopReason.BREAKPOINT,
                    cycle=self._cycle,
                    breakpoint=bp,
                    signal=bp.signal,
                    old_value=previous,
                    new_value=current,
                    message=f"Breakpoint {bp.id} hit: {bp.signal} changed {previous} -> {current}"
                )
                
                if bp.temporary:
                    self.remove_breakpoint(bp.id)
                
                return stop_info
        
        # Check watchpoints
        for wp in self._watchpoints.values():
            if not wp.enabled:
                continue
            
            try:
                is_gate = self._is_gate_signal(wp.signal)
                if is_gate:
                    current = self.peek_gate(wp.signal)
                    previous = self.peek_gate_previous(wp.signal)
                else:
                    current = self.peek(wp.signal)
                    previous = wp._last_value
            except Exception:
                continue
            
            if previous is not None and current != previous:
                wp.hit_count += 1
                return StopInfo(
                    reason=StopReason.WATCHPOINT,
                    cycle=self._cycle,
                    watchpoint=wp,
                    signal=wp.signal,
                    old_value=previous,
                    new_value=current,
                    message=f"Watchpoint {wp.id} hit: {wp.signal} changed {previous} -> {current}"
                )
        
        return None
    
    def _get_all_signal_values(self) -> dict[str, int]:
        """Get values of all trackable signals (for stability detection)."""
        result = {}
        result.update(self.get_all_inputs())
        result.update(self.get_all_outputs())
        return result
    
    # =========================================================================
    # Context Manager
    # =========================================================================
    
    def __enter__(self) -> "DebugController":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass  # Library cleanup handled by ctypes
    
    def __repr__(self) -> str:
        name = self.debug_info.component if self.debug_info else "unknown"
        return f"DebugController({name}, cycle={self.cycle})"
