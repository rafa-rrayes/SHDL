# SHDL Documentation

Complete documentation for the Simple Hardware Description Language (SHDL) and its Python library.

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [SHDL Language Reference](#shdl-language-reference)
   - [Lexical Elements](#lexical-elements)
   - [Component Structure](#component-structure)
   - [Data Types and Signals](#data-types-and-signals)
   - [Imports and Modules](#imports-and-modules)
   - [Instances and Connections](#instances-and-connections)
   - [Generators](#generators)
   - [Standard Gates](#standard-gates)
4. [Python API Reference](#python-api-reference)
   - [Circuit Class](#circuit-class)
5. [CLI Reference](#cli-reference)
6. [Examples](#examples)
   - [Language Examples](#language-examples)
   - [Python API Examples](#python-api-examples)
7. [Advanced Topics](#advanced-topics)
   - [Compilation Process](#compilation-process)
   - [Debugging](#debugging)
   - [Best Practices](#best-practices)

---

## Introduction

SHDL (Simple Hardware Description Language) is a lightweight HDL designed for creating digital circuits and easily simulating them. It compiles to C for fast execution and portability, providing a Python API for simulation and interaction.

### Key Features

- **Simplicity** - Minimal syntax for maximum clarity
- **Hierarchy** - Build complex circuits from simple components
- **Fast Simulation** - Compiled to native C code for performance
- **Python Integration** - Easy-to-use Python API for circuit interaction
- **Portability** - Cross-platform support

---

## Getting Started

### Installation

```bash
pip install SHDL
```

### Quick Example

Create a simple circuit file `halfAdder.shdl`:

```shdl
component HalfAdder(A, B) -> (Sum, Carry) {
    xor1: XOR;
    and1: AND;
    
    connect {
        A -> xor1.A;
        B -> xor1.B;
        A -> and1.A;
        B -> and1.B;
        xor1.O -> Sum;
        and1.O -> Carry;
    }
}
```

Use it in Python:

```python
from SHDL import Circuit

circuit = Circuit("halfAdder.shdl")
circuit.poke("A", 1)
circuit.poke("B", 1)
circuit.step(10)
print(f"Sum: {circuit.peek('Sum')}, Carry: {circuit.peek('Carry')}")
```

---

# SHDL Language Reference

## Lexical Elements

### Comments

```shdl
# This is a single-line comment
```

Comments begin with `#` and continue to the end of the line.

### Identifiers

Identifiers must:
- Start with a letter (a-z, A-Z)
- Contain only letters, digits, and underscores
- Be case-sensitive

Examples:
```shdl
validName
gate1
my_component
ALU_8bit
```

### Keywords

Reserved keywords:
- `component`
- `use`
- `connect`

### Operators

- `->` : Connection operator
- `::` : Module scope operator
- `{}` : Braces for grouping
- `[]` : Brackets for bit indexing and generators
- `:` : Instance type declaration
- `;` : Statement terminator
- `,` : Separator

## Component Structure

### Syntax

```shdl
component ComponentName(input_ports) -> (output_ports) {
    instance_declarations
    
    connect {
        connection_statements
    }
}
```

### Component Declaration

```shdl
component <name>(<inputs>) -> (<outputs>) { ... }
```

- **name**: Component identifier
- **inputs**: Comma-separated list of input ports
- **outputs**: Comma-separated list of output ports

### Example

```shdl
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    # Component body
}
```

## Data Types and Signals

### Single-bit Signals

Default port type. Represents a single wire carrying 0 or 1.

```shdl
component MyGate(A, B) -> (Out) {
    # A, B, Out are all 1-bit signals
}
```

### Multi-bit Signals (Vectors)

Declare with bit width in square brackets:

```shdl
component Adder8(A[8], B[8]) -> (Sum[8]) {
    # A, B, Sum are 8-bit vectors
}
```

**Bit Indexing:**
- Indexing is 1-based
- `Signal[1]` refers to the least significant bit (LSB)
- `Signal[N]` refers to the most significant bit for N-bit signal

```shdl
A[1]    # LSB of A
A[8]    # MSB of 8-bit A
```

---

## Imports and Modules

### Syntax

```shdl
use <module>::{<component1>, <component2>, ...};
```

### Standard Gates Module 


```shdl
use stdgates::{AND, OR, NOT, XOR, NAND, NOR};
# This is just for fun, it doesnt actually do anything.
```

Available standard gates:
- `AND` - Two-input AND gate
- `OR` - Two-input OR gate
- `NOT` - Single-input inverter
- `XOR` - Two-input XOR gate
- `NAND` - Two-input NAND gate
- `NOR` - Two-input NOR gate

### Custom Component Imports

```shdl
use fullAdder::{FullAdder};
use myModule::{ComponentA, ComponentB, ComponentC};
```

Import paths:
- Module name corresponds to filename (without `.shdl` extension)
- Searches in current directory and include paths specified with `-I`

---

## Instances and Connections

### Instance Declaration


```shdl
<instance_name>: <ComponentType>;
```

Examples:

```shdl
gate1: AND;
adder: FullAdder;
reg0: Register8;
```

You can declare multiple instances in one line:

```shdl
and1: AND; and2: AND; and3: AND;
```

---

### Connections and Connect Block

All connections must be within a `connect` block:

```shdl
connect {
    # connection statements
}
```
Syntax for connections:

```shdl
<source> -> <destination>;
```

#### Input to Instance Port

```shdl
A -> gate1.A;
B -> gate1.B;
```

#### Instance Output to Instance Input

```shdl
gate1.O -> gate2.A;
```

#### Instance Output to Component Output

```shdl
gate2.O -> Result;
```

#### Bit-indexed Connections

```shdl
DataBus[1] -> gate.A;      # LSB
DataBus[8] -> gate.B;      # MSB
```

### Port Naming Conventions

Standard port names for gates:
- **Inputs**: `A`, `B` (two-input gates), `A` (NOT gate)
- **Output**: `O` (for standard gates)
- **Custom**: Component-defined port names

---

Generators create repetitive structures using loop syntax.

### Syntax

```shdl
>variable[range]{
    # repeated content
}
```

### Range Formats

**1 to N:**
```shdl
>i[8]{
    # Creates iterations with i = 1, 2, 3, 4, 5, 6, 7, 8
}
```

**Start to End:**
```shdl
>i[4, 10]{
    # Creates iterations with i = 4, 5, 6, 7, 8, 9, 10
}
```

### Variable Substitution

Use `{variable}` to substitute the loop variable:

```shdl
>i[4]{
    gate{i}: AND;      # Creates: gate1, gate2, gate3, gate4
}
```

### Generator in Instance Declarations

```shdl
>i[8]{
    and{i}: AND;
    or{i}: OR;
}
# Creates: and1, and2, ..., and8, or1, or2, ..., or8
```

### Generator in Connections

```shdl
connect {
    >i[8]{
        In[{i}] -> gate{i}.A;
        gate{i}.O -> Out[{i}];
    }
}
```

---

## Standard Gates

Built-in primitive gates available in SHDL:

```shdl
component AND(A, B) -> (O) { ... }
component OR(A, B) -> (O) { ... }
component NOT(A) -> (O) { ... }
component XOR(A, B) -> (O) { ... }
component NAND(A, B) -> (O) { ... }
component NOR(A, B) -> (O) { ... }
```

All two-input gates use ports `A` and `B` for inputs and `O` for output. NOT gate uses `A` for input and `O` for output.

---

# Python API Reference

The Python API provides a simple interface for loading, simulating, and interacting with SHDL circuits.

## Circuit Class

```python
from SHDL import Circuit
```

### Constructor

```python
Circuit(shdl_file, search_paths=None)
```

**Parameters:**
- `shdl_file` (str | Path): Path to the SHDL file to load
- `search_paths` (list[str], optional): Directories to search for imported components

**Returns:** Circuit instance

**Raises:**
- `FileNotFoundError`: If the SHDL file doesn't exist
- `CompilationError`: If compilation fails

**Example:**
```python
# Basic usage
circuit = Circuit("adder.shdl")

# With custom search paths
circuit = Circuit(
    "main.shdl",
    search_paths=["./components", "./lib"]
)
```

#### Methods

##### poke(port_name, value)

Set the value of an input port.

```python
circuit.poke(port_name, value)
```

**Parameters:**
- `port_name` (str): Name of the input port
- `value` (int): Value to set (unsigned 64-bit integer)

**Example:**
```python
circuit.poke("A", 42)
circuit.poke("clk", 1)
```

##### peek(port_name)

Read the value of an output port.

```python
value = circuit.peek(port_name)
```

**Parameters:**
- `port_name` (str): Name of the output port

**Returns:** int - Current value of the port (unsigned 64-bit integer)

**Example:**
```python
result = circuit.peek("Sum")
print(f"Output: {result}")
```

##### step(cycles)

Advance the simulation by a number of cycles.

```python
circuit.step(cycles)
```

**Parameters:**
- `cycles` (int): Number of simulation cycles to run

**Example:**
```python
# Run for 10 cycles
circuit.step(10)

# Single step
circuit.step(1)
```

##### reset()

Reset the circuit to its initial state.

```python
circuit.reset()
```

**Example:**
```python
circuit.reset()
circuit.poke("A", 0)
```

---

# CLI Reference

The `shdlc` command-line tool compiles SHDL files to C code and optionally builds executables.

## shdlc Command

Compile SHDL files to C code and optionally build executables.

```bash
shdlc [options] <input.shdl>
```

## Options

| Option | Description |
|--------|-------------|
| `-o FILE`, `--output FILE` | Specify output C file (default: `<input>.c`) |
| `-I DIR`, `--include DIR` | Add directory to component search path (can be used multiple times) |
| `-c`, `--compile-only` | Generate C code only, don't compile to binary |
| `-O LEVEL`, `--optimize LEVEL` | GCC optimization level: 0, 1, 2, or 3 (default: 3) |
| `-h`, `--help` | Show help message |

## Usage Examples

```bash
# Compile to C
shdlc adder.shdl

# Specify output file
shdlc adder.shdl -o my_adder.c

# Add include paths
shdlc main.shdl -I ./components -I ./lib

# Generate C only, don't compile
shdlc adder.shdl -c

# Compile with optimization
shdlc adder.shdl -O 3
---

# Examples

## Language Examples

### Full Adder
from SHDL import Circuit

circuit = Circuit("reg16.shdl")

# Write value
circuit.poke("In", 12345)
circuit.poke("clk", 0)
circuit.step(10)

# Clock rising edge
circuit.poke("clk", 1)
circuit.step(10)

# Clock falling edge
circuit.poke("clk", 0)
circuit.step(10)

# Read stored value
value = circuit.peek("Out")
print(f"Stored: {value}")  # Output: Stored: 12345
```

```python
from SHDL import Circuit

circuit = Circuit("addSub16.shdl")

# Addition: 100 + 50
circuit.poke("A", 100)
circuit.poke("B", 50)
circuit.poke("sub", 0)  # 0 = add
circuit.step(100)
print(circuit.peek("Sum"))  # Output: 150

# Subtraction: 100 - 50
circuit.poke("sub", 1)  # 1 = subtract
circuit.step(100)
print(circuit.peek("Sum"))  # Output: 50
```

---


### Compilation Process

SHDL compilation happens in several stages:

1. **Parsing**: SHDL file is parsed into an AST
2. **Resolution**: Component imports are resolved
3. **Flattening**: Nested components are flattened to a single level
4. **C Generation**: C code is generated from the flattened circuit
5. **Compilation**: GCC compiles C code to a shared library
6. **Loading**: Python loads the shared library via ctypes

### Debugging

#### Check Generated C Code

```bash
shdlc circuit.shdl -c
cat circuit.c
```

#### Verbose Compilation

The Circuit class will show compilation errors if they occur.

#### Test Individual Components

Test components in isolation before composing them:

```python
# Test component alone
test_circuit = Circuit("fullAdder.shdl")
test_circuit.poke("A", 1)
test_circuit.poke("B", 1)
test_circuit.poke("Cin", 0)
test_circuit.step(10)
assert test_circuit.peek("Sum") == 0
assert test_circuit.peek("Cout") == 1
```
