#!/usr/bin/env python3
"""
SHDB - Simple Hardware Debugger CLI

An interactive debugger for SHDL circuits, inspired by GDB.

Usage:
    shdb circuit.shdl              # Load from SHDL source
    shdb libcircuit.dylib          # Load from compiled library
    shdb libcircuit.dylib -d info.shdb  # Specify debug info file
"""

import argparse
import sys
import readline
import os
import re
from pathlib import Path
from typing import Optional, Callable

from .circuit import Circuit, StopResult, GateInfo, PortInfo
from .controller import BreakpointType


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    
    @classmethod
    def disable(cls):
        """Disable colors (for non-terminal output)."""
        cls.RESET = ""
        cls.BOLD = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.MAGENTA = ""
        cls.CYAN = ""


def colorize(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{color}{text}{Colors.RESET}"


class SHDB:
    """Interactive SHDB debugger session."""
    
    VERSION = "1.0.0"
    
    # Command aliases
    ALIASES = {
        "s": "step",
        "c": "continue",
        "p": "print",
        "b": "break",
        "d": "delete",
        "i": "info",
        "q": "quit",
        "h": "help",
        "?": "help",
        "run": "continue",
    }
    
    def __init__(self, circuit: Circuit):
        self.circuit = circuit
        self.running = True
        self._debugger_vars: dict[str, int] = {}
        self._last_command = ""
        self._print_format = "d"  # Default: decimal
        
        # Set up readline
        self._setup_readline()
    
    def _setup_readline(self) -> None:
        """Configure readline for command completion."""
        readline.set_completer(self._complete)
        readline.parse_and_bind("tab: complete")
        
        # Try to load history
        history_file = Path.home() / ".shdb_history"
        try:
            readline.read_history_file(history_file)
        except (FileNotFoundError, PermissionError, OSError):
            pass
        
        # Save history on exit
        import atexit
        def save_history():
            try:
                readline.write_history_file(history_file)
            except (PermissionError, OSError):
                pass
        atexit.register(save_history)
    
    def _complete(self, text: str, state: int) -> Optional[str]:
        """Tab completion for commands and signals."""
        if state == 0:
            line = readline.get_line_buffer()
            words = line.split()
            
            if len(words) <= 1:
                # Complete command names
                commands = [
                    "step", "continue", "reset", "quit", "help",
                    "print", "set", "break", "watch", "delete",
                    "enable", "disable", "clear", "info", "finish",
                    "scope", "hierarchy",
                ]
                self._completions = [c for c in commands if c.startswith(text)]
            else:
                # Complete signal names
                signals = []
                for port in self.circuit.inputs:
                    signals.append(port.name)
                for port in self.circuit.outputs:
                    signals.append(port.name)
                self._completions = [s for s in signals if s.startswith(text)]
        
        try:
            return self._completions[state]
        except IndexError:
            return None
    
    def run(self) -> None:
        """Run the interactive debugger loop."""
        self._print_banner()
        
        while self.running:
            try:
                prompt = f"{colorize('(shdb)', Colors.CYAN)} "
                line = input(prompt).strip()
                
                if not line:
                    # Repeat last command
                    if self._last_command:
                        line = self._last_command
                    else:
                        continue
                
                self._last_command = line
                self._execute(line)
                
            except EOFError:
                print()
                self.running = False
            except KeyboardInterrupt:
                print("\nInterrupted. Use 'quit' to exit.")
    
    def _print_banner(self) -> None:
        """Print the startup banner."""
        print(f"{Colors.BOLD}SHDB - Simple Hardware Debugger v{self.VERSION}{Colors.RESET}")
        print("Type 'help' for available commands.\n")
        
        c = self.circuit
        print(f"Loaded: {colorize(c.component_name, Colors.GREEN)} ({c.num_gates} gates)")
        
        if c.inputs:
            inputs_str = ", ".join(
                f"{p.name}[{p.width}]" if p.width > 1 else p.name 
                for p in c.inputs
            )
            print(f"  Inputs:  {inputs_str}")
        
        if c.outputs:
            outputs_str = ", ".join(
                f"{p.name}[{p.width}]" if p.width > 1 else p.name 
                for p in c.outputs
            )
            print(f"  Outputs: {outputs_str}")
        
        print()
    
    def _execute(self, line: str) -> None:
        """Execute a command line."""
        # Parse command and arguments
        parts = line.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Handle format specifier (e.g., print/x)
        if "/" in cmd:
            cmd, fmt = cmd.split("/", 1)
            self._print_format = fmt[0] if fmt else "d"
        
        # Resolve alias
        cmd = self.ALIASES.get(cmd, cmd)
        
        # Find handler
        handler = getattr(self, f"cmd_{cmd}", None)
        if handler:
            try:
                handler(args)
            except Exception as e:
                print(colorize(f"Error: {e}", Colors.RED))
        else:
            print(colorize(f"Unknown command: {cmd}", Colors.RED))
            print("Type 'help' for available commands.")
    
    # =========================================================================
    # Commands
    # =========================================================================
    
    def cmd_help(self, args: str) -> None:
        """Show help information."""
        if args:
            # Help for specific command
            handler = getattr(self, f"cmd_{args}", None)
            if handler and handler.__doc__:
                print(handler.__doc__)
            else:
                print(f"No help for: {args}")
            return
        
        print(f"""
{Colors.BOLD}Simulation Control{Colors.RESET}
  reset              Reset circuit to initial state
  step [N]           Advance N cycles (default: 1)
  continue, run      Run until breakpoint
  finish             Run until signals stabilize

{Colors.BOLD}Signal Inspection{Colors.RESET}
  print <signal>     Print signal value(s)
  print/x <signal>   Print in hexadecimal
  print/b <signal>   Print in binary
  set <signal> = N   Set input signal value

{Colors.BOLD}Breakpoints{Colors.RESET}
  break <signal>     Break on signal change
  break <sig> if <cond>  Conditional breakpoint
  watch <signal>     Watch for changes
  delete N           Delete breakpoint N
  enable/disable N   Enable/disable breakpoint N
  clear              Delete all breakpoints

{Colors.BOLD}Information{Colors.RESET}
  info signals       Show all signals
  info inputs        Show input ports
  info outputs       Show output ports
  info gates [pat]   Show gates (optional pattern)
  info breakpoints   Show breakpoints
  info watchpoints   Show watchpoints

{Colors.BOLD}Hierarchy{Colors.RESET}
  scope <path>       Change scope (use .. for up, / for root)
  hierarchy          Show component hierarchy

{Colors.BOLD}Other{Colors.RESET}
  quit               Exit debugger
  help [cmd]         Show help
""")
    
    def cmd_quit(self, args: str) -> None:
        """Exit the debugger."""
        self.running = False
        print("Goodbye.")
    
    def cmd_reset(self, args: str) -> None:
        """Reset the circuit to initial state."""
        self.circuit.reset()
        print(f"Circuit reset. Cycle: {self.circuit.cycle}")
    
    def cmd_step(self, args: str) -> None:
        """Advance simulation by N cycles (default: 1)."""
        n = int(args) if args else 1
        self.circuit.step(n)
        print(f"Cycle: {self.circuit.cycle}")
    
    def cmd_continue(self, args: str) -> None:
        """Run until a breakpoint triggers."""
        result = self.circuit.continue_()
        if result.stopped:
            print(f"{colorize('Breakpoint hit', Colors.YELLOW)}: {result.signal} "
                  f"changed {result.old_value} -> {result.new_value}")
        print(f"Cycle: {result.cycle}")
    
    def cmd_finish(self, args: str) -> None:
        """Run until signals stabilize."""
        result = self.circuit.finish()
        print(f"Cycle: {result.cycle} - {result.reason}")
    
    def cmd_print(self, args: str) -> None:
        """Print signal values. Format: print [/x|/b|/d] <signal> [signal...]"""
        if not args:
            print("Usage: print <signal> [signal...]")
            return
        
        signals = args.split()
        
        for sig in signals:
            try:
                # Check for bit indexing
                match = re.match(r"(\w+)\[(\d+)(?::(\d+))?\]", sig)
                if match:
                    name, start, end = match.groups()
                    start = int(start)
                    if end:
                        value = self.circuit.peek_bits(name, start, int(end))
                    else:
                        value = self.circuit.peek_bit(name, start)
                else:
                    # Try as signal first (ports), then gate
                    try:
                        value = self.circuit.peek(sig)
                    except Exception:
                        value = self.circuit.peek_gate(sig)
                
                self._print_value(sig, value)
                
            except Exception as e:
                print(colorize(f"{sig}: {e}", Colors.RED))
    
    def _print_value(self, name: str, value: int) -> None:
        """Print a value in the current format."""
        if self._print_format == "x":
            print(f"{name} = {colorize(f'0x{value:04X}', Colors.GREEN)}")
        elif self._print_format == "b":
            print(f"{name} = {colorize(f'0b{value:016b}', Colors.GREEN)}")
        else:  # decimal
            hex_str = f"0x{value:04X}"
            print(f"{name} = {colorize(str(value), Colors.GREEN)} ({hex_str})")
    
    def cmd_set(self, args: str) -> None:
        """Set an input signal value. Format: set <signal> = <value>"""
        if "=" not in args:
            print("Usage: set <signal> = <value>")
            return
        
        parts = args.split("=", 1)
        signal = parts[0].strip()
        value_str = parts[1].strip()
        
        # Parse value (supports 0x, 0b prefixes)
        try:
            value = int(value_str, 0)
        except ValueError:
            print(colorize(f"Invalid value: {value_str}", Colors.RED))
            return
        
        # Check for bit indexing
        match = re.match(r"(\w+)\[(\d+)(?::(\d+))?\]", signal)
        if match:
            name, start, end = match.groups()
            start = int(start)
            if end:
                self.circuit.poke_bits(name, start, int(end), value)
            else:
                # Single bit
                current = self.circuit.peek(name)
                mask = 1 << (start - 1)
                new_value = (current & ~mask) | ((value & 1) << (start - 1))
                self.circuit.poke(name, new_value)
        else:
            self.circuit.poke(signal, value)
        
        # Confirm
        actual = self.circuit.peek(signal.split("[")[0])
        print(f"{signal.split('[')[0]} = {actual}")
    
    def cmd_break(self, args: str) -> None:
        """Set a breakpoint. Format: break <signal> [if <condition>]"""
        if not args:
            print("Usage: break <signal> [if <condition>]")
            return
        
        # Parse condition
        condition = None
        if " if " in args.lower():
            parts = re.split(r"\s+if\s+", args, flags=re.IGNORECASE)
            signal = parts[0].strip()
            condition = parts[1].strip() if len(parts) > 1 else None
        else:
            signal = args.strip()
        
        bp = self.circuit.breakpoint(signal, condition=condition)
        print(f"Breakpoint {bp.id}: {signal}" + 
              (f" if {condition}" if condition else " (any change)"))
    
    def cmd_watch(self, args: str) -> None:
        """Set a watchpoint. Format: watch <signal>"""
        if not args:
            print("Usage: watch <signal>")
            return
        
        wp = self.circuit.watchpoint(args.strip())
        print(f"Watchpoint {wp.id}: {args.strip()}")
    
    def cmd_delete(self, args: str) -> None:
        """Delete a breakpoint. Format: delete <N>"""
        if not args:
            print("Usage: delete <breakpoint-number>")
            return
        
        try:
            bp_id = int(args)
            if self.circuit._controller:
                if self.circuit._controller.remove_breakpoint(bp_id):
                    print(f"Deleted breakpoint {bp_id}")
                elif self.circuit._controller.remove_watchpoint(bp_id):
                    print(f"Deleted watchpoint {bp_id}")
                else:
                    print(colorize(f"No breakpoint/watchpoint {bp_id}", Colors.RED))
        except ValueError:
            print(colorize(f"Invalid number: {args}", Colors.RED))
    
    def cmd_enable(self, args: str) -> None:
        """Enable a breakpoint. Format: enable <N>"""
        if not args:
            print("Usage: enable <breakpoint-number>")
            return
        
        try:
            bp_id = int(args)
            if self.circuit._controller and self.circuit._controller.enable_breakpoint(bp_id):
                print(f"Enabled breakpoint {bp_id}")
            else:
                print(colorize(f"No breakpoint {bp_id}", Colors.RED))
        except ValueError:
            print(colorize(f"Invalid number: {args}", Colors.RED))
    
    def cmd_disable(self, args: str) -> None:
        """Disable a breakpoint. Format: disable <N>"""
        if not args:
            print("Usage: disable <breakpoint-number>")
            return
        
        try:
            bp_id = int(args)
            if self.circuit._controller and self.circuit._controller.disable_breakpoint(bp_id):
                print(f"Disabled breakpoint {bp_id}")
            else:
                print(colorize(f"No breakpoint {bp_id}", Colors.RED))
        except ValueError:
            print(colorize(f"Invalid number: {args}", Colors.RED))
    
    def cmd_clear(self, args: str) -> None:
        """Clear all breakpoints."""
        self.circuit.clear_breakpoints()
        self.circuit.clear_watchpoints()
        print("All breakpoints and watchpoints deleted.")
    
    def cmd_info(self, args: str) -> None:
        """Show information. Format: info <what>"""
        if not args:
            print("Usage: info signals|inputs|outputs|gates|breakpoints|watchpoints")
            return
        
        parts = args.split(None, 1)
        what = parts[0].lower()
        pattern = parts[1] if len(parts) > 1 else "*"
        
        if what in ("signals", "s"):
            self._info_signals()
        elif what in ("inputs", "i"):
            self._info_inputs()
        elif what in ("outputs", "o"):
            self._info_outputs()
        elif what in ("gates", "g"):
            self._info_gates(pattern)
        elif what in ("breakpoints", "b"):
            self._info_breakpoints()
        elif what in ("watchpoints", "w"):
            self._info_watchpoints()
        else:
            print(colorize(f"Unknown info type: {what}", Colors.RED))
    
    def _info_signals(self) -> None:
        """Show all signals."""
        self._info_inputs()
        print()
        self._info_outputs()
    
    def _info_inputs(self) -> None:
        """Show input ports."""
        print(f"{Colors.BOLD}Inputs:{Colors.RESET}")
        for port in self.circuit.inputs:
            value = self.circuit.peek(port.name)
            width_str = f"[{port.width}]" if port.width > 1 else ""
            print(f"  {port.name}{width_str} = {value} (0x{value:X})")
    
    def _info_outputs(self) -> None:
        """Show output ports."""
        print(f"{Colors.BOLD}Outputs:{Colors.RESET}")
        for port in self.circuit.outputs:
            value = self.circuit.peek(port.name)
            width_str = f"[{port.width}]" if port.width > 1 else ""
            print(f"  {port.name}{width_str} = {value} (0x{value:X})")
    
    def _info_gates(self, pattern: str) -> None:
        """Show gates matching pattern."""
        print(f"{Colors.BOLD}Gates ({pattern}):{Colors.RESET}")
        count = 0
        for gate in self.circuit.gates(pattern):
            print(f"  {gate.name}: {gate.type} = {gate.output}")
            count += 1
            if count >= 50:
                print(f"  ... (showing first 50)")
                break
        
        if count == 0:
            print("  (no gates match)")
    
    def _info_breakpoints(self) -> None:
        """Show breakpoints."""
        print(f"{Colors.BOLD}Breakpoints:{Colors.RESET}")
        if self.circuit._controller:
            bps = self.circuit._controller.get_breakpoints()
            if bps:
                for bp in bps:
                    print(f"  {bp}")
            else:
                print("  (none)")
        else:
            print("  (no controller)")
    
    def _info_watchpoints(self) -> None:
        """Show watchpoints."""
        print(f"{Colors.BOLD}Watchpoints:{Colors.RESET}")
        if self.circuit._controller:
            wps = self.circuit._controller.get_watchpoints()
            if wps:
                for wp in wps:
                    print(f"  {wp}")
            else:
                print("  (none)")
        else:
            print("  (no controller)")
    
    def cmd_scope(self, args: str) -> None:
        """Change scope. Format: scope <path>"""
        if not args:
            print(f"Current scope: {self.circuit.current_scope}")
            return
        
        if self.circuit.scope(args.strip()):
            print(f"Scope: {self.circuit.current_scope}")
        else:
            print(colorize(f"Invalid scope: {args}", Colors.RED))
    
    def cmd_hierarchy(self, args: str) -> None:
        """Show component hierarchy."""
        print(f"{Colors.BOLD}Hierarchy:{Colors.RESET}")
        print(f"  {self.circuit.component_name}")
        for inst in self.circuit.instances():
            print(f"    {inst.name}: {inst.component_type}")


def main():
    """Main entry point for shdb."""
    parser = argparse.ArgumentParser(
        prog="shdb",
        description="Simple Hardware Debugger - Interactive debugger for SHDL circuits",
        epilog="Example: shdb adder16.shdl"
    )
    
    parser.add_argument(
        "input",
        help="SHDL source file or compiled library (.shdl, .dylib, .so)"
    )
    
    parser.add_argument(
        "-d", "--debug-info",
        help="Path to .shdb debug info file (auto-detected if not specified)"
    )
    
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    
    parser.add_argument(
        "-c", "--command",
        action="append",
        default=[],
        help="Execute command(s) and exit"
    )
    
    parser.add_argument(
        "-x", "--script",
        help="Execute commands from script file"
    )
    
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"SHDB {SHDB.VERSION}"
    )
    
    args = parser.parse_args()
    
    # Handle colors
    if args.no_color or not sys.stdout.isatty():
        Colors.disable()
    
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Load circuit
        if input_path.suffix == ".shdl":
            circuit = Circuit(source=input_path)
        else:
            # Assume it's a library
            circuit = Circuit(
                library=input_path,
                debug_info=args.debug_info,
            )
        
        # Create debugger
        debugger = SHDB(circuit)
        
        # Execute script if provided
        if args.script:
            script_path = Path(args.script)
            if script_path.exists():
                with open(script_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            debugger._execute(line)
        
        # Execute command-line commands
        if args.command:
            for cmd in args.command:
                debugger._execute(cmd)
            # If commands were provided, exit unless interactive
            if not sys.stdin.isatty():
                sys.exit(0)
        
        # Run interactive loop
        debugger.run()
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'circuit' in locals():
            circuit.close()


if __name__ == "__main__":
    main()
