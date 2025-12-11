---
sidebar_position: 3
---

# Base SHDL

Base SHDL is the canonical, minimal representation of an SHDL circuit. It serves as the intermediate representation between the high-level Expanded SHDL and the generated C code.

## What is Base SHDL?

Base SHDL contains:
- Only primitive gates (`AND`, `OR`, `NOT`, `XOR`)
- Power pins (`__VCC__`, `__GND__`)
- Explicit single-bit connections
- No hierarchy, no abstractions

It's what your SHDL code becomes after flattening, and what the compiler uses to generate C code.

## Primitive Gates

Base SHDL has exactly **6 primitive types**:

### Logic Gates

| Gate | Inputs | Output | Operation |
|------|--------|--------|-----------|
| `AND` | A, B | O | O = A ∧ B |
| `OR` | A, B | O | O = A ∨ B |
| `NOT` | A | O | O = ¬A |
| `XOR` | A, B | O | O = A ⊕ B |

### Power Pins

| Pin | Output | Purpose |
|-----|--------|---------|
| `__VCC__` | O | Constant logic HIGH (1) |
| `__GND__` | O | Constant logic LOW (0) |

### Port Naming Convention

All primitives follow consistent port naming:
- **Inputs:** `A`, `B` (uppercase letters)
- **Output:** `O` (letter O, uppercase)

For `NOT`, `__VCC__`, and `__GND__`, only relevant ports exist:
- `NOT`: input `A`, output `O`
- `__VCC__`: output `O` only
- `__GND__`: output `O` only

:::info Why These Four Gates?
The four logic gates (`AND`, `OR`, `NOT`, `XOR`) were chosen because they map directly to C bitwise operations (`&`, `|`, `~`, `^`), enabling highly efficient code generation.

NAND and NOR are not primitives—they can be constructed:
- NAND: `NOT(AND(A, B))`
- NOR: `NOT(OR(A, B))`
:::

## Grammar

```ebnf
component       = "component" IDENT "(" port_list ")" "->" "(" port_list ")" "{" 
                  instance_list 
                  connect_block 
                  "}" ;

port_list       = port { "," port } ;
port            = IDENT [ "[" NUMBER "]" ] ;

instance_list   = { instance_decl } ;
instance_decl   = IDENT ":" primitive_type ";" ;

primitive_type  = "AND" | "OR" | "NOT" | "XOR" 
                | "__VCC__" | "__GND__" ;

connect_block   = "connect" "{" { connection } "}" ;
connection      = signal "->" signal ";" ;

signal          = port_ref | instance_port ;
port_ref        = IDENT [ "[" NUMBER "]" ] ;
instance_port   = IDENT "." IDENT ;
```

## Key Constraints

1. **No nested components** - All instances must be primitive gates or power pins
2. **No generators** - All repetition is explicitly written out
3. **No expanders** - All bit indices are explicit single numbers
4. **No constants** - Only `__VCC__` and `__GND__` instances
5. **No comments** - Pure structural description
6. **Single component** - One component per flattened output

## Instance Declarations

Instances are declared in the component body, before the `connect` block:

```
<instance_name>: <PrimitiveType>;
```

### Examples

```
x1: XOR;
a1: AND;
n1: NOT;
vcc_bit: __VCC__;
gnd_bit: __GND__;
```

### Naming Patterns

Instance names in flattened Base SHDL follow patterns from the flattening process:

| Pattern | Example | Source |
|---------|---------|--------|
| Simple | `x1`, `a1`, `n1` | Direct instances |
| Hierarchy-flattened | `fa1_x1`, `fa2_a1` | From subcomponents |
| Constant bits | `Hundred_bit3` | From constants |

## Connections

All connections are declared inside the `connect` block:

```
connect {
    <source> -> <destination>;
    ...
}
```

### Signal References

| Format | Meaning |
|--------|---------|
| `PortName` | Single-bit component port |
| `PortName[N]` | Bit N of multi-bit component port |
| `instance.Port` | Port of a primitive instance |

### Examples

```
A -> x1.A;           # Component input to gate input
A[1] -> fa1.A;       # Bit 1 of multi-bit input
x1.O -> x2.A;        # Gate output to gate input
fa1_x2.O -> Sum[1];  # Gate output to component output bit
```

## Complete Example

A 2-bit adder in Base SHDL:

```
component Add2(A[2], B[2], Cin) -> (Sum[2], Cout) {
    # Full adder 1
    fa1_x1: XOR;
    fa1_x2: XOR;
    fa1_a1: AND;
    fa1_a2: AND;
    fa1_o1: OR;
    
    # Full adder 2
    fa2_x1: XOR;
    fa2_x2: XOR;
    fa2_a1: AND;
    fa2_a2: AND;
    fa2_o1: OR;

    connect {
        # Full adder 1
        A[1] -> fa1_x1.A;
        B[1] -> fa1_x1.B;
        fa1_x1.O -> fa1_x2.A;
        Cin -> fa1_x2.B;
        fa1_x2.O -> Sum[1];
        
        A[1] -> fa1_a1.A;
        B[1] -> fa1_a1.B;
        fa1_x1.O -> fa1_a2.A;
        Cin -> fa1_a2.B;
        fa1_a1.O -> fa1_o1.A;
        fa1_a2.O -> fa1_o1.B;
        
        # Full adder 2
        A[2] -> fa2_x1.A;
        B[2] -> fa2_x1.B;
        fa2_x1.O -> fa2_x2.A;
        fa1_o1.O -> fa2_x2.B;  # Carry from FA1
        fa2_x2.O -> Sum[2];
        
        A[2] -> fa2_a1.A;
        B[2] -> fa2_a1.B;
        fa2_x1.O -> fa2_a2.A;
        fa1_o1.O -> fa2_a2.B;
        fa2_a1.O -> fa2_o1.A;
        fa2_a2.O -> fa2_o1.B;
        fa2_o1.O -> Cout;
    }
}
```

## Semantic Rules

### Connection Rules

1. **Single driver** - Each input should have exactly one source
2. **Fan-out allowed** - A single source can drive multiple destinations
3. **No floating inputs** - All primitive inputs must be connected
4. **No floating outputs** - Component outputs must be driven

### Type Consistency

1. All connections are single-bit
2. Multi-bit ports are accessed bit-by-bit using `[N]` indexing
3. Bit indices must be within range: `1 ≤ N ≤ width`

### Instance Uniqueness

Each instance name must be unique within a component.

## Using the Flattener

You can generate Base SHDL from Expanded SHDL using PySHDL:

```python
from SHDL import flatten_file, format_base_shdl

# Flatten to Base SHDL
base_shdl = flatten_file("adder16.shdl", component="Adder16")
print(base_shdl)
```

Or from the command line:

```bash
pyshdl flatten adder16.shdl -c Adder16 -o adder16_flat.shdl
```
