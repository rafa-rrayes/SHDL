---
sidebar_position: 2
---

# Flattening Pipeline

The flattener transforms Expanded SHDL into Base SHDL through five sequential phases. Each phase must complete before the next begins.

## Pipeline Overview

```
Expanded SHDL
      │
      ▼
┌─────────────────┐
│ Phase 1: Lexical│   Remove comments, imports
│    Stripping    │
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Phase 2: Generator│   Expand >i[N]{...} constructs
│    Expansion     │
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Phase 3: Expander│   Expand Signal[:N] notation
│    Expansion     │
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Phase 4: Constant│   Convert to __VCC__/__GND__
│  Materialization │
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Phase 5: Hierarchy│   Inline all subcomponents
│    Flattening    │
└─────────────────┘
      │
      ▼
   Base SHDL
```

---

## Phase 1: Lexical Stripping

**Purpose:** Remove all non-structural elements from the source.

### What Gets Removed

| Element | Example | Action |
|---------|---------|--------|
| Hash comments | `# This is a comment` | Removed |
| String comments | `"A short comment"` | Removed |
| Multi-line comments | `"""..."""` | Removed |
| Import statements | `use module::{...}` | Resolved and removed |
| Whitespace | Extra spaces/newlines | Normalized |

### Example

**Input:**
```
# This is a full adder
use helpers::{Helper};

component FullAdder(A, B, Cin) -> (Sum, Cout) {
    x1: XOR;  "first xor"
    ...
}
```

**Output:**
```
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    x1: XOR;
    ...
}
```

---

## Phase 2: Generator Expansion

**Purpose:** Expand all generator constructs into explicit statements.

### How It Works

Generators are expanded from the innermost to outermost. Each iteration:
1. Substitutes the loop variable
2. Evaluates arithmetic expressions
3. Produces explicit code

### Range Parsing

| Range Syntax | Values Generated |
|--------------|------------------|
| `[N]` | 1, 2, 3, ..., N |
| `[A:B]` | A, A+1, ..., B |
| `[A:]` | A, A+1, ... (context-dependent) |
| `[A:B, C, D:E]` | A..B, C, D..E (combined) |

### Arithmetic Evaluation

Expressions inside `{...}` are evaluated:
- `{i+1}` → value of i plus 1
- `{i-1}` → value of i minus 1
- `{i*2}` → value of i times 2
- `{i*j+k}` → full expression evaluation

### Example

**Input:**
```
>i[3]{
    and{i}: AND;
}

connect {
    >i[3]{
        In[{i}] -> and{i}.A;
    }
}
```

**Output:**
```
and1: AND;
and2: AND;
and3: AND;

connect {
    In[1] -> and1.A;
    In[2] -> and2.A;
    In[3] -> and3.A;
}
```

### Nested Generators

Nested generators are expanded innermost-first:

**Input:**
```
>i[2]{
    >j[2]{
        cell{i}_{j}: BitCell;
    }
}
```

**Output:**
```
cell1_1: BitCell;
cell1_2: BitCell;
cell2_1: BitCell;
cell2_2: BitCell;
```

---

## Phase 3: Expander Expansion

**Purpose:** Expand all bit-slice notation into individual bit connections.

### Slice Notation

| Notation | Meaning | Expansion (8-bit signal) |
|----------|---------|--------------------------|
| `S[:4]` | Bits 1 to 4 | `S[1], S[2], S[3], S[4]` |
| `S[5:]` | Bits 5 to width | `S[5], S[6], S[7], S[8]` |
| `S[3:6]` | Bits 3 to 6 | `S[3], S[4], S[5], S[6]` |

### Width Matching

Source and destination slices must have the same width:

```
In[:4] -> Out[:4];    # ✓ Both 4 bits
In[:4] -> Out[5:8];   # ✓ Both 4 bits (different ranges, same width)
In[:4] -> Out[:8];    # ✗ Error: 4 bits vs 8 bits
```

### Example

**Input:**
```
connect {
    In[:4] -> Out[:4];
    In[5:8] -> Result[1:4];
}
```

**Output:**
```
connect {
    In[1] -> Out[1];
    In[2] -> Out[2];
    In[3] -> Out[3];
    In[4] -> Out[4];
    In[5] -> Result[1];
    In[6] -> Result[2];
    In[7] -> Result[3];
    In[8] -> Result[4];
}
```

---

## Phase 4: Constant Materialization

**Purpose:** Convert named constants into `__VCC__` and `__GND__` instances.

### How Constants Become Gates

Each bit of a constant becomes a power pin instance:
- Bit value 1 → `__VCC__` instance
- Bit value 0 → `__GND__` instance

### Bit Ordering

- Bit 1 is LSB (rightmost in binary)
- Bit N is MSB (leftmost in binary)

### Naming Convention

Constant bits are named: `{CONST_NAME}_bit{INDEX}`

### Example

**Input:**
```
component Example(In[4]) -> (Out[4]) {
    FIVE = 5;  # Binary: 101 (3 bits)
    
    xor1: XOR;
    xor2: XOR;
    xor3: XOR;
    
    connect {
        In[1] -> xor1.A;
        FIVE[1] -> xor1.B;
        xor1.O -> Out[1];
        
        In[2] -> xor2.A;
        FIVE[2] -> xor2.B;
        xor2.O -> Out[2];
        
        In[3] -> xor3.A;
        FIVE[3] -> xor3.B;
        xor3.O -> Out[3];
    }
}
```

**Output:**
```
component Example(In[4]) -> (Out[4]) {
    FIVE_bit1: __VCC__;   # 5 = 0b101, bit 1 = 1
    FIVE_bit2: __GND__;   # bit 2 = 0
    FIVE_bit3: __VCC__;   # bit 3 = 1
    
    xor1: XOR;
    xor2: XOR;
    xor3: XOR;
    
    connect {
        In[1] -> xor1.A;
        FIVE_bit1.O -> xor1.B;
        xor1.O -> Out[1];
        
        In[2] -> xor2.A;
        FIVE_bit2.O -> xor2.B;
        xor2.O -> Out[2];
        
        In[3] -> xor3.A;
        FIVE_bit3.O -> xor3.B;
        xor3.O -> Out[3];
    }
}
```

---

## Phase 5: Hierarchy Flattening

**Purpose:** Inline all subcomponent instances, eliminating hierarchy.

This is the most complex phase. It requires:
1. Resolving all component definitions
2. Recursively flattening nested components
3. Prefixing instance names to avoid collisions
4. Rewiring connections through the hierarchy

### Naming Convention

When a subcomponent is flattened, all its internal instances get prefixed:

```
{parent_instance_name}_{child_instance_name}
```

**Example:**
- Parent instance: `fa1` (a FullAdder)
- Child instance inside FullAdder: `x1` (an XOR gate)
- Flattened name: `fa1_x1`

### Nested Hierarchy

For deeply nested components, prefixes accumulate:

```
level1_level2_level3_instanceName
```

**Example:**
- Top: instance `alu1` of type ALU
- ALU has: instance `adder1` of type Adder
- Adder has: instance `fa1` of type FullAdder
- FullAdder has: instance `x1` of type XOR

Flattened name: `alu1_adder1_fa1_x1`

### Connection Rewiring

When flattening, connections to subcomponent ports must be rewired to the actual internal signals:

**Before flattening:**
```
fa1: FullAdder;
connect {
    X -> fa1.A;
    fa1.Sum -> Result;
}
```

**After flattening:**
```
fa1_x1: XOR; fa1_x2: XOR; fa1_a1: AND; fa1_a2: AND; fa1_o1: OR;
connect {
    X -> fa1_x1.A;      # fa1.A mapped to fa1_x1.A
    fa1_x2.O -> Result; # fa1.Sum was driven by x2.O
}
```

### Complete Example

**Input:**
```
use fullAdder::{FullAdder};

component Adder4(A[4], B[4], Cin) -> (Sum[4], Cout) {
    >i[4]{
        fa{i}: FullAdder;
    }
    
    connect {
        A[1] -> fa1.A;
        B[1] -> fa1.B;
        Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];
        
        >i[2:4]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;
            fa{i}.Sum -> Sum[{i}];
        }
        
        fa4.Cout -> Cout;
    }
}
```

**After All Phases (Base SHDL):**
```
component Adder4(A[4], B[4], Cin) -> (Sum[4], Cout) {
    fa1_x1: XOR; fa1_x2: XOR; fa1_a1: AND; fa1_a2: AND; fa1_o1: OR;
    fa2_x1: XOR; fa2_x2: XOR; fa2_a1: AND; fa2_a2: AND; fa2_o1: OR;
    fa3_x1: XOR; fa3_x2: XOR; fa3_a1: AND; fa3_a2: AND; fa3_o1: OR;
    fa4_x1: XOR; fa4_x2: XOR; fa4_a1: AND; fa4_a2: AND; fa4_o1: OR;
    
    connect {
        A[1] -> fa1_x1.A; B[1] -> fa1_x1.B;
        A[1] -> fa1_a1.A; B[1] -> fa1_a1.B;
        fa1_x1.O -> fa1_x2.A; Cin -> fa1_x2.B;
        fa1_x1.O -> fa1_a2.A; Cin -> fa1_a2.B;
        fa1_a1.O -> fa1_o1.A; fa1_a2.O -> fa1_o1.B;
        fa1_x2.O -> Sum[1];
        
        # ... (remaining adders follow same pattern)
        
        fa4_o1.O -> Cout;
    }
}
```

---

## Guarantees

The flattening protocol guarantees:

1. **Correctness** - The flattened circuit is functionally equivalent to the original
2. **Uniqueness** - No name collisions through hierarchical prefixing
3. **Completeness** - All abstractions are resolved to primitives
4. **Determinism** - Same input always produces same output
