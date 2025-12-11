---
sidebar_position: 4
---

# Signals

Signals represent wires that carry digital values between components.

## Single-bit Signals

The default signal type. Carries a single bit (0 or 1).

```
component SimpleGate(A, B) -> (Out) {
    # A, B, and Out are all single-bit signals
}
```

## Multi-bit Signals (Vectors)

Declared with bit width in square brackets. Represent a bus of parallel wires.

```
component DataPath(Data[16], Address[8]) -> (Result[16]) {
    # Data and Result are 16-bit vectors
    # Address is an 8-bit vector
}
```

## Bit Indexing

Access individual bits of a vector using bracket notation.

### Rules

- Indexing is **1-based** (not 0-based)
- Index 1 is the LSB (least significant bit)
- Index N is the MSB for an N-bit signal

```
Signal[1]     # LSB (bit 1)
Signal[8]     # Bit 8 (MSB for 8-bit signal)
Data[16]      # MSB of 16-bit Data
```

### Example

```
component BitExtract(In[8]) -> (Low, High) {
    connect {
        In[1] -> Low;    # Extract LSB
        In[8] -> High;   # Extract MSB
    }
}
```

## Bit Slicing (Expanders)

Expanders provide a simple way to connect contiguous ranges of bits in a single statement.

### Syntax

```
Signal[start:end]    # Bits from start to end (inclusive)
Signal[:N]           # Bits 1 to N
Signal[N:]           # Bits N to the signal's width
```

### How Expanders Work

An expander automatically creates one connection per bit in the range:

```
# This expander:
In[:4] -> Out[:4];

# Is equivalent to these 4 connections:
In[1] -> Out[1];
In[2] -> Out[2];
In[3] -> Out[3];
In[4] -> Out[4];
```

### Example

```
component SplitByte(In[8]) -> (LowNibble[4], HighNibble[4]) {
    connect {
        In[:4] -> LowNibble;     # Bits 1-4
        In[5:8] -> HighNibble;   # Bits 5-8
    }
}
```

### Limitations of Expanders

- Only work in connections (not for creating instances)
- Cannot perform arithmetic or complex transformations
- Cannot be nested
- Only handle contiguous bit ranges

For more complex repetitive patterns, use [Generators](./generators).

## Expanders vs Generators

| Feature | Expanders | Generators |
|---------|-----------|------------|
| Syntax | `Signal[1:8]` | `>i[8]{ ... }` |
| Use in connections | ✓ | ✓ |
| Use in declarations | ✗ | ✓ |
| Arithmetic | ✗ | ✓ (`{i+1}`, `{i*2}`) |
| Nesting | ✗ | ✓ |
| Non-contiguous ranges | ✗ | ✓ (`[1:4, 8, 12:]`) |
| Complexity | Simple | Powerful |
