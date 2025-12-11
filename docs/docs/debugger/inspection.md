---
sidebar_position: 4
---

# Signal Inspection

SHDB provides powerful signal inspection capabilities, from simple value reads to complex expressions and internal gate access.

## Signal Path Syntax

### Basic Signals

```
A                   # Input port A
Sum                 # Output port Sum
```

### Bit Slicing

SHDL uses 1-based indexing:

```
A[1]                # First bit of A
A[16]               # 16th bit of A
A[1:8]              # Bits 1 through 8
A[8:16]             # Upper half of 16-bit signal
```

### Instance Ports

Access signals within component instances:

```
fa1.A               # Input A of instance fa1
fa1.Sum             # Output Sum of instance fa1
fa2.Cin             # Input Cin of instance fa2
```

### Gate Outputs

Every gate has an output `.O`:

```
fa1.x1.O            # Output of gate x1 in instance fa1
fa1_x1.O            # Same gate using flattened name
x1.O                # Relative to current scope (if in fa1)
```

### Nested Hierarchy

For deeply nested designs:

```
top.sub1.sub2.gate1.O
```

### Raw Internal Access (Advanced)

Access internal C state directly:

```
$XOR_O_0            # Raw XOR output chunk
$AND_O_0            # Raw AND output chunk
$state              # Full state structure
```

## Print Formats

### Decimal (Default)

```
(shdb) print Sum
Sum = 59
```

### Hexadecimal

```
(shdb) print/x Sum
Sum = 0x003B

(shdb) print/x A B Sum
A = 0x002A, B = 0x0011, Sum = 0x003B
```

### Binary

```
(shdb) print/b Sum
Sum = 0b0000000000111011

(shdb) print/b Cout
Cout = 0b0
```

### Table Format

Best for multiple signals:

```
(shdb) print/t A B Sum Cout
┌────────┬──────────────────┬─────────┐
│ Signal │ Hex              │ Decimal │
├────────┼──────────────────┼─────────┤
│ A      │ 0x002A           │ 42      │
│ B      │ 0x0011           │ 17      │
│ Sum    │ 0x003B           │ 59      │
│ Cout   │ 0x0              │ 0       │
└────────┴──────────────────┴─────────┘
```

## Expressions

### Arithmetic

```
(shdb) print A + B
A + B = 59

(shdb) print A - B
A - B = 25

(shdb) print A * 2
A * 2 = 84
```

### Bitwise Operations

```
(shdb) print A & B
A & B = 0

(shdb) print A | B
A | B = 59

(shdb) print A ^ B
A ^ B = 59

(shdb) print ~A
~A = 65493

(shdb) print A << 2
A << 2 = 168

(shdb) print Sum >> 4
Sum >> 4 = 3
```

### Comparisons

```
(shdb) print A == B
A == B = false

(shdb) print A > B
A > B = true

(shdb) print Sum == (A + B)
Sum == (A + B) = true
```

### Masking

```
(shdb) print Sum & 0xFF
Sum & 0xFF = 59

(shdb) print (A + B) & 0xFFFF
(A + B) & 0xFFFF = 59
```

## Debugger Variables

Store values for later use:

```
(shdb) set $expected = A + B
(shdb) step
(shdb) print Sum == $expected
Sum == $expected = true

(shdb) set $mask = 0xFF
(shdb) print Sum & $mask
Sum & $mask = 59
```

Built-in variables:

| Variable | Description |
|----------|-------------|
| `$cycle` | Current cycle count |
| `$pc` | Program counter (if applicable) |
| `$_` | Last printed value |

## Wildcards and Batch Inspection

### All Ports

```
(shdb) print *
A = 42, B = 17, Cin = 0, Sum = 59, Cout = 0
```

### Instance Wildcard

```
(shdb) print fa1.*
fa1.A = 1, fa1.B = 1, fa1.Cin = 0, fa1.Sum = 1, fa1.Cout = 1
```

### Gate Patterns

```
(shdb) print /gates fa1*
fa1_x1 = 1
fa1_x2 = 1
fa1_a1 = 0
fa1_a2 = 1
fa1_o1 = 1
```

## Inspecting Gates

### Listing Gates

```
(shdb) info gates
Gates (356 total):
  XOR: 32 gates
  AND: 32 gates
  OR:  16 gates
  NOT: 0 gates
  VCC: 16 gates
  GND: 0 gates
```

### Filtered Listing

```
(shdb) info gates fa1*
Gates matching 'fa1*':
  fa1_x1: XOR, output=1
  fa1_x2: XOR, output=1
  fa1_a1: AND, output=0
  fa1_a2: AND, output=1
  fa1_o1: OR,  output=1
```

### Gate Details

```
(shdb) info gate fa1_x1
Gate: fa1_x1
  Type: XOR
  Output: 1
  Hierarchy: Adder16/fa1/x1
  Source: fullAdder.shdl:3
  Lane: 0, Chunk: 0
```

## Scope-Relative References

When you enter a scope, references become relative:

```
(shdb) scope fa1
Current scope: Adder16/fa1

(shdb) print x1.O           # Same as fa1.x1.O
x1.O = 1

(shdb) print A              # Same as fa1.A (instance input)
A = 1

(shdb) print ../A           # Parent's A (top-level input)
../A = 42
```

## Signal Information

### Port Widths

```
(shdb) info signal A
Signal: A
  Type: Input
  Width: 16 bits
  Current value: 42 (0x002A)
  Source: adder16.shdl:5
```

### Signal Connections

```
(shdb) info connections A
Signal A connects to:
  -> fa1.A (bit 1)
  -> fa2.A (bit 2)
  -> fa3.A (bit 3)
  ...
```

## Examples

### Debugging an Adder

```
(shdb) set A = 0xFF
(shdb) set B = 0x01
(shdb) step
(shdb) print/t A B Sum Cout
┌────────┬──────────────────┬─────────┐
│ Signal │ Hex              │ Decimal │
├────────┼──────────────────┼─────────┤
│ A      │ 0x00FF           │ 255     │
│ B      │ 0x0001           │ 1       │
│ Sum    │ 0x0100           │ 256     │
│ Cout   │ 0x0              │ 0       │
└────────┴──────────────────┴─────────┘
```

### Tracing Through Gates

```
(shdb) set A = 1
(shdb) set B = 1
(shdb) step

(shdb) print A B                    # Inputs
A = 1, B = 1

(shdb) print fa1.x1.O               # First XOR
fa1.x1.O = 0                        # 1 XOR 1 = 0

(shdb) print fa1.a1.O               # First AND
fa1.a1.O = 1                        # 1 AND 1 = 1

(shdb) print Cout
Cout = 1                            # Carry out
```

### Finding Signal Dependencies

```
(shdb) info gates *o1*              # All OR gates (carry chain)
fa1_o1: OR, output=1
fa2_o1: OR, output=0
fa3_o1: OR, output=0
...
```
