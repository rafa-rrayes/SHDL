# SHDL - Simple Hardware Description Language

A simple and expressive hardware description language designed for easy digital circuit modeling and simulation. It's purpose is to be extremely minimal while still being able to create complex designs just from the most basic logic gates. SHDL allows users to define combinational and sequential logic circuits using a clean syntax, supporting hierarchical designs and vector operations.

## Features

- **Simple Syntax** - Clean, minimal syntax for describing digital circuits
- **Hierarchical Design** - Build complex circuits from reusable components
- **Vector Support** - Support for multi-bit signals
- **Generators** - Loop constructs for repetitive circuit patterns
- **C Code Generation** - Compile SHDL to optimized C simulators

## Quick Example

```shdl
# Full Adder Component
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    instances {
        xor1: XOR;
        xor2: XOR;
        and1: AND;
        and2: AND;
        or1: OR;
    }
    
    connect {
        A -> xor1.A;
        B -> xor1.B;
        xor1.Y -> xor2.A;
        Cin -> xor2.B;
        xor2.Y -> Sum;
        # ... carry logic
    }
}
```

## Getting Started

### Prerequisites

- Python 3.7+

### Usage

1. **Write your circuit** in SHDL (`.shdl` file)
2. **Compile to C**:
   ```shell
   chmod +x shdlc
   ./shdlc my_circuit.shdl -o my_circuit.c
   ```
3. **Compile and run** the generated C code
    ```shell
    gcc my_circuit.c -o my_circuit
    ./my_circuit
    ```

## Project Structure

- `shdl_compiler.py` - Main compiler library
- `SHDL_components/` - Example component library
- `LANGUAGE_SPEC.md` - Complete language specification

## Documentation

See [LANGUAGE_SPEC.md](LANGUAGE_SPEC.md) for the complete language specification.


I love the idea of SHDL and I think it would be awesome if someone could implement it in a better way. I have little idea of what I'm doing here.

You can customize the way you interact with the binary circuit simulation by altering the main function. The way it's implemented is very basic and just for testing purposes. I want to add something like GDB for the simulation. I also want to make a tool that allows you to map pins on the circuit to real world inputs/outputs like GPIO pins on a Raspberry Pi or an Arduino and then you can actually use the circuits you design in SHDL with real hardware. 