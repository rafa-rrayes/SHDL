---
sidebar_position: 3
---

# Components

Components are the fundamental building blocks in SHDL. Each component defines a reusable circuit module with inputs, outputs, and internal logic.

## Component Declaration

```
component <name>(<input_ports>) -> (<output_ports>) {
    <body>
}
```

**Parts:**
- `<name>`: Component identifier (PascalCase recommended)
- `<input_ports>`: Comma-separated list of input port declarations
- `<output_ports>`: Comma-separated list of output port declarations
- `<body>`: Instance declarations, constants, and connect block

## Ports

Ports define the interface of a component.

### Single-bit Ports

```
component MyGate(A, B) -> (Out) { ... }
```

### Multi-bit Ports (Vectors)

```
component Adder8(A[8], B[8], Cin) -> (Sum[8], Cout) { ... }
```

### Port Naming Conventions

- Use meaningful names (`DataIn`, `Clock`, `Enable`)
- Standard gates use `A`, `B` for inputs and `O` for output

## Component Body

The body contains:
1. Instance declarations
2. Constant declarations
3. A `connect` block

### Example

```
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    # Instance declarations
    xor1: XOR;
    xor2: XOR;
    and1: AND;
    and2: AND;
    or1: OR;
    
    connect {
        # Connection statements
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

## Instances

Instances are concrete occurrences of components within another component.

### Instance Declaration

```
<instance_name>: <ComponentType>;
```

**Examples:**

```
gate1: AND;
adder: FullAdder;
reg0: Register8;
```

### Multiple Instances

You can declare multiple instances on one line:

```
and1: AND; and2: AND; and3: AND;
```

Or use generators for multiple instances:

```
>i[8]{
    gate{i}: AND;
}
# Creates: gate1, gate2, gate3, gate4, gate5, gate6, gate7, gate8
```

### Port Access

Access instance ports using dot notation:

```
<instance>.<port>
```

**Examples:**

```
gate1.A      # Input A of gate1
gate1.B      # Input B of gate1
gate1.O      # Output O of gate1
adder.Sum    # Sum output of adder
adder.Cout   # Carry output of adder
```

**With bit indexing:**

```
adder.Sum[1]     # LSB of adder's Sum output
register.Data[8] # Bit 8 of register's Data port
```

## Complete Example

Here's a complete 2-to-1 multiplexer:

```
component Mux2(A, B, Sel) -> (Out) {
    not1: NOT;
    and1: AND;
    and2: AND;
    or1: OR;
    
    connect {
        # Invert selection signal
        Sel -> not1.A;
        
        # Select A when Sel = 0
        A -> and1.A;
        not1.O -> and1.B;
        
        # Select B when Sel = 1
        B -> and2.A;
        Sel -> and2.B;
        
        # Combine results
        and1.O -> or1.A;
        and2.O -> or1.B;
        or1.O -> Out;
    }
}
```
