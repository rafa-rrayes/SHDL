---
sidebar_position: 6
---

# Generators

Generators dynamically create SHDL code using a for-loop-like structure. Each line inside a generator is copied once for every value in the range, with the loop variable substituted.

:::tip Generators vs Expanders
Generators are the powerful, general-purpose tool for repetitive patterns. Unlike expanders (which only expand bit ranges in connections), generators can:
- Create multiple instances
- Be used in both declarations and connections
- Perform arithmetic operations (`{i+1}`, `{i*j}`, `{i-1}`)
- Be nested for multi-dimensional structures
- Use non-contiguous ranges (`[1:4, 8, 12:16]`)
:::

## Generator Syntax

```
>variable[range]{
    # Repeated content - copied for each value
}
```

- `>` prefix indicates a generator
- `variable` is the loop variable (commonly `i`, `j`, `k`)
- `range` specifies which values the variable takes
- Content inside `{}` is repeated for each value, with `{variable}` substituted

## Range Formats

### Single Value (1 to N)

```
>i[8]{
    # i = 1, 2, 3, 4, 5, 6, 7, 8
}
```

### Closed Range (start to end)

```
>i[4:10]{
    # i = 4, 5, 6, 7, 8, 9, 10
}
```

### Open-ended Range

```
>i[5:]{
    # i = 5, 6, 7, ... (to signal's bit width)
}
```

### Multiple Ranges (comma-separated)

```
>i[1:4, 8, 12:16]{
    # i = 1, 2, 3, 4, 8, 12, 13, 14, 15, 16
}
```

## Variable Substitution

Use `{variable}` to insert the loop variable's value:

```
>i[4]{
    gate{i}: AND;
}
```

Expands to:

```
gate1: AND;
gate2: AND;
gate3: AND;
gate4: AND;
```

## Arithmetic in Substitutions

Generators support arithmetic expressions inside `{}`:

```
>i[2:8]{
    prev{i-1}.O -> curr{i}.A;    # {i-1} = previous index
    Data[{i+1}] -> curr{i}.B;    # {i+1} = next index
}
```

### Supported Operations

- **Addition**: `{i+1}`, `{i+10}`
- **Subtraction**: `{i-1}`, `{j-2}`
- **Multiplication**: `{i*2}`, `{i*j}`
- **Complex expressions**: `{i*4+1}`, `{i*j+k}`

### Stride Example

```
>i[4]{
    Data[{i*2-1}] -> EvenBits[{i}];   # Bits 1, 3, 5, 7
    Data[{i*2}] -> OddBits[{i}];       # Bits 2, 4, 6, 8
}
```

## Generator Usage

### In Instance Declarations

```
>i[8]{
    and{i}: AND;
    or{i}: OR;
}
# Creates: and1-and8, or1-or8
```

### In Connections

```
connect {
    >i[8]{
        In[{i}] -> gate{i}.A;
        gate{i}.O -> Out[{i}];
    }
}
```

### Nested Generators

For 2D structures:

```
>i[4]{
    >j[4]{
        cell{i}_{j}: BitCell;
    }
}
# Creates: cell1_1, cell1_2, ..., cell4_4 (16 instances)
```

### Nested with Arithmetic

```
>row[4]{
    >col[4]{
        # Linear index from 2D coordinates
        cell{row*4+col}: Memory;
    }
}
# Creates: cell5, cell6, ..., cell20
```

## Real-world Example: 8-Input AND Gate

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

## Real-world Example: 8-bit Ripple Carry Adder

```
use fullAdder::{FullAdder};

component Adder8(A[8], B[8], Cin) -> (Sum[8], Cout) {
    >i[8]{
        fa{i}: FullAdder;
    }
    
    connect {
        # First adder gets Cin
        A[1] -> fa1.A;
        B[1] -> fa1.B;
        Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];
        
        # Chain remaining adders
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
