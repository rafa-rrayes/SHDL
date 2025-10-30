# SHDL - Simple Hardware Description Language

A lightweight hardware description language and Python driver for digital circuit simulation. SHDL provides an intuitive syntax for defining digital circuits and a clean Python API for interacting with them (PySHDL).

## Features

- 🚀 **Simple Syntax** - Easy-to-learn hardware description language
- 🐍 **Python Integration** - Seamless Python API for circuit simulation
- ⚡ **C Backend** - Compiles to optimized C code for fast simulation and portability
- 🔧 **Command Line Tools** - Built-in compiler and utilities
- 📦 **Component Reuse** - Import and compose reusable circuit components

## Installation

```bash
pip install PySHDL
```

## Quick Start

### 1. Define a Circuit (SHDL)

Create a file `adder.shdl`:

```shdl
use fullAdder::{FullAdder};

component Adder16(A[16], B[16], Cin) -> (Sum[16], Cout) {
    >i[16]{
        fa{i}: FullAdder;
    }
    
    connect {
        A[1] -> fa1.A;
        B[1] -> fa1.B;
        Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];
        
        >i[2, 16]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;
            fa{i}.Sum -> Sum[{i}];
        }
        
        fa16.Cout -> Cout;
    }
}
```

### 2. Use in Python

```python
from PySHDL import Circuit

# Load and compile the circuit
circuit = Circuit("adder.shdl")

# Set input values
circuit.poke("A", 42)
circuit.poke("B", 17)
circuit.poke("Cin", 1)

# Run simulation
circuit.step(10)

# Read output
result = circuit.peek("Sum")
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
