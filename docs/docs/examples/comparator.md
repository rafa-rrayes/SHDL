---
sidebar_position: 5
---

# Comparator

A circuit that compares two values and determines if they are equal.

## Compare with Constant

This example compares an 8-bit input against the constant value 100:

```
use or8inputs::{Or8Inputs};

component Compare100(A[8]) -> (Equal) {
    # XOR gates to check each bit against the constant
    >i[8]{
        xor{i}: XOR;
    }
    
    # Combine all XOR outputs
    or1: Or8Inputs;
    
    # Invert: Equal = NOT(any bits different)
    not1: NOT;

    # The constant value 100 (binary: 01100100)
    Hundred[8] = 100;

    connect {
        # Compare each bit
        >i[8]{
            A[{i}] -> xor{i}.A;
            Hundred[{i}] -> xor{i}.B;
            xor{i}.O -> or1.A[{i}];
        }
        
        # If any XOR output is 1, values differ
        # So Equal = NOT(OR of all XORs)
        or1.Out -> not1.A;
        not1.O -> Equal;
    }
}
```

## How It Works

1. **XOR each bit pair** - If bits are the same, XOR outputs 0. If different, outputs 1.
2. **OR all results** - If any bit differs, the OR outputs 1.
3. **Invert** - We want Equal=1 when they match, so invert the OR output.

### Truth Example

Comparing `A = 100` with constant `100`:
- Each XOR outputs 0 (bits are identical)
- OR of all zeros = 0
- NOT(0) = 1 → Equal!

Comparing `A = 101` with constant `100`:
- Bit 1: XOR(1, 0) = 1 (different!)
- OR includes a 1 → outputs 1
- NOT(1) = 0 → Not equal

## Generic Two-Input Comparator

Compare two 8-bit inputs:

```
use or8inputs::{Or8Inputs};

component Compare8(A[8], B[8]) -> (Equal) {
    >i[8]{
        xor{i}: XOR;
    }
    or1: Or8Inputs;
    not1: NOT;

    connect {
        >i[8]{
            A[{i}] -> xor{i}.A;
            B[{i}] -> xor{i}.B;
            xor{i}.O -> or1.A[{i}];
        }
        or1.Out -> not1.A;
        not1.O -> Equal;
    }
}
```

## Required Components

This example uses `Or8Inputs`, an 8-input OR gate:

```
component Or8Inputs(A[8]) -> (Out) {
    >i[7]{
        or{i}: OR;
    }
    
    connect {
        A[1] -> or1.A;
        A[2] -> or1.B;
        
        >i[2:7]{
            or{i-1}.O -> or{i}.A;
            A[{i+1}] -> or{i}.B;
        }
        
        or7.O -> Out;
    }
}
```

## Testing with PySHDL

```python
from SHDL import SHDLCircuit

with SHDLCircuit("compare100.shdl") as cmp:
    # Test equal case
    cmp.poke("A", 100)
    cmp.step()
    assert cmp.peek("Equal") == 1
    
    # Test not equal
    cmp.poke("A", 99)
    cmp.step()
    assert cmp.peek("Equal") == 0
    
    cmp.poke("A", 101)
    cmp.step()
    assert cmp.peek("Equal") == 0
    
    print("All comparator tests passed!")
```
