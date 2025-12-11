---
sidebar_position: 9
---

# Standard Gates

Built-in primitive gates available in all SHDL files without imports.

## Overview

SHDL provides six standard primitive gates. Four are logic gates, and two are constant sources (power pins).

| Gate | Type | Inputs | Output | Description |
|------|------|--------|--------|-------------|
| `AND` | Logic | A, B | O | Logical AND |
| `OR` | Logic | A, B | O | Logical OR |
| `NOT` | Logic | A | O | Logical NOT (inverter) |
| `XOR` | Logic | A, B | O | Exclusive OR |
| `__VCC__` | Power | (none) | O | Constant HIGH (1) |
| `__GND__` | Power | (none) | O | Constant LOW (0) |

## Logic Gates

### AND Gate

Outputs 1 only when both inputs are 1.

| A | B | O |
|---|---|---|
| 0 | 0 | 0 |
| 0 | 1 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |

```
component AndExample(X, Y) -> (Z) {
    g1: AND;
    
    connect {
        X -> g1.A;
        Y -> g1.B;
        g1.O -> Z;
    }
}
```

### OR Gate

Outputs 1 when at least one input is 1.

| A | B | O |
|---|---|---|
| 0 | 0 | 0 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 1 |

```
component OrExample(X, Y) -> (Z) {
    g1: OR;
    
    connect {
        X -> g1.A;
        Y -> g1.B;
        g1.O -> Z;
    }
}
```

### NOT Gate

Inverts the input.

| A | O |
|---|---|
| 0 | 1 |
| 1 | 0 |

```
component NotExample(X) -> (Z) {
    g1: NOT;
    
    connect {
        X -> g1.A;
        g1.O -> Z;
    }
}
```

### XOR Gate

Outputs 1 when inputs are different.

| A | B | O |
|---|---|---|
| 0 | 0 | 0 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 0 |

```
component XorExample(X, Y) -> (Z) {
    g1: XOR;
    
    connect {
        X -> g1.A;
        Y -> g1.B;
        g1.O -> Z;
    }
}
```

## Power Pins

Power pins are constant sources. They have no inputs—only a single output `O`.

### VCC (Constant HIGH)

Always outputs logic 1.

```
component ConstantOne() -> (Out) {
    vcc: __VCC__;
    
    connect {
        vcc.O -> Out;
    }
}
```

### GND (Constant LOW)

Always outputs logic 0.

```
component ConstantZero() -> (Out) {
    gnd: __GND__;
    
    connect {
        gnd.O -> Out;
    }
}
```

:::info Power Pin Names
The double underscores in `__VCC__` and `__GND__` indicate these are system-reserved names. You cannot use identifiers starting with `__` for your own instances.
:::

## Derived Gates

NAND and NOR are not primitives in SHDL, but they can be easily constructed:

### NAND Gate

```
component NAND(A, B) -> (O) {
    and1: AND;
    not1: NOT;
    
    connect {
        A -> and1.A;
        B -> and1.B;
        and1.O -> not1.A;
        not1.O -> O;
    }
}
```

### NOR Gate

```
component NOR(A, B) -> (O) {
    or1: OR;
    not1: NOT;
    
    connect {
        A -> or1.A;
        B -> or1.B;
        or1.O -> not1.A;
        not1.O -> O;
    }
}
```

### XNOR Gate

```
component XNOR(A, B) -> (O) {
    xor1: XOR;
    not1: NOT;
    
    connect {
        A -> xor1.A;
        B -> xor1.B;
        xor1.O -> not1.A;
        not1.O -> O;
    }
}
```

## Port Conventions

All primitive gates follow these conventions:

| Port | Direction | Usage |
|------|-----------|-------|
| `A` | Input | First input (all gates) |
| `B` | Input | Second input (2-input gates) |
| `O` | Output | Gate output |

The output port is always named `O` (letter O, not zero).

## Common Patterns

### Buffer (Double Inverter)

A signal passed through two NOT gates remains unchanged but gets re-driven:

```
component Buffer(In) -> (Out) {
    n1: NOT;
    n2: NOT;
    
    connect {
        In -> n1.A;
        n1.O -> n2.A;
        n2.O -> Out;
    }
}
```

### 3-Input AND (Cascaded)

```
component And3(A, B, C) -> (O) {
    and1: AND;
    and2: AND;
    
    connect {
        A -> and1.A;
        B -> and1.B;
        and1.O -> and2.A;
        C -> and2.B;
        and2.O -> O;
    }
}
```

### N-Input AND (Using Generator)

```
component And8(A[8]) -> (Out) {
    >i[7]{
        and{i}: AND;
    }
    
    connect {
        A[1] -> and1.A;
        A[2] -> and1.B;
        
        >i[2:7]{
            and{i-1}.O -> and{i}.A;
            A[{i+1}] -> and{i}.B;
        }
        
        and7.O -> Out;
    }
}
```

## Why These Primitives?

SHDL uses only AND, OR, NOT, and XOR as logic primitives because:

1. **Completeness** - These gates can implement any Boolean function
2. **Efficiency** - They map directly to C bitwise operators (`&`, `|`, `~`, `^`)
3. **Simplicity** - Fewer primitives means simpler compiler and flattener
4. **Performance** - Direct mapping enables SIMD-style bit-packed evaluation

The power pins (`__VCC__` and `__GND__`) exist to support constants after flattening, where named constants become explicit constant sources.
