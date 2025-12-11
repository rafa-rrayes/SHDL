---
sidebar_position: 1
---

# SHDB Overview

**SHDB** (Simple Hardware Debugger) is an interactive debugger for SHDL circuits, inspired by GDB. It allows you to step through simulations, inspect any signal including internal gates, set breakpoints, record waveforms, and navigate component hierarchies.

## Key Features

- **Step-by-step simulation** - Advance one cycle at a time or run until breakpoints
- **Signal inspection** - Read any signal: inputs, outputs, and **internal gates**
- **Breakpoints & watchpoints** - Pause on signal changes or specific values
- **Waveform recording** - Record and export signal traces (VCD, JSON)
- **Hierarchy navigation** - Debug at any abstraction level
- **Source mapping** - Connect flattened gates back to original SHDL source
- **Python integration** - Script your debug sessions

## GDB Comparison

If you're familiar with GDB, you'll feel right at home:

| GDB Feature | SHDB Equivalent |
|-------------|-----------------|
| `break` on line | `break` on signal change |
| `watch` variable | `watch` signal value |
| `step` one instruction | `step` one clock cycle |
| `print` variable | `print` signal or gate output |
| `backtrace` | `hierarchy` - show instance path |
| `info locals` | `info signals` - show all signals |
| Source-level debugging | SHDL source mapping |
| Assembly-level debugging | Base SHDL / gate-level inspection |

## Quick Example

```bash
$ shdb adder16.shdl
SHDB - Simple Hardware Debugger v1.0
Loaded: Adder16 (356 gates)

(shdb) set A = 42
(shdb) set B = 17
(shdb) step
(shdb) print Sum
Sum = 59 (0x003B)

(shdb) print fa1.x1.O       # Internal gate!
fa1.x1.O = 1

(shdb) break Cout           # Break on carry out
Breakpoint 1: Cout (any change)

(shdb) set A = 0xFFFF
(shdb) set B = 1
(shdb) step
Breakpoint 1 hit: Cout changed 0 -> 1
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         SHDB Debugger                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌───────────────┐  ┌───────────────────────┐ │
│  │ CLI REPL    │  │ Python API    │  │ Scripting Engine      │ │
│  │ (readline)  │  │ (shdb module) │  │ (.shdb scripts)       │ │
│  └──────┬──────┘  └───────┬───────┘  └───────────┬───────────┘ │
│         └────────────────┼──────────────────────┘              │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    Debug Controller                        │ │
│  │  - Breakpoint/watchpoint management                       │ │
│  │  - Stepping logic                                         │ │
│  └───────────────────────┬───────────────────────────────────┘ │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                   Debug Info Manager                       │ │
│  │  - Source mapping (.shdl → gates)                         │ │
│  │  - Symbol table (signals, instances, hierarchy)           │ │
│  └───────────────────────┬───────────────────────────────────┘ │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                  Simulation Backend                        │ │
│  │  - Extended C library with gate-level peek                │ │
│  │  - Waveform recording buffer                              │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Debug vs Release Builds

SHDB requires a **debug build** of your circuit. Debug builds include:

- **Gate name table** - Maps gate names to their locations
- **`peek_gate()` function** - Read any internal gate output
- **Cycle counter** - Track simulation time
- **`.shdb` file** - JSON metadata with hierarchy and source mapping

```bash
# Release build (default) - optimized, no debug features
shdlc adder16.shdl -c -o libadder16.dylib

# Debug build - includes introspection
shdlc -g adder16.shdl -c -o libadder16.dylib
# Produces: libadder16.dylib + libadder16.shdb
```

## Next Steps

- [Getting Started](./getting-started) - Install and run SHDB
- [Commands Reference](./commands) - Complete command list
- [Breakpoints](./breakpoints) - Set breakpoints and watchpoints
- [Waveforms](./waveforms) - Record and export signal traces
- [Python API](./python-api) - Script your debugging sessions
