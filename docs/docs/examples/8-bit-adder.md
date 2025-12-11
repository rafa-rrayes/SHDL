---
sidebar_position: 3
---

# 8-bit Ripple Carry Adder

An 8-bit adder that can add two 8-bit numbers together, using a chain of full adders.

## How It Works

A ripple carry adder chains multiple full adders together, where the carry output of each adder feeds into the carry input of the next. While simple, this design has propagation delay as carries "ripple" through the chain.

## SHDL Implementation

```
use fullAdder::{FullAdder};

component Adder8(A[8], B[8], Cin) -> (Sum[8], Cout) {
    # Create 8 full adders using a generator
    >i[8]{
        fa{i}: FullAdder;
    }
    
    connect {
        # First adder gets the initial carry input
        A[1] -> fa1.A;
        B[1] -> fa1.B;
        Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];
        
        # Chain remaining adders (carry ripples through)
        >i[2:8]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;
            fa{i}.Sum -> Sum[{i}];
        }
        
        # Final carry output
        fa8.Cout -> Cout;
    }
}
```

## Key Concepts Used

### Generators

The generator `>i[8]{ fa{i}: FullAdder; }` creates 8 instances:
- `fa1`, `fa2`, `fa3`, `fa4`, `fa5`, `fa6`, `fa7`, `fa8`

### Arithmetic in Generators

The expression `fa{i-1}.Cout -> fa{i}.Cin` connects:
- `fa1.Cout -> fa2.Cin`
- `fa2.Cout -> fa3.Cin`
- ...and so on

### Multi-bit Signals

`A[8]` declares an 8-bit input vector. Individual bits are accessed as `A[1]` through `A[8]`.

## Usage Example

```
use adder8::{Adder8};

component Add16to8(Value[8]) -> (Result[8], Overflow) {
    adder: Adder8;
    Sixteen[8] = 16;  # Constant 16 (8 bits)
    Zero = 0;         # No carry in
    
    connect {
        Value[:8] -> adder.A[:8];
        Sixteen[:8] -> adder.B[:8];
        Zero -> adder.Cin;
        adder.Sum[:8] -> Result[:8];
        adder.Cout -> Overflow;
    }
}
```

## Extending to 16-bit

The same pattern extends to any width:

```
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
        
        >i[2:16]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;
            fa{i}.Sum -> Sum[{i}];
        }
        
        fa16.Cout -> Cout;
    }
}
```
