---
sidebar_position: 5
---

# Connections

Connections define how signals flow between ports, instances, and constants.

## Connect Block

All connections must be inside a `connect` block:

```
connect {
    # Connection statements here
}
```

A component must have exactly one `connect` block.

## Connection Syntax

```
<source> -> <destination>;
```

The arrow `->` indicates signal flow from source to destination.

### Valid Sources

- Component input ports
- Instance output ports
- Constants
- Bit-indexed or sliced versions of the above

### Valid Destinations

- Component output ports
- Instance input ports
- Bit-indexed or sliced versions of the above

## Connection Patterns

### Input to Instance

```
A -> gate1.A;
B -> gate1.B;
```

### Instance to Instance

```
gate1.O -> gate2.A;
xor1.O -> and1.B;
```

### Instance to Output

```
gate2.O -> Result;
adder.Sum -> Sum;
```

### Bit-indexed Connections

```
DataBus[1] -> gate.A;      # Single bit
DataBus[8] -> gate.B;
gate.O -> Result[1];
```

### Slice Connections

```
Input[:4] -> LowNibble;    # Bits 1-4
Input[5:8] -> HighNibble;  # Bits 5-8
```

### Constant to Instance

```
MASK[1] -> and1.A;
Zero[{i}] -> gate{i}.B;
```

## Complete Example

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

## Connection Rules

### Single Driver Rule

Each input can only be driven by one source. This is invalid:

```
# ERROR: Two sources driving the same input
A -> gate1.A;
B -> gate1.A;  # Error!
```

### Multiple Destinations

A single source can drive multiple destinations:

```
A -> gate1.A;
A -> gate2.A;  # OK - A drives both gates
A -> and1.B;   # OK - fan-out is allowed
```

### Connection Order

The order of connections in the connect block does not affect behavior. Connections are evaluated concurrently, just like real hardware.

```
connect {
    # These are equivalent orderings:
    A -> xor1.A;
    B -> xor1.B;
    xor1.O -> Sum;
    
    # Same as:
    xor1.O -> Sum;
    B -> xor1.B;
    A -> xor1.A;
}
```
