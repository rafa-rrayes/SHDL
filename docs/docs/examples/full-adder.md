---
sidebar_position: 2
---

# Full Adder

A full adder adds two single-bit numbers along with a carry input, producing a sum and carry output.

## Truth Table

| A | B | Cin | Sum | Cout |
|---|---|-----|-----|------|
| 0 | 0 |  0  |  0  |   0  |
| 0 | 0 |  1  |  1  |   0  |
| 0 | 1 |  0  |  1  |   0  |
| 0 | 1 |  1  |  0  |   1  |
| 1 | 0 |  0  |  1  |   0  |
| 1 | 0 |  1  |  0  |   1  |
| 1 | 1 |  0  |  0  |   1  |
| 1 | 1 |  1  |  1  |   1  |

## Logic

- **Sum** = A XOR B XOR Cin
- **Cout** = (A AND B) OR ((A XOR B) AND Cin)

## SHDL Implementation

```
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    xor1: XOR;
    xor2: XOR;
    and1: AND;
    and2: AND;
    or1: OR;
    
    connect {
        # Sum = A XOR B XOR Cin
        A -> xor1.A;
        B -> xor1.B;
        xor1.O -> xor2.A;
        Cin -> xor2.B;
        xor2.O -> Sum;
        
        # Cout = (A AND B) OR ((A XOR B) AND Cin)
        A -> and1.A;
        B -> and1.B;
        xor1.O -> and2.A;
        Cin -> and2.B;
        and1.O -> or1.A;
        and2.O -> or1.B;
        or1.O -> Cout;
    }
}
```

## Circuit Diagram

```
    A ───┬──────► XOR ──┬──► XOR ────► Sum
         │          ▲    │       ▲
         │          │    │       │
    B ───┼──────────┘    │       │
         │               │       │
         │               ▼       │
         │          ┌──► AND ─┐  │
         │          │         │  │
   Cin ──┼──────────┘         ▼  │
         │                   OR ─┴──► Cout
         │                    ▲
         └──────────────► AND┘
         ▲
         │
    B ───┘
```

## Usage

Full adders are chained together to create multi-bit adders:

```
use fullAdder::{FullAdder};

component Adder4(A[4], B[4], Cin) -> (Sum[4], Cout) {
    >i[4]{
        fa{i}: FullAdder;
    }
    
    connect {
        A[1] -> fa1.A;
        B[1] -> fa1.B;
        Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];
        
        >i[2:4]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;
            fa{i}.Sum -> Sum[{i}];
        }
        
        fa4.Cout -> Cout;
    }
}
```
