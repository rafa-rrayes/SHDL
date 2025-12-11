---
sidebar_position: 2
---

# Getting Started with SHDB

This guide walks you through your first debugging session with SHDB.

## Prerequisites

Make sure you have SHDL installed:

```bash
pip install shdl
# or
uv add shdl
```

## Creating a Debug Build

SHDB requires circuits compiled with debug information. Use the `-g` flag:

```bash
# Compile with debug info
shdlc -g myCircuit.shdl -c -o libmyCircuit.dylib
```

This produces two files:
- `libmyCircuit.dylib` - The shared library with debug functions
- `libmyCircuit.shdb` - JSON file with debug metadata

### Debug Levels

| Flag | Description |
|------|-------------|
| `-g` | Standard debug info (equivalent to `-g2`) |
| `-g1` | Minimal: gate names and types only |
| `-g2` | Standard: hierarchy + source lines |
| `-g3` | Full: all connections, constants, complete source map |

```bash
# Full debug info
shdlc -g3 myCircuit.shdl -c -o libmyCircuit.dylib
```

### Skipping the .shdb File

If you only need gate inspection without the metadata file:

```bash
shdlc -g --no-shdb myCircuit.shdl -c -o libmyCircuit.dylib
```

## Starting SHDB

### From a Compiled Library

```bash
shdb libmyCircuit.dylib
```

SHDB automatically looks for `libmyCircuit.shdb` in the same directory.

### from SHDL Source

Compile and debug in one step:

```bash
shdb myCircuit.shdl
```

SHDB compiles with `-g` automatically and loads the result.

### Specifying the Debug Info File

```bash
shdb libmyCircuit.dylib -d /path/to/myCircuit.shdb
```

## The SHDB Prompt

When SHDB starts, you'll see:

```
SHDB - Simple Hardware Debugger v1.0
Type 'help' for available commands.

Loaded: Adder16 (356 gates)
  Inputs:  A[16], B[16], Cin
  Outputs: Sum[16], Cout

(shdb) █
```

The prompt shows:
- Component name and gate count
- Input and output ports with their widths

## Your First Session

Let's debug a 16-bit adder:

### 1. Set Input Values

```
(shdb) set A = 42
(shdb) set B = 17
```

### 2. Advance Simulation

```
(shdb) step
```

This runs one clock cycle, allowing signals to propagate.

### 3. Read Outputs

```
(shdb) print Sum
Sum = 59 (0x003B)

(shdb) print Cout
Cout = 0
```

### 4. Inspect Internal Gates

This is where debug builds shine - you can see inside the circuit:

```
(shdb) print fa1.x1.O
fa1.x1.O = 1

(shdb) info gates fa1*
Gates matching 'fa1*':
  fa1_x1: XOR, output=1
  fa1_x2: XOR, output=1
  fa1_a1: AND, output=0
  fa1_a2: AND, output=1
  fa1_o1: OR,  output=1
```

### 5. Set a Breakpoint

```
(shdb) break Cout
Breakpoint 1: Cout (any change)

(shdb) set A = 0xFFFF
(shdb) set B = 1
(shdb) continue

Breakpoint 1 hit: Cout changed 0 -> 1
Cycle: 2
```

### 6. View Hierarchy

```
(shdb) hierarchy
Adder16
├── fa1: FullAdder
│   ├── x1: XOR
│   ├── x2: XOR
│   ├── a1: AND
│   ├── a2: AND
│   └── o1: OR
├── fa2: FullAdder
└── ... (14 more instances)
```

### 7. Exit

```
(shdb) quit
Goodbye.
```

## Command Shortcuts

SHDB supports GDB-style short forms:

| Short | Command |
|-------|---------|
| `s` | `step` |
| `c` | `continue` |
| `p` | `print` |
| `b` | `break` |
| `w` | `watch` |
| `d` | `delete` |
| `i` | `info` |
| `h` | `help` |
| `q` | `quit` |

## Tab Completion

Press `Tab` to complete:
- Command names
- Signal names
- Gate names
- Instance paths

```
(shdb) print fa<Tab>
fa1   fa2   fa3   fa4   ...

(shdb) print fa1.<Tab>
fa1.A    fa1.B    fa1.Cin    fa1.Sum    fa1.Cout    fa1.x1    fa1.x2    ...
```

## Command History

- `Up/Down` arrows to navigate history
- `Ctrl+R` to search history
- `history` command to show all history

## Getting Help

```
(shdb) help
Available commands:
  reset, step, continue, finish, run, quit
  print, set, info
  break, tbreak, watch, awatch, rwatch
  delete, disable, enable, clear
  hierarchy, scope, where, list
  record, source, define
  python, help, history, shell, log

(shdb) help break
break SIGNAL [if CONDITION]
  Set a breakpoint on signal changes.
  
  Examples:
    break Cout            # Break on any change
    break Cout if Cout==1 # Break when Cout becomes 1
    break fa1.x1.O        # Break on internal gate
```

## Next Steps

- [Commands Reference](./commands) - All available commands
- [Signal Inspection](./inspection) - Print formats and expressions
- [Breakpoints](./breakpoints) - Advanced breakpoint techniques
