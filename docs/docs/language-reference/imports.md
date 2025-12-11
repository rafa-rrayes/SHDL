---
sidebar_position: 8
---

# Imports

Import components from other SHDL files using the `use` statement.

## Import Syntax

```
use <module>::{<Component1>, <Component2>, ...};
```

## Examples

```
use fullAdder::{FullAdder};
use alu::{ALU, Shifter, Comparator};
use utils::{Mux2, Mux4, Decoder};
```

## Module Resolution

- Module name corresponds to filename without `.shdl` extension
- `use fullAdder::{...}` looks for `fullAdder.shdl`
- Searches in:
  1. Current directory
  2. Directories specified with `-I` flag during compilation

## File Structure Example

```
project/
├── main.shdl
├── components/
│   ├── fullAdder.shdl
│   └── register.shdl
```

```
# In main.shdl (compiled with -I components/)
use fullAdder::{FullAdder};
use register::{Register8, Register16};
```

## Complete Example

**fullAdder.shdl:**

```
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    xor1: XOR;
    xor2: XOR;
    and1: AND;
    and2: AND;
    or1: OR;
    
    connect {
        A -> xor1.A;
        B -> xor1.B;
        xor1.O -> xor2.A;
        Cin -> xor2.B;
        xor2.O -> Sum;
        
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

**adder8.shdl:**

```
use fullAdder::{FullAdder};

component Adder8(A[8], B[8], Cin) -> (Sum[8], Cout) {
    >i[8]{
        fa{i}: FullAdder;
    }
    
    connect {
        A[1] -> fa1.A;
        B[1] -> fa1.B;
        Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];
        
        >i[2:8]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;
            fa{i}.Sum -> Sum[{i}];
        }
        
        fa8.Cout -> Cout;
    }
}
```

## Import Rules

1. Imports must appear at the top of the file, before any component definitions
2. You can import multiple components from the same module in one statement
3. Circular imports are not allowed
4. Each component can only be defined once per module
