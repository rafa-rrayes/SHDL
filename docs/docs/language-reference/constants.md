---
sidebar_position: 7
---

# Constants

Constants define fixed bit patterns that can be used in connections without external inputs.

## Declaration

```
<name> = <value>;
<name>[<width>] = <value>;   # With explicit bit width
```

Constants are declared in the component body, alongside instance declarations.

```
component MyComponent(In[8]) -> (Out) {
    THRESHOLD = 100;
    MASK = 0xFF;
    DATA[8] = 100;    # Explicit 8-bit width
    
    connect { ... }
}
```

## Number Formats

| Format | Prefix | Example | Decimal Value |
|--------|--------|---------|---------------|
| Decimal | (none) | `100` | 100 |
| Hexadecimal | `0x` | `0x64` | 100 |
| Binary | `0b` | `0b01100100` | 100 |

```
DECIMAL_VAL = 255;
HEX_VAL = 0xFF;
BINARY_VAL = 0b11111111;
# All three represent the same value
```

## Bit Width

### Inferred Width (from value)

By default, the bit width is automatically determined from the value:

| Value | Binary | Inferred Width |
|-------|--------|----------------|
| 1 | `1` | 1 bit |
| 6 | `110` | 3 bits |
| 100 | `1100100` | 7 bits |
| 255 | `11111111` | 8 bits |
| 256 | `100000000` | 9 bits |

```
One = 1;           # 1-bit constant
Six = 6;           # 3-bit constant (0b110)
OneHundred = 100;  # 7-bit constant
MaxByte = 255;     # 8-bit constant
```

### Explicit Width (recommended)

When a constant needs to match a specific port width, use explicit width annotation:

```
Hundred[8] = 100;  # 8-bit constant (bits 1-8 defined, bit 8 = 0)
Zero[16] = 0;      # 16-bit constant of all zeros
Pattern[4] = 5;    # 4-bit constant: 0b0101
```

:::warning Best Practice
When using constants with generators that iterate over a fixed bit range (like `>i[8]`), always specify the width explicitly to avoid "undefined bit" errors.
:::

### Width Example

```
# Good: explicit width matches the port width
component Add100(A[8]) -> (Sum[8], Cout) {
    Hundred[8] = 100;  # Explicit 8-bit width
    connect {
        >i[8]{
            Hundred[{i}] -> fa{i}.B;  # All 8 bits are defined
        }
    }
}

# Risky: inferred width (7 bits for value 100)
component Add100Bad(A[8]) -> (Sum[8], Cout) {
    Hundred = 100;  # Only 7 bits! Hundred[8] is undefined
    connect {
        >i[8]{
            Hundred[{i}] -> fa{i}.B;  # Error: bit 8 doesn't exist
        }
    }
}
```

## Using Constants

Constants can be used in connections like any signal. Individual bits can be accessed with indexing.

```
component Compare100(A[8]) -> (Equal) {
    >i[8]{
        xor{i}: XOR;
    }
    or1: Or8Inputs;
    not1: NOT;

    OneHundred[8] = 100;

    connect {
        >i[8]{
            A[{i}] -> xor{i}.A;
            OneHundred[{i}] -> xor{i}.B;  # Access each bit
            xor{i}.O -> or1.A[{i}];
        }
        or1.Out -> not1.A;
        not1.O -> Equal;
    }
}
```

## Bit Indexing on Constants

```
MyConst = 0b1010;    # 4-bit constant
# MyConst[1] = 0 (LSB)
# MyConst[2] = 1
# MyConst[3] = 0
# MyConst[4] = 1 (MSB)
```

Remember: Bit 1 is always the LSB (rightmost bit in binary representation).
