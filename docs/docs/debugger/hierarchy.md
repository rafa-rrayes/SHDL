---
sidebar_position: 6
---

# Hierarchy Navigation

SHDL circuits are hierarchical - components instantiate other components. SHDB lets you navigate this hierarchy to debug at any level of abstraction.

## Understanding Hierarchy

Consider a 16-bit adder built from full adders:

```
Adder16
├── fa1: FullAdder
│   ├── x1: XOR
│   ├── x2: XOR
│   ├── a1: AND
│   ├── a2: AND
│   └── o1: OR
├── fa2: FullAdder
│   └── ...
├── fa3: FullAdder
│   └── ...
└── ... (13 more)
```

Each FullAdder is an instance of the FullAdder component.

## Viewing Hierarchy

### hierarchy Command

```
(shdb) hierarchy
Adder16
├── fa1: FullAdder (5 gates)
│   ├── x1: XOR
│   ├── x2: XOR
│   ├── a1: AND
│   ├── a2: AND
│   └── o1: OR
├── fa2: FullAdder (5 gates)
│   ├── x1: XOR
│   ├── x2: XOR
│   ├── a1: AND
│   ├── a2: AND
│   └── o1: OR
└── ... (14 more instances)
```

### Limiting Depth

```
(shdb) hierarchy --depth 1
Adder16
├── fa1: FullAdder (5 gates)
├── fa2: FullAdder (5 gates)
├── fa3: FullAdder (5 gates)
└── ... (13 more instances)
```

### Filtering

```
(shdb) hierarchy fa1
Adder16/fa1: FullAdder
├── x1: XOR
├── x2: XOR
├── a1: AND
├── a2: AND
└── o1: OR
```

## Navigating with Scope

The `scope` command changes your current location in the hierarchy.

### Entering a Scope

```
(shdb) scope fa1
Current scope: Adder16/fa1

(shdb) where
Adder16/fa1
```

### Relative References

Once in a scope, references are relative:

```
(shdb) scope fa1
(shdb) print x1.O           # Same as fa1.x1.O
x1.O = 1

(shdb) print A              # Instance input (from parent)
A = 1

(shdb) print Sum            # Instance output
Sum = 0
```

### Moving Up

```
(shdb) scope ..             # Parent scope
Current scope: Adder16

(shdb) scope /              # Root scope
Current scope: Adder16
```

### Absolute Paths

Use `/` prefix for absolute paths:

```
(shdb) scope fa1
(shdb) print /A             # Top-level A, not fa1.A
/A = 42

(shdb) print /fa2.x1.O      # Other instance
/fa2.x1.O = 0
```

### Nested Scopes

```
(shdb) scope fa1
(shdb) scope x1             # Not typically needed (x1 is a gate)
Error: x1 is a primitive gate, not a component instance

(shdb) scope /cpu/alu       # For deeply nested designs
Current scope: CPU/alu
```

## Hierarchy Information

### Instance Details

```
(shdb) info instance fa1
Instance: fa1
  Type: FullAdder
  Parent: Adder16
  Source: adder16.shdl:8
  Gates: 5 (x1, x2, a1, a2, o1)
  Ports:
    A <- Adder16.A[1]
    B <- Adder16.B[1]
    Cin <- (internal)
    Sum -> Adder16.Sum[1]
    Cout -> fa2.Cin
```

### All Instances

```
(shdb) info instances
Instances in Adder16:
  fa1: FullAdder (line 8)
  fa2: FullAdder (line 8)
  fa3: FullAdder (line 8)
  ...
```

### Instance Types

```
(shdb) info types
Component types used:
  FullAdder: 16 instances (80 gates)
  (primitives): 80 gates total
    XOR: 32
    AND: 32
    OR: 16
```

## Source Mapping

### Viewing Source

```
(shdb) list
Showing source for current scope (Adder16):

   5: COMPONENT Adder16(A[16], B[16], Cin -> Sum[16], Cout)
   6:   // 16-bit ripple carry adder
   7:   
   8:   fa1 = FullAdder(A[1], B[1], Cin)
   9:   fa2 = FullAdder(A[2], B[2], fa1.Cout)
  10:   fa3 = FullAdder(A[3], B[3], fa2.Cout)
  ...
```

### Source at Instance

```
(shdb) scope fa1
(shdb) list

Showing source for FullAdder (fa1):

   1: COMPONENT FullAdder(A, B, Cin -> Sum, Cout)
   2:   x1 = XOR(A, B)
   3:   x2 = XOR(x1.O, Cin)      // Sum output
   4:   a1 = AND(A, B)
   5:   a2 = AND(x1.O, Cin)
   6:   o1 = OR(a1.O, a2.O)      // Carry output
   7:   Sum = x2.O
   8:   Cout = o1.O
```

### Finding Source for a Gate

```
(shdb) info gate fa1_x1
Gate: fa1_x1
  Type: XOR
  Source: fullAdder.shdl:2
  
(shdb) list fullAdder.shdl:2
   1: COMPONENT FullAdder(A, B, Cin -> Sum, Cout)
>  2:   x1 = XOR(A, B)
   3:   x2 = XOR(x1.O, Cin)
```

## Hierarchical Paths

### Path Syntax

```
Adder16                     # Top component
Adder16/fa1                 # Instance fa1
Adder16/fa1/x1              # Gate x1 in fa1
Adder16/fa1.Sum             # Port Sum of fa1
```

### Gates from Line

Find all gates that came from a source line:

```
(shdb) info line adder16.shdl:8
Line 8 generated:
  fa1_x1, fa1_x2, fa1_a1, fa1_a2, fa1_o1
  
(shdb) info line fullAdder.shdl:2
Line 2 generated:
  fa1_x1, fa2_x1, fa3_x1, ... (16 gates)
```

## Debugging in Hierarchy

### Breakpoints with Hierarchy

```
(shdb) break fa1.Cout           # Instance output
(shdb) break fa1.o1.O           # Internal gate
(shdb) break /fa8.Cout          # Absolute path
```

### Watching Carry Chain

```
(shdb) scope /

# Watch carry propagation through adder
(shdb) watch fa1.Cout
(shdb) watch fa2.Cout
(shdb) watch fa3.Cout
(shdb) watch fa4.Cout

(shdb) set A = 0xFFFF
(shdb) set B = 1
(shdb) step

Watchpoint 1 hit: fa1.Cout changed 0 -> 1
Watchpoint 2 hit: fa2.Cout changed 0 -> 1
...
```

### Comparing Instances

```
(shdb) print fa1.x1.O fa2.x1.O fa3.x1.O fa4.x1.O
fa1.x1.O = 1, fa2.x1.O = 0, fa3.x1.O = 1, fa4.x1.O = 0
```

## Flattened vs Hierarchical Names

SHDB understands both:

| Hierarchical | Flattened |
|--------------|-----------|
| `fa1.x1` | `fa1_x1` |
| `fa1.x1.O` | `fa1_x1.O` |
| `cpu.alu.adder.fa1.x1` | `cpu_alu_adder_fa1_x1` |

```
(shdb) print fa1.x1.O
fa1.x1.O = 1

(shdb) print fa1_x1.O
fa1_x1.O = 1
```

The hierarchical form is more readable; the flattened form matches what's in the generated C code.

## Practical Examples

### Tracing Signal Through Hierarchy

```
(shdb) # Follow bit 1 through the adder
(shdb) print A[1] B[1]
A[1] = 1, B[1] = 1

(shdb) scope fa1
(shdb) print A B Cin
A = 1, B = 1, Cin = 0

(shdb) print x1.O           # A XOR B
x1.O = 0

(shdb) print a1.O           # A AND B  
a1.O = 1

(shdb) print o1.O           # Carry out
o1.O = 1

(shdb) print Sum Cout
Sum = 0, Cout = 1
```

### Finding Broken Instance

```
(shdb) # Test each full adder
(shdb) for $i in 1..16
> scope fa$i
> if Sum != ((../A[$i] ^ ../B[$i]) ^ Cin)
>   print "Mismatch in fa" $i
> end
> scope ..
> end
```
