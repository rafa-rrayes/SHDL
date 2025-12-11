---
sidebar_position: 1
---

# Half Adder

A half adder is the simplest arithmetic circuit that adds two single-bit numbers.

## Truth Table

| A | B | Sum | Carry |
|---|---|-----|-------|
| 0 | 0 |  0  |   0   |
| 0 | 1 |  1  |   0   |
| 1 | 0 |  1  |   0   |
| 1 | 1 |  0  |   1   |

## Logic

- **Sum** = A XOR B (outputs 1 when inputs differ)
- **Carry** = A AND B (outputs 1 when both inputs are 1)

## SHDL Implementation

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

## Circuit Diagram

```
    A ───┬──────► XOR ────► Sum
         │          ▲
         │          │
    B ───┼──────────┘
         │
         └──────► AND ────► Carry
         ▲
         │
    B ───┘
```

## Usage

The half adder is the building block for:
- Full adders (by adding a carry input)
- Multi-bit adders
- ALUs
