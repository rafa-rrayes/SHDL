---
sidebar_position: 1
slug: /intro
---

# Introduction to SHDL

**SHDL** (Simple Hardware Description Language) is a minimalist hardware description language designed for clarity and ease of use. It describes digital circuits as hierarchical compositions of components connected by signals.

## SHDL vs PySHDL

| | SHDL | PySHDL |
|---|------|--------|
| **What is it?** | A hardware description *language* | A Python *library* |
| **Purpose** | Describe digital circuits in `.shdl` files | Parse, compile, and simulate SHDL circuits |
| **File extension** | `.shdl` | `.py` |
| **Install command** | N/A (it's a language spec) | `pip install PySHDL` |

- **SHDL** is the language specification - the syntax and semantics for describing circuits
- **PySHDL** is the reference implementation - a Python library that can parse, flatten, compile, and simulate SHDL circuits

## Why SHDL?

Traditional hardware description languages like Verilog and VHDL are powerful but complex. SHDL takes a different approach:

- **Simplicity**: Minimal syntax, maximum clarity
- **Hierarchy**: Build complex circuits from simple building blocks
- **Explicitness**: All connections are explicitly declared
- **Educational**: Perfect for learning digital logic design

## Quick Example

Here's a simple half adder in SHDL:

```
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

## Key Features

### 🔧 Built-in Primitive Gates
SHDL comes with standard logic gates: `AND`, `OR`, `NOT`, and `XOR`. Power pins `__VCC__` and `__GND__` provide constant values.

### 📦 Hierarchical Components
Build complex circuits by composing simpler components:

```
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    ha1: HalfAdder;
    ha2: HalfAdder;
    or1: OR;
    
    connect {
        A -> ha1.A;
        B -> ha1.B;
        ha1.Sum -> ha2.A;
        Cin -> ha2.B;
        ha2.Sum -> Sum;
        ha1.Carry -> or1.A;
        ha2.Carry -> or1.B;
        or1.O -> Cout;
    }
}
```

### 🔄 Generators for Repetitive Patterns
Create multiple instances with loop-like syntax:

```
>i[8]{
    gate{i}: AND;
}
# Creates: gate1, gate2, gate3, gate4, gate5, gate6, gate7, gate8
```

### 📊 Multi-bit Signals (Vectors)
Work with buses and multi-bit data:

```
component Adder8(A[8], B[8], Cin) -> (Sum[8], Cout) {
    # 8-bit adder implementation
}
```

## Getting Started

Ready to dive in? Check out:

1. [Installation Guide](/docs/getting-started/installation) - Install PySHDL on your machine
2. [Your First Circuit](/docs/getting-started/first-circuit) - Build a simple circuit step by step
3. [Language Reference](/docs/category/language-reference) - Complete SHDL syntax documentation
4. [Architecture](/docs/architecture/overview) - Understand how SHDL works under the hood
5. [SHDB Debugger](/docs/debugger/overview) - Debug circuits with GDB-style commands

## Design Philosophy

SHDL follows these core principles:

| Principle | Description |
|-----------|-------------|
| **Clarity over brevity** | Code should be readable and self-documenting |
| **Gates. That's all** | Use only basic gates as building blocks, no if statements or complex constructs |
| **Explicit over implicit** | All connections must be explicitly declared |
| **Composition over complexity** | Complex circuits are built from simple components |
| **1-based indexing** | All bit indices start at 1 (LSB = 1) |

## What You Can Build

With SHDL, you can design:

- **Basic Logic**: Gates, multiplexers, decoders
- **Arithmetic Units**: Adders, subtractors, ALUs
- **Memory Elements**: Registers, flip-flops, RAM
- **Complete CPUs**: Full processor designs with control units

Check out the [Examples](/docs/category/examples) section for complete implementations!
