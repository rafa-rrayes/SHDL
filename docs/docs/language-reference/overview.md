---
sidebar_position: 1
---

# Language Overview

SHDL (Simple Hardware Description Language) is a minimalist hardware description language designed for clarity and ease of use.

:::tip This is the Language Reference
This section documents **SHDL** - the language syntax and semantics. For information on using the **PySHDL** Python library to compile and simulate circuits, see [Using PySHDL](/docs/getting-started/using-pyshdl).
:::

## Basic Structure

Every SHDL file contains one or more component definitions:

```
component ComponentName(inputs) -> (outputs) {
    # Instances and constants
    
    connect {
        # Connections
    }
}
```

## Design Philosophy

- **Simplicity**: Minimal syntax, maximum clarity
- **Hierarchy**: Build complex circuits from simple building blocks
- **Explicitness**: All connections are explicitly declared
- **1-based Indexing**: All bit indices start at 1 (LSB = 1)

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Components** | Reusable circuit modules with inputs and outputs |
| **Instances** | Concrete occurrences of components |
| **Signals** | Wires that carry digital values |
| **Connections** | How signals flow between ports and instances |
| **Generators** | Loop-like constructs for repetitive patterns |
| **Constants** | Fixed bit patterns for use in circuits |

## Reserved Keywords

| Keyword | Purpose |
|---------|---------|
| `component` | Declares a new component |
| `use` | Imports components from modules |
| `connect` | Begins the connection block |

## Primitive Gates

Built-in gates available without imports:

| Gate | Inputs | Output | Function |
|------|--------|--------|----------|
| `AND` | A, B | O | O = A ∧ B |
| `OR` | A, B | O | O = A ∨ B |
| `NOT` | A | O | O = ¬A |
| `XOR` | A, B | O | O = A ⊕ B |
| `NAND` | A, B | O | O = ¬(A ∧ B) |
| `NOR` | A, B | O | O = ¬(A ∨ B) |

## What's Next?

Explore each aspect of the language in detail:

- [Lexical Elements](./lexical-elements) - Comments, identifiers, literals
- [Components](./components) - Defining reusable circuit modules
- [Signals](./signals) - Single-bit and multi-bit signals
- [Connections](./connections) - Wiring signals together
- [Generators](./generators) - Creating repetitive patterns
- [Constants](./constants) - Using fixed values
- [Imports](./imports) - Importing from other files
