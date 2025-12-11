---
sidebar_position: 1
---

# Architecture Overview

SHDL uses a multi-stage compilation pipeline that transforms high-level hardware descriptions into highly optimized, executable simulations.

## The Big Picture

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXPANDED SHDL                                │
│     (Your source code: hierarchy, generators, constants)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   FLATTENER     │
                    │  (5 phases)     │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        BASE SHDL                                │
│         (Flat, explicit: only primitive gates)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │    COMPILER     │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      C SOURCE CODE                              │
│       (Bit-packed SIMD-style simulation)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  C COMPILER     │
                    │  (clang/gcc)    │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SHARED LIBRARY                                │
│        (.dylib / .so / .dll)                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PYTHON API    │
                    │  (SHDLCircuit)  │
                    └─────────────────┘
```

## Two Languages, One System

SHDL actually consists of two related languages:

| | Expanded SHDL | Base SHDL |
|---|---|---|
| **Purpose** | Human authoring | Compilation target |
| **Abstraction** | High-level, convenient | Low-level, explicit |
| **Hierarchy** | Nested components | Flat, single-level |
| **Features** | Generators, expanders, constants | Primitives only |

**Expanded SHDL** is what you write. It includes powerful features like:
- Hierarchical component composition
- Generators for repetitive patterns
- Expanders for bit-range operations
- Named constants
- Import statements

**Base SHDL** is the intermediate representation after flattening. It contains:
- Only primitive gates (`AND`, `OR`, `NOT`, `XOR`)
- Power pins (`__VCC__`, `__GND__`)
- Explicit single-bit connections
- No hierarchy, no abstractions

## Why This Architecture?

### Separation of Concerns

1. **Flattener**: Handles all language complexity (generators, hierarchy, etc.)
2. **Compiler**: Only deals with simple primitives and connections
3. **Driver**: Provides a clean Python interface

This separation makes each component simpler, easier to test, and easier to maintain.

### Performance

The final C code uses a **bit-packed SIMD-style** approach:
- Gates of the same type are packed into 64-bit integers
- A single CPU operation evaluates up to 64 gates in parallel
- This makes simulation extremely fast

### Portability

The generated C code is portable and can be compiled on any platform:
- macOS (`.dylib`)
- Linux (`.so`)
- Windows (`.dll`)

## Key Components

### 1. Lexer & Parser

Tokenizes and parses SHDL source code into an Abstract Syntax Tree (AST).

```python
from SHDL import parse_file

module = parse_file("adder16.shdl")
for component in module.components:
    print(f"Component: {component.name}")
```

### 2. Flattener

Transforms Expanded SHDL to Base SHDL through 5 phases:

1. **Lexical Stripping** - Remove comments and imports
2. **Generator Expansion** - Unroll all generators
3. **Expander Expansion** - Expand bit-slice notation
4. **Constant Materialization** - Convert constants to `__VCC__`/`__GND__`
5. **Hierarchy Flattening** - Inline all subcomponents

```python
from SHDL import flatten_file

base_shdl = flatten_file("adder16.shdl", component="Adder16")
print(base_shdl)
```

### 3. Compiler

Compiles Base SHDL to optimized C code:

```python
from SHDL import compile_shdl_file

c_code = compile_shdl_file("adder16.shdl")
print(c_code)
```

### 4. Driver

The `SHDLCircuit` class handles:
- Compilation to C
- Invoking the C compiler
- Loading the shared library
- Providing `poke()`, `peek()`, `step()` interface

```python
from SHDL import SHDLCircuit

with SHDLCircuit("adder16.shdl") as circuit:
    circuit.poke("A", 100)
    circuit.poke("B", 50)
    circuit.step()
    print(circuit.peek("Sum"))  # 150
```

## What's Next?

- [Flattening Pipeline](./flattening-pipeline) - Deep dive into the 5 flattening phases
- [Compiler Internals](./compiler-internals) - How C code generation works
- [Base SHDL](./base-shdl) - The intermediate representation
- [SHDB Debugger](/docs/debugger/overview) - Interactive debugging for SHDL circuits
