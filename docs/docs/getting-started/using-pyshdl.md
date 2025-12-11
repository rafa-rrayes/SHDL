---
sidebar_position: 3
---

# Using PySHDL

PySHDL is the Python library for working with SHDL circuits. This guide covers the Python API for simulating circuits.

## The SHDLCircuit Class

The main interface for simulation is the `SHDLCircuit` class:

```python
from SHDL import SHDLCircuit

# Load a circuit from a file
circuit = SHDLCircuit("myCircuit.shdl")

# Set inputs
circuit.poke("A", 42)
circuit.poke("B", 17)

# Advance simulation
circuit.step()

# Read outputs
result = circuit.peek("Sum")
print(result)

# Clean up
circuit.close()
```

## Context Manager (Recommended)

Use the context manager for automatic cleanup:

```python
from SHDL import SHDLCircuit

with SHDLCircuit("adder16.shdl") as circuit:
    circuit["A"] = 100
    circuit["B"] = 200
    circuit.step()
    print(circuit["Sum"])  # 300
# Automatically cleaned up here
```

## Dict-like Interface

For convenience, you can use dictionary syntax:

```python
# These are equivalent:
circuit.poke("A", 42)
circuit["A"] = 42

# These are equivalent:
value = circuit.peek("Sum")
value = circuit["Sum"]
```

## Circuit Information

Get information about the loaded circuit:

```python
with SHDLCircuit("adder16.shdl") as circuit:
    print(circuit.name)      # "Adder16"
    print(circuit.inputs)    # ["A", "B", "Cin"]
    print(circuit.outputs)   # ["Sum", "Cout"]
    
    # Detailed port info
    for port in circuit.info.inputs:
        print(f"{port.name}: {port.width} bits (max: {port.max_value})")
```

## Multi-bit Signals

SHDL supports multi-bit signals (vectors). Values are passed as integers:

```python
with SHDLCircuit("adder16.shdl") as circuit:
    # Set 16-bit values
    circuit["A"] = 0xFFFF  # 65535
    circuit["B"] = 0x0001  # 1
    circuit.step()
    
    # Read result (also 16 bits)
    print(circuit["Sum"])   # 0 (overflow)
    print(circuit["Cout"])  # 1 (carry out)
```

## Testing Circuits

Example of testing an 8-bit adder:

```python
from SHDL import SHDLCircuit
import random

def test_adder8():
    with SHDLCircuit("adder8.shdl") as adder:
        # Test 100 random additions
        for _ in range(100):
            a = random.randint(0, 255)
            b = random.randint(0, 255)
            
            adder["A"] = a
            adder["B"] = b
            adder["Cin"] = 0
            adder.step()
            
            expected_sum = (a + b) & 0xFF
            expected_cout = 1 if (a + b) > 255 else 0
            
            assert adder["Sum"] == expected_sum
            assert adder["Cout"] == expected_cout
        
        print("All tests passed!")

test_adder8()
```

## Compilation Pipeline

PySHDL compiles circuits through several stages:

```
┌─────────────────┐
│  Expanded SHDL  │  ← Your .shdl file
│  (generators,   │
│   imports, etc) │
└────────┬────────┘
         │ Flattener
         ▼
┌─────────────────┐
│    Base SHDL    │  ← Primitives only
│  (AND, OR, NOT, │
│   XOR, VCC, GND)│
└────────┬────────┘
         │ Compiler
         ▼
┌─────────────────┐
│    C Code       │  ← Generated C
└────────┬────────┘
         │ clang
         ▼
┌─────────────────┐
│ Shared Library  │  ← .dylib/.so/.dll
└────────┬────────┘
         │ ctypes
         ▼
┌─────────────────┐
│  SHDLCircuit    │  ← Python interface
└─────────────────┘
```

## Advanced Options

### Custom Include Paths

If your circuit imports from other files:

```python
circuit = SHDLCircuit(
    "cpu.shdl",
    include_paths=["./components", "./alu"]
)
```

### Selecting a Component

If a file has multiple components:

```python
circuit = SHDLCircuit(
    "components.shdl",
    component="FullAdder"  # Compile this specific component
)
```

### Keeping the Compiled Library

For debugging, keep the generated library:

```python
circuit = SHDLCircuit(
    "circuit.shdl",
    keep_library=True,
    library_dir="./build"
)
```

## Debugging with SHDB

For interactive debugging with breakpoints, signal inspection, and waveforms, see the [SHDB Debugger](/docs/debugger/overview) documentation.

Quick example:
```bash
# Compile with debug info
shdlc -g circuit.shdl -c -o libcircuit.dylib

# Start debugger
shdb libcircuit.dylib
```

## Error Handling

```python
from SHDL import SHDLCircuit, CompilationError, SimulationError

try:
    with SHDLCircuit("broken.shdl") as circuit:
        circuit.step()
except CompilationError as e:
    print(f"Failed to compile: {e}")
except SimulationError as e:
    print(f"Simulation error: {e}")
```

## Low-Level API

For more control, use the individual modules:

```python
from SHDL import parse_file, Flattener, format_base_shdl

# Parse SHDL file
module = parse_file("circuit.shdl")

# Flatten to Base SHDL
flattener = Flattener()
flattener.load_file("circuit.shdl")
base_shdl = flattener.flatten_to_base_shdl("MyComponent")

# Print the flattened result
print(format_base_shdl(base_shdl))
```
