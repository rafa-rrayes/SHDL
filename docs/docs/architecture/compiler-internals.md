---
sidebar_position: 4
---

# Compiler Internals

The SHDL compiler transforms Base SHDL into highly optimized C code. This page explains how the code generation works and the optimization techniques used.

## Compilation Pipeline

```
Base SHDL
    │
    ▼
┌─────────────┐
│   Parser    │   Tokenize and parse Base SHDL
└─────────────┘
    │
    ▼
┌─────────────┐
│  Analyzer   │   Semantic analysis, build connection graph
└─────────────┘
    │
    ▼
┌─────────────┐
│  CodeGen    │   Generate optimized C code
└─────────────┘
    │
    ▼
  C Source
    │
    ▼
┌─────────────┐
│ C Compiler  │   clang/gcc compiles to native code
└─────────────┘
    │
    ▼
Shared Library
```

## Bit-Packing Architecture

The key optimization in SHDL's compiler is **bit-packed SIMD-style** execution:

1. **Gate Packing** - All gates of the same type are packed into 64-bit integers
2. **Lane Assignment** - Each gate instance occupies one bit position (lane)
3. **Parallel Evaluation** - A single CPU operation evaluates up to 64 gates simultaneously
4. **Chunking** - If more than 64 gates of one type exist, multiple chunks are used

### Why Bit-Packing?

Consider a 16-bit adder with 32 XOR gates. Without bit-packing, you'd need 32 separate operations. With bit-packing, all 32 XOR gates are evaluated with a **single `^` operation**.

```
// Without bit-packing (slow)
xor1_out = xor1_a ^ xor1_b;
xor2_out = xor2_a ^ xor2_b;
// ... 30 more lines

// With bit-packing (fast)
XOR_outputs = XOR_inputs_A ^ XOR_inputs_B;  // All 32 at once!
```

## Generated Code Structure

### State Structure

The compiler generates a `State` struct containing outputs of all gate families:

```c
typedef struct {
    uint64_t XOR_O_0;   // Chunk 0 of XOR outputs (up to 64 gates)
    uint64_t XOR_O_1;   // Chunk 1 if > 64 XOR gates
    uint64_t AND_O_0;   // Chunk 0 of AND outputs
    uint64_t OR_O_0;    // Chunk 0 of OR outputs
    uint64_t NOT_O_0;   // Chunk 0 of NOT outputs
} State;
```

**Rules:**
- Only gate types that appear in the circuit are included
- Each chunk holds up to 64 gate outputs
- Chunk naming: `<GATE_TYPE>_O_<chunk_index>`

### The `tick()` Function

The core simulation function computes the next state:

```c
static inline State tick(State s, uint64_t A, uint64_t B, uint64_t Cin) {
    State n = s;  // Copy current state
    
    // 1. Build input vectors for each gate family
    // 2. Evaluate all gates in parallel
    // 3. Store results in next state
    
    return n;
}
```

### Input Vector Construction

For each gate family, build packed input vectors by gathering bits:

```c
uint64_t XOR_0_A = 0ull;
// Gather from component input A, bit 0, into lane 0
XOR_0_A |= ((uint64_t)-( ((A >> 0) & 1u) )) & 0x0000000000000001ull;
// Gather from component input A, bit 1, into lane 2
XOR_0_A |= ((uint64_t)-( ((A >> 1) & 1u) )) & 0x0000000000000004ull;
// Gather from XOR output bit 0, into lane 1
XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 0) & 1u) )) & 0x0000000000000002ull;
```

#### The Bit-Spreading Idiom

```c
((uint64_t)-( bit_value ))
```

This branchless technique:
1. Extracts a single bit: `(value >> bit_pos) & 1u`
2. Converts to all-ones or all-zeros: `(uint64_t)-(bit_value)`
   - If bit is 1: result is `0xFFFFFFFFFFFFFFFF`
   - If bit is 0: result is `0x0000000000000000`
3. Masks to target lane: `& lane_mask`

This is highly efficient on modern CPUs—no branches, pure arithmetic.

### Gate Evaluation

After building input vectors, evaluate all gates with a single operation:

```c
// XOR gates: O = A ^ B
n.XOR_O_0 = (XOR_0_A ^ XOR_0_B) & active_lanes_mask;

// AND gates: O = A & B
n.AND_O_0 = (AND_0_A & AND_0_B) & active_lanes_mask;

// OR gates: O = A | B
n.OR_O_0 = (OR_0_A | OR_0_B) & active_lanes_mask;

// NOT gates: O = ~A
n.NOT_O_0 = (~NOT_0_A) & active_lanes_mask;
```

The `active_lanes_mask` ensures only valid lanes are set when there are fewer than 64 gates in a chunk.

### Constant Gates

`__VCC__` and `__GND__` gates are special:
- `__VCC__`: Output is always 1 in its lane
- `__GND__`: Output is always 0 in its lane

These are handled by pre-computing constant masks at compile time.

## Library API

The generated C library exposes these functions:

### `void reset(void)`

Resets all internal state to zero:

```c
void reset(void) {
    memset(&dut, 0, sizeof(dut));
}
```

### `void poke(const char *signal_name, uint64_t value)`

Sets an input signal value:

```c
void poke(const char *signal_name, uint64_t value) {
    if (strcmp(signal_name, "A") == 0) {
        dut.input_A = value & 0xFFull;  // Mask to port width
    } else if (strcmp(signal_name, "B") == 0) {
        dut.input_B = value & 0xFFull;
    }
    // ...
}
```

### `uint64_t peek(const char *signal_name)`

Reads current value of any signal:

```c
uint64_t peek(const char *signal_name) {
    if (strcmp(signal_name, "A") == 0) return dut.input_A;
    
    ensure_outputs();  // Compute if needed
    
    if (strcmp(signal_name, "Sum") == 0) return dut.sum;
    // ...
}
```

### `void step(int cycles)`

Advances simulation by N cycles:

```c
void step(int cycles) {
    for (int i = 0; i < cycles; ++i) {
        dut.current = tick(dut.current, dut.input_A, dut.input_B, dut.input_Cin);
    }
    // Update cached outputs
    dut.sum = extract_Sum(&dut.current);
    dut.cout = extract_Cout(&dut.current);
}
```

## Lane Assignment Strategy

The compiler assigns each gate instance to a specific lane:

1. **Group by type** - Collect all AND gates, all XOR gates, etc.
2. **Assign lanes sequentially** - Gate 0 → lane 0, Gate 1 → lane 1, etc.
3. **Create chunks** - Every 64 gates starts a new chunk
4. **Record mapping** - Track which lane holds which gate for I/O extraction

Example for a 16-bit adder with 32 XOR gates:

```
fa1_x1 → XOR_O_0, lane 0
fa1_x2 → XOR_O_0, lane 1
fa2_x1 → XOR_O_0, lane 2
fa2_x2 → XOR_O_0, lane 3
...
fa16_x2 → XOR_O_0, lane 31
```

## Output Extraction

Generated functions extract component outputs from packed state:

```c
static inline uint64_t extract_Sum(const State *s) {
    return (((s->XOR_O_0 >> 1) & 1ull) << 0)   // Sum[1] from lane 1
         | (((s->XOR_O_0 >> 3) & 1ull) << 1)   // Sum[2] from lane 3
         | (((s->XOR_O_0 >> 5) & 1ull) << 2)   // Sum[3] from lane 5
         // ...
         ;
}
```

## Two-Phase Update Model

The simulator uses a two-phase model for correct timing:

1. **Compute Phase** - `tick()` computes next state from current state + inputs
2. **Commit Phase** - `step()` commits the computed state

This ensures:
- Combinational loops are handled correctly
- Sequential logic with feedback works properly
- Multiple `poke()` calls can be made before evaluation

## Complete Example

For a simple buffer component:

**Input (Base SHDL):**
```
component Buffer(A) -> (B) { 
    n1: NOT; 
    n2: NOT; 
    
    connect { 
        A -> n1.A; 
        n1.O -> n2.A; 
        n2.O -> B; 
    } 
}
```

**Output (C code):**
```c
#include <stdint.h>
#include <string.h>

typedef struct {
    uint64_t NOT_O_0;
} State;

static inline State tick(State s, uint64_t A) {
    State n = s;
    
    // NOT gate inputs
    uint64_t NOT_0_A = 0ull;
    NOT_0_A |= ((uint64_t)-( (A & 1u) )) & 0x1ull;
    NOT_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 0) & 1u) )) & 0x2ull;
    
    // Evaluate NOT gates
    n.NOT_O_0 = (~NOT_0_A) & 0x3ull;  // 2 active lanes
    
    return n;
}

static inline uint64_t extract_B(const State *s) {
    return (s->NOT_O_0 >> 1) & 1ull;  // B from lane 1
}

// ... rest of API implementation
```

## Using the Compiler

### From Python

```python
from SHDL import compile_shdl_file

# Generate C code
c_code = compile_shdl_file("adder16.shdl")
print(c_code)

# Or compile directly to a loadable circuit
from SHDL import SHDLCircuit

circuit = SHDLCircuit("adder16.shdl")
```

### From Command Line

```bash
# Generate C code
shdlc adder16.shdl -o adder16.c

# Compile to shared library
shdlc adder16.shdl -c -o libadder16.dylib

# Debug build with introspection support
shdlc -g adder16.shdl -c -o libadder16.dylib
```

## Debug Builds

The compiler supports debug builds with the `-g` flag, which add:

- **Gate name table** - Maps gate names to their bit positions
- **`peek_gate()` function** - Read any internal gate output by name
- **Cycle counter** - Track simulation time
- **`.shdb` file** - JSON metadata with hierarchy and source mapping

See [Debug Build Reference](/docs/debugger/debug-build) for complete documentation.
