"""
High-Level Circuit API for SHDB

Provides a user-friendly interface for debugging SHDL circuits,
matching the documented shdb.Circuit API.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any, Iterator
import tempfile
import os

from .debuginfo import DebugInfo, PortInfo as DebugPortInfo, GateInfo as DebugGateInfo
from .controller import (
    DebugController, 
    StopReason, 
    StopInfo, 
    Breakpoint as ControllerBreakpoint,
    Watchpoint as ControllerWatchpoint,
    BreakpointType,
)
from .symbols import SignalRef, SignalType


@dataclass
class PortInfo:
    """Information about a circuit port."""
    name: str
    width: int
    
    @classmethod
    def from_debug_info(cls, port: DebugPortInfo) -> "PortInfo":
        return cls(name=port.name, width=port.width)


@dataclass
class GateInfo:
    """Information about a gate, including its current output value."""
    name: str
    type: str
    output: int
    hierarchy: str
    source_file: str = ""
    source_line: int = 0
    
    @classmethod
    def from_debug_info(cls, gate: DebugGateInfo, output: int = 0) -> "GateInfo":
        return cls(
            name=gate.name,
            type=gate.gate_type,
            output=output,
            hierarchy=gate.hierarchy_path,
            source_file=gate.source.file if gate.source else "",
            source_line=gate.source.line if gate.source else 0,
        )


@dataclass
class SourceLocation:
    """A location in source code."""
    file: str
    line: int
    column: int = 0
    
    def __str__(self) -> str:
        if self.column:
            return f"{self.file}:{self.line}:{self.column}"
        return f"{self.file}:{self.line}"


@dataclass
class StopResult:
    """Result of a continue or run operation."""
    stopped: bool
    cycle: int
    reason: str
    signal: str = ""
    old_value: int = 0
    new_value: int = 0
    
    @classmethod
    def from_stop_info(cls, info: StopInfo) -> "StopResult":
        reason_map = {
            StopReason.NONE: "none",
            StopReason.STEP: "step",
            StopReason.BREAKPOINT: "breakpoint",
            StopReason.WATCHPOINT: "watchpoint",
            StopReason.ERROR: "error",
            StopReason.USER_INTERRUPT: "interrupt",
        }
        return cls(
            stopped=info.reason not in (StopReason.NONE, StopReason.STEP),
            cycle=info.cycle,
            reason=reason_map.get(info.reason, "unknown"),
            signal=info.signal or "",
            old_value=info.old_value or 0,
            new_value=info.new_value or 0,
        )


@dataclass
class WaveformSample:
    """A single waveform sample."""
    cycle: int
    values: dict[str, int] = field(default_factory=dict)
    
    def __getitem__(self, signal: str) -> int:
        return self.values.get(signal, 0)


class Breakpoint:
    """A breakpoint handle for the Circuit API."""
    
    def __init__(self, circuit: "Circuit", bp: ControllerBreakpoint):
        self._circuit = circuit
        self._bp = bp
    
    @property
    def id(self) -> int:
        return self._bp.id
    
    @property
    def signal(self) -> str:
        return self._bp.signal
    
    @property
    def enabled(self) -> bool:
        return self._bp.enabled
    
    @property
    def hit_count(self) -> int:
        return self._bp.hit_count
    
    def enable(self) -> None:
        """Enable this breakpoint."""
        self._circuit._controller.enable_breakpoint(self._bp.id)
    
    def disable(self) -> None:
        """Disable this breakpoint."""
        self._circuit._controller.disable_breakpoint(self._bp.id)
    
    def delete(self) -> None:
        """Delete this breakpoint."""
        self._circuit._controller.remove_breakpoint(self._bp.id)
    
    def __str__(self) -> str:
        return str(self._bp)


class Watchpoint:
    """A watchpoint handle for the Circuit API."""
    
    def __init__(self, circuit: "Circuit", wp: ControllerWatchpoint):
        self._circuit = circuit
        self._wp = wp
    
    @property
    def id(self) -> int:
        return self._wp.id
    
    @property
    def signal(self) -> str:
        return self._wp.signal
    
    @property
    def enabled(self) -> bool:
        return self._wp.enabled
    
    @property
    def hit_count(self) -> int:
        return self._wp.hit_count
    
    def delete(self) -> None:
        """Delete this watchpoint."""
        self._circuit._controller.remove_watchpoint(self._wp.id)
    
    def __str__(self) -> str:
        return str(self._wp)


# Type for watch callbacks: signal, old_value, new_value -> should_continue
WatchCallback = Callable[[str, int, int], bool]


class Circuit:
    """
    High-level interface for debugging SHDL circuits.
    
    Example usage:
    
        with Circuit("adder16.shdl") as c:
            c.poke("A", 42)
            c.poke("B", 17)
            c.step()
            print(c.peek("Sum"))  # 59
    
    Can be loaded from:
    - SHDL source file (compiles automatically with -g)
    - Pre-compiled library + debug info file
    """
    
    def __init__(
        self,
        source: Optional[str | Path] = None,
        *,
        library: Optional[str | Path] = None,
        debug_info: Optional[str | Path] = None,
    ):
        """
        Load a circuit for debugging.
        
        Args:
            source: Path to .shdl source file (will compile with -g)
            library: Path to pre-compiled .dylib/.so library
            debug_info: Path to .shdb debug info file
        """
        self._controller: Optional[DebugController] = None
        self._debug_info: Optional[DebugInfo] = None
        self._temp_files: list[Path] = []
        self._source_path: Optional[Path] = None
        
        # Waveform recording
        self._recording: bool = False
        self._recorded_signals: list[str] = []
        self._waveform_data: list[WaveformSample] = []
        
        # Scope management
        self._current_scope: list[str] = []
        
        if source:
            self._load_from_source(Path(source))
        elif library:
            self._load_from_library(Path(library), Path(debug_info) if debug_info else None)
        else:
            raise ValueError("Must provide either source or library")
    
    def _load_from_source(self, source_path: Path) -> None:
        """Compile SHDL source and load the result."""
        from SHDL.compiler import SHDLCompiler
        from SHDL import Flattener
        
        self._source_path = source_path.absolute()
        
        # Create temp directory for compiled files
        temp_dir = Path(tempfile.mkdtemp(prefix="shdb_"))
        lib_name = source_path.stem
        
        # Determine library extension
        import platform
        ext = ".dylib" if platform.system() == "Darwin" else ".so"
        lib_path = temp_dir / f"lib{lib_name}{ext}"
        
        # Flatten the source first
        flattener = Flattener(search_paths=[str(source_path.parent)])
        flattener.load_file(str(source_path))
        
        # Get the last component
        components = list(flattener._library.components.keys())
        if not components:
            raise ValueError(f"No components found in {source_path}")
        comp_name = components[-1]
        
        base_shdl = flattener.flatten_to_base_shdl(comp_name)
        
        # Compile with debug info
        compiler = SHDLCompiler()
        result = compiler.compile_to_library_debug(
            base_shdl,
            str(lib_path),
            component_name=comp_name,
            source_path=str(source_path),
            debug_level=2,
            generate_shdb=True,
        )
        
        if not result.success:
            errors = "\n".join(result.errors)
            raise RuntimeError(f"Compilation failed:\n{errors}")
        
        self._temp_files.append(lib_path)
        
        # Load debug info
        shdb_path = Path(str(lib_path).rsplit(".", 1)[0] + ".shdb")
        if shdb_path.exists():
            self._debug_info = DebugInfo.load(shdb_path)
            self._temp_files.append(shdb_path)
        
        # Create controller
        self._controller = DebugController(
            lib_path,
            debug_info=self._debug_info,
            source_paths=[source_path.parent],
        )
    
    def _load_from_library(self, lib_path: Path, debug_path: Optional[Path] = None) -> None:
        """Load from pre-compiled library."""
        if not lib_path.exists():
            raise FileNotFoundError(f"Library not found: {lib_path}")
        
        # Auto-detect debug info path
        if debug_path is None:
            stem = str(lib_path).rsplit(".", 1)[0]
            debug_path = Path(stem + ".shdb")
        
        # Load debug info if available
        if debug_path.exists():
            self._debug_info = DebugInfo.load(debug_path)
        
        # Create controller
        self._controller = DebugController(
            lib_path,
            debug_info=self._debug_info,
        )
    
    def close(self) -> None:
        """Clean up resources."""
        self._controller = None
        
        # Clean up temp files
        for path in self._temp_files:
            try:
                path.unlink()
            except OSError:
                pass
        self._temp_files.clear()
    
    def __enter__(self) -> "Circuit":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def cycle(self) -> int:
        """Current simulation cycle."""
        return self._controller.cycle if self._controller else 0
    
    @property
    def inputs(self) -> list[PortInfo]:
        """List of input ports."""
        if not self._debug_info:
            return []
        return [PortInfo.from_debug_info(p) for p in self._debug_info.inputs]
    
    @property
    def outputs(self) -> list[PortInfo]:
        """List of output ports."""
        if not self._debug_info:
            return []
        return [PortInfo.from_debug_info(p) for p in self._debug_info.outputs]
    
    @property
    def current_scope(self) -> str:
        """Current hierarchy scope."""
        if not self._debug_info:
            return ""
        if not self._current_scope:
            return self._debug_info.component
        return "/".join([self._debug_info.component] + self._current_scope)
    
    @property
    def component_name(self) -> str:
        """Name of the loaded component."""
        if self._debug_info:
            return self._debug_info.component
        return "unknown"
    
    @property
    def num_gates(self) -> int:
        """Total number of gates."""
        if self._debug_info:
            return self._debug_info.num_gates
        return 0
    
    # =========================================================================
    # Simulation Control
    # =========================================================================
    
    def reset(self) -> None:
        """Reset the circuit to initial state."""
        if self._controller:
            self._controller.reset()
    
    def step(self, cycles: int = 1) -> None:
        """Advance simulation by N cycles."""
        if not self._controller:
            return
        
        for _ in range(cycles):
            self._controller.step(1)
            
            # Record waveform if active
            if self._recording and self._recorded_signals:
                sample = WaveformSample(cycle=self._controller.cycle)
                for sig in self._recorded_signals:
                    try:
                        sample.values[sig] = self.peek(sig)
                    except Exception:
                        pass
                self._waveform_data.append(sample)
    
    def poke(self, signal: str, value: int) -> None:
        """Set an input signal value."""
        if self._controller:
            self._controller.poke(signal, value)
    
    def peek(self, signal: str) -> int:
        """Read a signal value."""
        if not self._controller:
            return 0
        return self._controller.peek(signal)
    
    def poke_bits(self, signal: str, start: int, end: int, value: int) -> None:
        """Set a range of bits in a signal (1-indexed, inclusive)."""
        current = self.peek(signal)
        width = end - start + 1
        mask = ((1 << width) - 1) << (start - 1)
        new_value = (current & ~mask) | ((value << (start - 1)) & mask)
        self.poke(signal, new_value)
    
    def peek_bit(self, signal: str, bit: int) -> int:
        """Read a single bit from a signal (1-indexed)."""
        value = self.peek(signal)
        return (value >> (bit - 1)) & 1
    
    def peek_bits(self, signal: str, start: int, end: int) -> int:
        """Read a range of bits from a signal (1-indexed, inclusive)."""
        value = self.peek(signal)
        width = end - start + 1
        mask = (1 << width) - 1
        return (value >> (start - 1)) & mask
    
    # =========================================================================
    # Gate Access
    # =========================================================================
    
    def peek_gate(self, name: str) -> int:
        """Read a gate output value."""
        if not self._controller:
            return 0
        # Handle hierarchical names (convert . to _)
        flat_name = name.replace(".", "_")
        return self._controller.peek_gate(flat_name)
    
    def get_gate(self, name: str) -> Optional[GateInfo]:
        """Get gate information including current output."""
        if not self._debug_info:
            return None
        
        # Handle hierarchical names
        flat_name = name.replace(".", "_")
        gate = self._debug_info.get_gate(flat_name)
        if not gate:
            return None
        
        output = 0
        try:
            output = self.peek_gate(flat_name)
        except Exception:
            pass
        
        return GateInfo.from_debug_info(gate, output)
    
    def gates(
        self, 
        pattern: str = "*", 
        *, 
        type: Optional[str] = None
    ) -> Iterator[GateInfo]:
        """
        Iterate over gates matching a pattern.
        
        Args:
            pattern: Glob pattern to match gate names
            type: Filter by gate type (AND, OR, XOR, NOT, etc.)
        """
        if not self._debug_info:
            return
        
        for gate in self._debug_info.get_gates_by_pattern(pattern):
            if type and gate.gate_type != type:
                continue
            
            output = 0
            try:
                output = self.peek_gate(gate.name)
            except Exception:
                pass
            
            yield GateInfo.from_debug_info(gate, output)
    
    # =========================================================================
    # Breakpoints and Watchpoints
    # =========================================================================
    
    def breakpoint(
        self, 
        signal: str, 
        *, 
        condition: Optional[str] = None
    ) -> Breakpoint:
        """
        Set a breakpoint on a signal.
        
        Args:
            signal: Signal name to break on
            condition: Optional condition expression (e.g., "Sum > 255")
        
        Returns:
            Breakpoint handle for managing the breakpoint
        """
        if not self._controller:
            raise RuntimeError("No circuit loaded")
        
        bp_type = BreakpointType.CHANGE
        value = None
        
        # Parse condition if provided
        if condition:
            bp_type = BreakpointType.CONDITION
            # Simple equality check: "signal == value"
            if "==" in condition:
                parts = condition.split("==")
                if len(parts) == 2:
                    try:
                        value = int(parts[1].strip(), 0)
                        bp_type = BreakpointType.VALUE
                    except ValueError:
                        pass
        
        bp = self._controller.add_breakpoint(
            signal,
            bp_type=bp_type,
            value=value,
            condition=condition,
        )
        return Breakpoint(self, bp)
    
    def watchpoint(
        self, 
        signal: str, 
        *, 
        condition: Optional[str] = None
    ) -> Watchpoint:
        """
        Set a watchpoint on a signal.
        
        Args:
            signal: Signal name to watch
            condition: Reserved for future use
        
        Returns:
            Watchpoint handle
        """
        if not self._controller:
            raise RuntimeError("No circuit loaded")
        
        wp = self._controller.add_watchpoint(signal)
        return Watchpoint(self, wp)
    
    def watch(self, signal: str, callback: WatchCallback) -> None:
        """
        Watch a signal with a callback.
        
        The callback is called on each change with (signal, old_value, new_value).
        Return True to continue, False to stop.
        """
        if not self._controller:
            return
        
        # Add a watchpoint
        self._controller.add_watchpoint(signal)
        # Store callback for run()
        if not hasattr(self, "_watch_callbacks"):
            self._watch_callbacks: dict[str, WatchCallback] = {}
        self._watch_callbacks[signal] = callback
    
    def clear_breakpoints(self) -> None:
        """Clear all breakpoints."""
        if self._controller:
            self._controller.clear_breakpoints()
    
    def clear_watchpoints(self) -> None:
        """Clear all watchpoints."""
        if self._controller:
            self._controller.clear_watchpoints()
    
    def continue_(self, max_cycles: int = 1000000) -> StopResult:
        """
        Continue execution until a breakpoint/watchpoint triggers.
        
        Note: Named continue_ because 'continue' is a Python keyword.
        """
        if not self._controller:
            return StopResult(stopped=False, cycle=0, reason="no circuit")
        
        info = self._controller.continue_until_breakpoint(max_cycles)
        return StopResult.from_stop_info(info)
    
    def run(self, max_cycles: int = 1000000) -> StopResult:
        """
        Run until a breakpoint, watchpoint, or callback returns False.
        """
        if not self._controller:
            return StopResult(stopped=False, cycle=0, reason="no circuit")
        
        for _ in range(max_cycles):
            info = self._controller.step(1)
            
            if self._recording and self._recorded_signals:
                sample = WaveformSample(cycle=self._controller.cycle)
                for sig in self._recorded_signals:
                    try:
                        sample.values[sig] = self.peek(sig)
                    except Exception:
                        pass
                self._waveform_data.append(sample)
            
            if info.reason == StopReason.BREAKPOINT:
                return StopResult.from_stop_info(info)
            
            if info.reason == StopReason.WATCHPOINT:
                # Check callback
                callbacks = getattr(self, "_watch_callbacks", {})
                if info.signal and info.signal in callbacks:
                    cb = callbacks[info.signal]
                    if not cb(info.signal, info.old_value or 0, info.new_value or 0):
                        return StopResult.from_stop_info(info)
                else:
                    return StopResult.from_stop_info(info)
        
        return StopResult(
            stopped=False,
            cycle=self._controller.cycle,
            reason="max_cycles",
        )
    
    def finish(self, max_cycles: int = 1000) -> StopResult:
        """Run until signals stabilize (for combinational settling)."""
        if not self._controller:
            return StopResult(stopped=False, cycle=0, reason="no circuit")
        
        info = self._controller.finish(max_cycles)
        return StopResult.from_stop_info(info)
    
    # =========================================================================
    # Hierarchy Navigation
    # =========================================================================
    
    def scope(self, path: str) -> bool:
        """
        Change the current scope.
        
        Args:
            path: Scope path. Use ".." to go up, "/" to go to root,
                  or an instance name to descend.
        
        Returns:
            True if scope change was successful
        """
        if not self._controller or not self._controller.symbols:
            return False
        
        if path == "/":
            self._controller.symbols.reset_scope()
            self._current_scope.clear()
            return True
        elif path == "..":
            if self._controller.symbols.exit_scope():
                if self._current_scope:
                    self._current_scope.pop()
                return True
            return False
        else:
            if self._controller.symbols.enter_scope(path):
                self._current_scope.append(path)
                return True
            return False
    
    def instances(self) -> list[Any]:
        """Get instances in the current scope."""
        if not self._debug_info:
            return []
        # Return hierarchy info
        result = []
        for node in self._debug_info.hierarchy.values():
            for name, inst in node.instances.items():
                result.append(inst)
        return result
    
    # =========================================================================
    # Source Mapping
    # =========================================================================
    
    def gates_from_line(self, file: str, line: int) -> list[str]:
        """Get gate names that originated from a source line."""
        if not self._debug_info:
            return []
        return self._debug_info.get_gates_at_line(file, line)
    
    def source_location(self, gate: str) -> Optional[SourceLocation]:
        """Get the source location for a gate."""
        if not self._debug_info:
            return None
        
        flat_name = gate.replace(".", "_")
        gate_info = self._debug_info.get_gate(flat_name)
        if gate_info and gate_info.source:
            return SourceLocation(
                file=gate_info.source.file,
                line=gate_info.source.line,
                column=gate_info.source.column,
            )
        return None
    
    # =========================================================================
    # Waveform Recording
    # =========================================================================
    
    def record_signals(self, signals: list[str]) -> None:
        """Set which signals to record."""
        self._recorded_signals = list(signals)
    
    def record_start(self) -> None:
        """Start recording waveforms."""
        self._recording = True
        self._waveform_data.clear()
    
    def record_stop(self) -> None:
        """Stop recording waveforms."""
        self._recording = False
    
    def record_data(self) -> list[WaveformSample]:
        """Get recorded waveform data."""
        return list(self._waveform_data)
    
    def record_signal(self, name: str) -> list[int]:
        """Get recorded values for a specific signal."""
        return [sample.values.get(name, 0) for sample in self._waveform_data]
    
    def record_export(self, path: str | Path) -> None:
        """
        Export recorded waveforms.
        
        Supported formats: .vcd, .json, .csv
        """
        path = Path(path)
        suffix = path.suffix.lower()
        
        if suffix == ".json":
            self._export_json(path)
        elif suffix == ".csv":
            self._export_csv(path)
        elif suffix == ".vcd":
            self._export_vcd(path)
        else:
            raise ValueError(f"Unknown export format: {suffix}")
    
    def _export_json(self, path: Path) -> None:
        """Export waveforms as JSON."""
        import json
        data = {
            "signals": self._recorded_signals,
            "samples": [
                {"cycle": s.cycle, "values": s.values}
                for s in self._waveform_data
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _export_csv(self, path: Path) -> None:
        """Export waveforms as CSV."""
        with open(path, "w") as f:
            # Header
            f.write("cycle," + ",".join(self._recorded_signals) + "\n")
            # Data
            for sample in self._waveform_data:
                values = [str(sample.values.get(s, 0)) for s in self._recorded_signals]
                f.write(f"{sample.cycle}," + ",".join(values) + "\n")
    
    def _export_vcd(self, path: Path) -> None:
        """Export waveforms as VCD (Value Change Dump)."""
        from datetime import datetime
        
        with open(path, "w") as f:
            # VCD Header
            f.write(f"$date\n  {datetime.now().isoformat()}\n$end\n")
            f.write("$version\n  SHDB 1.0\n$end\n")
            f.write("$timescale 1ns $end\n")
            
            # Define variables
            f.write("$scope module circuit $end\n")
            var_ids = {}
            for i, sig in enumerate(self._recorded_signals):
                var_id = chr(ord('!') + i)  # Use ASCII chars as identifiers
                var_ids[sig] = var_id
                # Determine width
                width = 1
                if self._debug_info:
                    port = self._debug_info.get_port(sig)
                    if port:
                        width = port.width
                f.write(f"$var wire {width} {var_id} {sig} $end\n")
            f.write("$upscope $end\n")
            f.write("$enddefinitions $end\n")
            
            # Initial values
            f.write("#0\n")
            for sig in self._recorded_signals:
                if self._waveform_data:
                    val = self._waveform_data[0].values.get(sig, 0)
                    f.write(f"b{val:b} {var_ids[sig]}\n")
            
            # Value changes
            prev_values: dict[str, int] = {}
            for sample in self._waveform_data:
                changes = []
                for sig in self._recorded_signals:
                    val = sample.values.get(sig, 0)
                    if sig not in prev_values or prev_values[sig] != val:
                        changes.append((sig, val))
                        prev_values[sig] = val
                
                if changes:
                    f.write(f"#{sample.cycle}\n")
                    for sig, val in changes:
                        f.write(f"b{val:b} {var_ids[sig]}\n")
    
    # =========================================================================
    # String Representation
    # =========================================================================
    
    def __repr__(self) -> str:
        name = self.component_name
        return f"Circuit({name}, cycle={self.cycle}, gates={self.num_gates})"
