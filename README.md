# SHDL - Simple Hardware Description Language

A lightweight hardware description language and Python driver for digital circuit simulation. SHDL provides an intuitive syntax for defining digital circuits and a clean Python API for interacting with them (PySHDL).

## Features

- 🚀 **Simple Syntax** - Easy-to-learn hardware description language
- 🐍 **Python Integration** - Seamless Python API for circuit simulation
- ⚡ **C Backend** - Compiles to optimized C code for fast simulation and portability
- 🔧 **Command Line Tools** - Built-in compiler and utilities
- 📦 **Component Reuse** - Import and compose reusable circuit components
- 🔢 **Constants Support** - Use named constants for parameterizable designs

## Installation

We recommend using `uv` for using PySHDL. If you don't have it installed, you can install it via pip:

```bash
pip install PySHDL
```

## Quick Start

### 1. Define a Circuit (SHDL)

Create a file `fullAdder.shdl`:

```shdl
component FullAdder(A, B, Cin) -> (Sum, Cout) {

    x1: XOR; a1: AND;
    x2: XOR; a2: AND;
    o1: OR;

    connect {
        A -> x1.A; B -> x1.B;
        A -> a1.A; B -> a1.B;

        x1.O -> x2.A; Cin -> x2.B;
        x1.O -> a2.A; Cin -> a2.B;
        a1.O -> o1.A; a2.O -> o1.B;

        x2.O -> Sum; o1.O -> Cout;
    }
}
```

### 2. Use in Python

```python
from SHDL import Circuit

# Load and compile the circuit
with Circuit("fullAdder.shdl") as c:
    # Set input values
    c.poke("A", 1)
    c.poke("B", 1)
    c.poke("Cin", 1)
    # Run simulation
    c.step(10)
    # Read output
    result = c.peek("Sum")
print(f"Result: {result}")  # Output: Result: 60
```

### 3. Compile from Command Line

```bash
# Compile SHDL to C
shdlc adder.shdl -o adder.c

# Compile and build executable
shdlc adder.shdl --optimize 3
```

## CLI Options

```
shdlc [options] <input.shdl>

Options:
  -o, --output FILE       Output C file (default: <input>.c)
  -I, --include DIR       Add directory to component search path
  -c, --compile-only      Generate C code only, do not compile to binary
  -O, --optimize LEVEL    GCC optimization level 0-3 (default: 3)
```

## Python API

### Circuit Class

```python
Circuit(shdl_file, search_paths=None)
```

Create a new circuit instance from a SHDL file.

**Methods:**

- `poke(port_name, value)` - Set an input port value
- `peek(port_name)` - Read an output port value
- `step(cycles)` - Advance simulation by N cycles
- `reset()` - Reset circuit to initial state

## Examples

See the `examples/` directory for more complete examples:

- `interacting.py` - Basic circuit interaction
- `SHDL_components/` - Reusable component library

## Documentation
Github repository: [rafa-rrayes/SHDL](https://github.com/rafa-rrayes/SHDL)
For more detailed documentation, see [DOCS.md](https://github.com/rafa-rrayes/SHDL/blob/master/DOCS.md)

## Requirements

- Python >= 3.9
- GCC or compatible C compiler (for circuit compilation)

## Author

**Rafa Rayes**  
Email: rafa@rayes.com.br
GitHub: [rafa-rrayes](https://github.com/rafa-rrayes)

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
