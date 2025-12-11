---
sidebar_position: 4
---

# Multiplexer

A multiplexer (mux) selects one of several inputs and forwards it to the output based on a selection signal.

## 2-to-1 Multiplexer

Selects between two inputs based on a single selection bit.

### Truth Table

| Sel | Out |
|-----|-----|
|  0  |  A  |
|  1  |  B  |

### SHDL Implementation

```
component Mux2(A, B, Sel) -> (Out) {
    not1: NOT;
    and1: AND;
    and2: AND;
    or1: OR;
    
    connect {
        # Invert selection signal
        Sel -> not1.A;
        
        # Select A when Sel = 0
        A -> and1.A;
        not1.O -> and1.B;
        
        # Select B when Sel = 1
        B -> and2.A;
        Sel -> and2.B;
        
        # Combine results
        and1.O -> or1.A;
        and2.O -> or1.B;
        or1.O -> Out;
    }
}
```

## 4-to-1 Multiplexer

Selects one of four inputs using 2 selection bits.

### SHDL Implementation

```
use mux2::{Mux2};

component Mux4(A, B, C, D, Sel[2]) -> (Out) {
    mux1: Mux2;  # A or B
    mux2: Mux2;  # C or D
    mux3: Mux2;  # Result of mux1 or mux2
    
    connect {
        # First level: select within pairs
        A -> mux1.A;
        B -> mux1.B;
        Sel[1] -> mux1.Sel;
        
        C -> mux2.A;
        D -> mux2.B;
        Sel[1] -> mux2.Sel;
        
        # Second level: select between pairs
        mux1.Out -> mux3.A;
        mux2.Out -> mux3.B;
        Sel[2] -> mux3.Sel;
        
        mux3.Out -> Out;
    }
}
```

## 8-to-1 Multiplexer

```
use mux4::{Mux4};
use mux2::{Mux2};

component Mux8(In[8], Sel[3]) -> (Out) {
    mux1: Mux4;  # Inputs 1-4
    mux2: Mux4;  # Inputs 5-8
    mux3: Mux2;  # Final selection
    
    connect {
        In[1] -> mux1.A;
        In[2] -> mux1.B;
        In[3] -> mux1.C;
        In[4] -> mux1.D;
        Sel[:2] -> mux1.Sel[:2];
        
        In[5] -> mux2.A;
        In[6] -> mux2.B;
        In[7] -> mux2.C;
        In[8] -> mux2.D;
        Sel[:2] -> mux2.Sel[:2];
        
        mux1.Out -> mux3.A;
        mux2.Out -> mux3.B;
        Sel[3] -> mux3.Sel;
        
        mux3.Out -> Out;
    }
}
```

## 16-bit 2-to-1 Multiplexer

For multi-bit data paths:

```
use mux2::{Mux2};

component Mux2_16(A[16], B[16], Sel) -> (Out[16]) {
    >i[16]{
        mux{i}: Mux2;
    }
    
    connect {
        >i[16]{
            A[{i}] -> mux{i}.A;
            B[{i}] -> mux{i}.B;
            Sel -> mux{i}.Sel;
            mux{i}.Out -> Out[{i}];
        }
    }
}
```

This uses a generator to create 16 individual 2-to-1 muxes, all controlled by the same selection signal.
