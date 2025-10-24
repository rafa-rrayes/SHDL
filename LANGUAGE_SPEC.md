# SHDL Language Specification

**Version 1.0**  
**Simple Hardware Description Language**

## Table of Contents

1. [Introduction](#introduction)
2. [Lexical Elements](#lexical-elements)
3. [Component Structure](#component-structure)
4. [Data Types](#data-types)
5. [Imports](#imports)
6. [Instances](#instances)
7. [Connections](#connections)
8. [Generators](#generators)
9. [Standard Gates](#standard-gates)
10. [Examples](#examples)

## Introduction

SHDL (Simple Hardware Description Language) is a domain-specific language for describing digital circuits. It emphasizes:

- **Simplicity** - Minimal syntax for maximum clarity
- **Hierarchy** - Build complex circuits from simple components
- **Reusability** - Import and compose components
- **Vectors** - First-class support for multi-bit signals

## Lexical Elements

### Comments

```shdl
# This is a single-line comment
```

Comments begin with `#` and continue to the end of the line.

### Identifiers

Identifiers must:
- Start with a letter (a-z, A-Z)
- Contain only letters, digits, and underscores
- Be case-sensitive

Examples:
```shdl
validName
gate1
my_component
ALU_8bit
```

### Keywords

Reserved keywords:
- `component`
- `use`
- `connect`

### Operators

- `->` : Connection operator
- `::` : Module scope operator
- `{}` : Braces for grouping
- `[]` : Brackets for bit indexing and generators
- `:` : Instance type declaration
- `;` : Statement terminator
- `,` : Separator

## Component Structure

### Syntax

```shdl
component ComponentName(input_ports) -> (output_ports) {
    instance_declarations
    
    connect {
        connection_statements
    }
}
```

### Component Declaration

```shdl
component <name>(<inputs>) -> (<outputs>) { ... }
```

- **name**: Component identifier
- **inputs**: Comma-separated list of input ports
- **outputs**: Comma-separated list of output ports

### Example

```shdl
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    # Component body
}
```

## Data Types

### Single-bit Signals

Default port type. Represents a single wire carrying 0 or 1.

```shdl
component MyGate(A, B) -> (Out) {
    # A, B, Out are all 1-bit signals
}
```

### Multi-bit Signals (Vectors)

Declare with bit width in square brackets:

```shdl
component Adder8(A[8], B[8]) -> (Sum[8]) {
    # A, B, Sum are 8-bit vectors
}
```

**Bit Indexing:**
- Indexing is 1-based
- `Signal[1]` refers to the least significant bit (LSB)
- `Signal[N]` refers to the most significant bit for N-bit signal

```shdl
A[1]    # LSB of A
A[8]    # MSB of 8-bit A
```

## Imports

### Syntax

```shdl
use <module>::{<component1>, <component2>, ...};
```

### Standard Gates Module

```shdl
use stdgates::{AND, OR, NOT, XOR, NAND, NOR, XNOR};
```

Available standard gates:
- `AND` - Two-input AND gate
- `OR` - Two-input OR gate
- `NOT` - Single-input inverter
- `XOR` - Two-input XOR gate
- `NAND` - Two-input NAND gate
- `NOR` - Two-input NOR gate
- `XNOR` - Two-input XNOR gate

### Custom Component Imports

```shdl
use fullAdder::{FullAdder};
use myModule::{ComponentA, ComponentB, ComponentC};
```

Import paths:
- Module name corresponds to filename (without `.shdl` extension)
- Searches in current directory and include paths specified with `-I`

## Instances

### Syntax

```shdl
<instance_name>: <ComponentType>;
```

### Examples

```shdl
gate1: AND;
adder: FullAdder;
reg0: Register8;
```

Multiple instances of the same type:

```shdl
and1: AND;
and2: AND;
and3: AND;
```

## Connections

### Connect Block

All connections must be within a `connect` block:

```shdl
connect {
    # connection statements
}
```

### Connection Syntax

```shdl
<source> -> <destination>;
```

### Types of Connections

#### Input to Instance Port

```shdl
A -> gate1.A;
B -> gate1.B;
```

#### Instance Output to Instance Input

```shdl
gate1.O -> gate2.A;
```

#### Instance Output to Component Output

```shdl
gate2.O -> Result;
```

#### Bit-indexed Connections

```shdl
DataBus[1] -> gate.A;      # LSB
DataBus[8] -> gate.B;      # MSB
```

### Port Names

Standard port names for gates:
- **Inputs**: `A`, `B` (two-input gates), `A` (NOT gate)
- **Output**: `O` (for standard gates)
- **Custom**: Component-defined port names

### Complete Example

```shdl
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

## Generators

Generators create repetitive structures using loop syntax.

### Syntax

```shdl
>variable[range]{
    # repeated content
}
```

### Range Formats

**1 to N:**
```shdl
>i[8]{
    # Creates iterations with i = 1, 2, 3, 4, 5, 6, 7, 8
}
```

**Start to End:**
```shdl
>i[4, 10]{
    # Creates iterations with i = 4, 5, 6, 7, 8, 9, 10
}
```

### Variable Substitution

Use `{variable}` to substitute the loop variable:

```shdl
>i[4]{
    gate{i}: AND;      # Creates: gate1, gate2, gate3, gate4
}
```

### Generator in Instance Declarations

```shdl
>i[8]{
    and{i}: AND;
    or{i}: OR;
}
# Creates: and1, and2, ..., and8, or1, or2, ..., or8
```

### Generator in Connections

```shdl
connect {
    >i[8]{
        In[{i}] -> gate{i}.A;
        gate{i}.O -> Out[{i}];
    }
}
```

### Complete Example: 8-bit Register

```shdl
use stdgates::{AND, NOR, NOT};

component ByteReg(In[8], clk) -> (Out[8]) {
    >i[8]{
        a1{i}: AND;
        a2{i}: AND;
        not1{i}: NOT;
        nor1{i}: NOR;
        nor2{i}: NOR;
    }
    
    connect {
        >i[8]{
            In[{i}] -> a1{i}.A;
            In[{i}] -> not1{i}.A;
            not1{i}.O -> a2{i}.A;
            
            clk -> a1{i}.B;
            clk -> a2{i}.B;
            
            a1{i}.O -> nor1{i}.A;
            a2{i}.O -> nor2{i}.A;
            nor1{i}.O -> nor2{i}.B;
            nor2{i}.O -> nor1{i}.B;
            nor2{i}.O -> Out[{i}];
        }
    }
}
```

## Standard Gates

### AND Gate

**Ports:** `A`, `B` (inputs), `O` (output)  
**Function:** Output is 1 if both inputs are 1

```shdl
and1: AND;
connect {
    In1 -> and1.A;
    In2 -> and1.B;
    and1.O -> Out;
}
```

### OR Gate

**Ports:** `A`, `B` (inputs), `O` (output)  
**Function:** Output is 1 if either input is 1

```shdl
or1: OR;
```

### NOT Gate

**Ports:** `A` (input), `O` (output)  
**Function:** Output is the inverse of input

```shdl
not1: NOT;
connect {
    In -> not1.A;
    not1.O -> Out;
}
```

### XOR Gate

**Ports:** `A`, `B` (inputs), `O` (output)  
**Function:** Output is 1 if inputs differ

```shdl
xor1: XOR;
```

### NAND Gate

**Ports:** `A`, `B` (inputs), `O` (output)  
**Function:** Output is 0 only if both inputs are 1

```shdl
nand1: NAND;
```

### NOR Gate

**Ports:** `A`, `B` (inputs), `O` (output)  
**Function:** Output is 1 only if both inputs are 0

```shdl
nor1: NOR;
```

### XNOR Gate

**Ports:** `A`, `B` (inputs), `O` (output)  
**Function:** Output is 1 if inputs are the same

```shdl
xnor1: XNOR;
```

## Examples

### Half Adder

```shdl
use stdgates::{XOR, AND};

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

### Full Adder

```shdl
use stdgates::{XOR, AND, OR};

component FullAdder(A, B, Cin) -> (Sum, Cout) {
    x1: XOR;
    a1: AND;
    x2: XOR;
    a2: AND;
    o1: OR;

    connect {
        A -> x1.A;
        B -> x1.B;
        A -> a1.A;
        B -> a1.B;
        
        x1.O -> x2.A;
        Cin -> x2.B;
        x1.O -> a2.A;
        Cin -> a2.B;
        
        a1.O -> o1.A;
        a2.O -> o1.B;
        
        x2.O -> Sum;
        o1.O -> Cout;
    }
}
```

### 4-bit Ripple Carry Adder

```shdl
use fullAdder::{FullAdder};

component Adder4(A[4], B[4], Cin) -> (Sum[4], Cout) {
    >i[4]{
        fa{i}: FullAdder;
    }
    
    connect {
        # First adder
        A[1] -> fa1.A;
        B[1] -> fa1.B;
        Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];
        
        # Middle adders
        >i[2, 3]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;
            fa{i}.Sum -> Sum[{i}];
        }
        
        # Last adder
        A[4] -> fa4.A;
        B[4] -> fa4.B;
        fa3.Cout -> fa4.Cin;
        fa4.Sum -> Sum[4];
        fa4.Cout -> Cout;
    }
}
```

## Grammar Reference

```ebnf
program          ::= import* component

import           ::= 'use' identifier '::' '{' identifier_list '}' ';'

component        ::= 'component' identifier '(' port_list ')' '->' '(' port_list ')' '{' 
                     instance_list 
                     connect_block 
                     '}'

port_list        ::= (port (',' port)*)?

port             ::= identifier ('[' number ']')?

instance_list    ::= (generator | instance)*

instance         ::= identifier ':' identifier ';'

generator        ::= '>' identifier '[' range ']' '{' (generator | instance | connection)* '}'

range            ::= number | number ',' number

connect_block    ::= 'connect' '{' (generator | connection)* '}'

connection       ::= signal '->' signal ';'

signal           ::= identifier ('.' identifier)? ('[' (number | '{' identifier '}') ']')?

identifier_list  ::= identifier (',' identifier)*

identifier       ::= [a-zA-Z][a-zA-Z0-9_]*

number           ::= [0-9]+
```

## Best Practices

1. **Use meaningful names** - `fullAdder` not `fa`, `dataRegister` not `reg`
2. **Group related instances** - Use generators for repetitive patterns
3. **Comment complex logic** - Explain non-obvious connections
4. **One component per file** - Match filename to component name
5. **Consistent port naming** - Use standard names (A, B, O) for gates
6. **Hierarchical design** - Break complex circuits into smaller components

## Limitations

- No tri-state logic
- No bidirectional ports
- No conditional logic (if/else)
- No arithmetic operators (use components instead)
- No concurrent assignments outside connect block
- No timing or delay specifications
