---
sidebar_position: 10
---

# Debug Build Reference

Technical reference for SHDB debug builds, including compiler flags, generated code, and the `.shdb` file format.

## Compiler Flags

### Basic Debug Build

```bash
shdlc -g myCircuit.shdl -c -o libmyCircuit.dylib
```

Produces:
- `libmyCircuit.dylib` - Shared library with debug functions
- `libmyCircuit.shdb` - Debug metadata file (JSON)

### Debug Levels

| Flag | Description | Gate Table | Source Map | Hierarchy |
|------|-------------|:----------:|:----------:|:---------:|
| `-g1` | Minimal | ✗ | ✗ | Basic |
| `-g2` | Standard (default) | ✓ | ✗ | Full |
| `-g3` | Full | ✓ | ✓ | Full |
| `-g` | Same as `-g2` | ✓ | ✗ | Full |

```bash
shdlc -g3 myCircuit.shdl -c -o libmyCircuit.dylib  # Full debug info
```

### Skip .shdb File

```bash
shdlc -g --no-shdb myCircuit.shdl -c -o libmyCircuit.dylib
```

Useful when you only need runtime gate inspection, not source mapping.

## Generated C Code

### Standard (Release) Build

```c
void reset(void);
void poke(const char *signal, uint64_t value);
uint64_t peek(const char *signal);
void step(int cycles);
```

### Debug Build Additions

```c
/* Debug build marker */
#define SHDB_DEBUG 1

/* Gate information table */
typedef struct {
    const char *name;
    uint8_t type;   /* GateType enum */
    uint8_t chunk;
    uint8_t lane;
} GateTableEntry;

static const GateTableEntry GATE_TABLE[] = { ... };
static const size_t NUM_GATES = ...;

/* Read any internal gate output by name */
uint64_t peek_gate(const char *gate_name);

/* Get current cycle count */
uint64_t get_cycle(void);

/* Enumerate gates */
size_t get_num_gates(void);
int get_gate_info(size_t index, const char **name, 
                  uint8_t *type, uint8_t *chunk, uint8_t *lane);
```

### Gate Type Enum

```c
enum GateType {
    GATE_XOR = 0,
    GATE_AND = 1,
    GATE_OR  = 2,
    GATE_NOT = 3,
    GATE_VCC = 4,
    GATE_GND = 5,
};
```

### peek_gate Implementation

```c
uint64_t peek_gate(const char *gate_name) {
    /* Ensure outputs are computed */
    if (!dut.outputs_valid) {
        dut.current = tick(dut.current, ...);
        dut.outputs_valid = 1;
    }

    /* Linear search (small circuits) or hash lookup (large circuits) */
    for (size_t i = 0; i < NUM_GATES; i++) {
        if (strcmp(GATE_TABLE[i].name, gate_name) == 0) {
            uint64_t chunk_val;
            switch (GATE_TABLE[i].type) {
                case GATE_XOR: chunk_val = dut.current.XOR_O_0; break;
                case GATE_AND: chunk_val = dut.current.AND_O_0; break;
                case GATE_OR:  chunk_val = dut.current.OR_O_0;  break;
                case GATE_NOT: chunk_val = dut.current.NOT_O_0; break;
                case GATE_VCC: return 1ull;
                case GATE_GND: return 0ull;
            }
            return (chunk_val >> GATE_TABLE[i].lane) & 1ull;
        }
    }
    return 0;  /* Not found */
}
```

### Cycle Counter

```c
static uint64_t cycle_count = 0;

void step(int cycles) {
    for (int i = 0; i < cycles; ++i) {
        dut.current = tick(dut.current, ...);
        cycle_count++;
    }
    /* ... update outputs ... */
}

uint64_t get_cycle(void) {
    return cycle_count;
}

void reset(void) {
    memset(&dut, 0, sizeof(dut));
    cycle_count = 0;
}
```

## .shdb File Format

The `.shdb` file is JSON containing all debug metadata.

### Top-Level Structure

```json
{
  "version": "1.0",
  "component": "Adder16",
  "source_file": "/path/to/adder16.shdl",
  "ports": { ... },
  "hierarchy": { ... },
  "gates": { ... },
  "source_map": { ... }
}
```

### Ports Section

```json
{
  "ports": {
    "inputs": [
      {
        "name": "A",
        "width": 16,
        "source_line": 5,
        "source_column": 21
      },
      {
        "name": "B",
        "width": 16,
        "source_line": 5,
        "source_column": 29
      },
      {
        "name": "Cin",
        "width": 1,
        "source_line": 5,
        "source_column": 37
      }
    ],
    "outputs": [
      {
        "name": "Sum",
        "width": 16,
        "source_line": 5,
        "source_column": 45
      },
      {
        "name": "Cout",
        "width": 1,
        "source_line": 5,
        "source_column": 56
      }
    ]
  }
}
```

### Hierarchy Section

```json
{
  "hierarchy": {
    "Adder16": {
      "source_file": "adder16.shdl",
      "source_line": 5,
      "instances": {
        "fa1": {
          "type": "FullAdder",
          "source_line": 8,
          "flattened_prefix": "fa1_"
        },
        "fa2": {
          "type": "FullAdder",
          "source_line": 9,
          "flattened_prefix": "fa2_"
        }
      }
    },
    "FullAdder": {
      "source_file": "fullAdder.shdl",
      "source_line": 1,
      "instances": {}
    }
  }
}
```

### Gates Section

```json
{
  "gates": {
    "fa1_x1": {
      "type": "XOR",
      "lane": 0,
      "chunk": 0,
      "hierarchy_path": "Adder16/fa1/x1",
      "original_name": "x1",
      "parent_instance": "fa1",
      "source": {
        "file": "fullAdder.shdl",
        "line": 2,
        "column": 3
      }
    },
    "fa1_x2": {
      "type": "XOR",
      "lane": 1,
      "chunk": 0,
      "hierarchy_path": "Adder16/fa1/x2",
      "original_name": "x2",
      "parent_instance": "fa1",
      "source": {
        "file": "fullAdder.shdl",
        "line": 3,
        "column": 3
      }
    }
  }
}
```

### Source Map Section

Maps source lines to generated gates (for `-g3`):

```json
{
  "source_map": {
    "adder16.shdl": {
      "8": ["fa1_x1", "fa1_x2", "fa1_a1", "fa1_a2", "fa1_o1"],
      "9": ["fa2_x1", "fa2_x2", "fa2_a1", "fa2_a2", "fa2_o1"]
    },
    "fullAdder.shdl": {
      "2": ["fa1_x1", "fa2_x1", "fa3_x1"],
      "3": ["fa1_x2", "fa2_x2", "fa3_x2"]
    }
  }
}
```

## TypeScript Schema

Full TypeScript type definitions for `.shdb` files:

```typescript
interface ShdbFile {
  version: "1.0";
  component: string;
  source_file: string;
  
  ports: {
    inputs: PortInfo[];
    outputs: PortInfo[];
  };
  
  hierarchy: {
    [component: string]: ComponentInfo;
  };
  
  gates: {
    [flattened_name: string]: GateInfo;
  };
  
  source_map?: {
    [file: string]: {
      [line: string]: string[];  // line -> gate names
    };
  };
}

interface PortInfo {
  name: string;
  width: number;
  source_line: number;
  source_column: number;
}

interface ComponentInfo {
  source_file: string;
  source_line: number;
  instances: {
    [name: string]: InstanceInfo;
  };
}

interface InstanceInfo {
  type: string;
  source_line: number;
  flattened_prefix: string;
}

interface GateInfo {
  type: "XOR" | "AND" | "OR" | "NOT" | "__VCC__" | "__GND__";
  lane: number;
  chunk: number;
  hierarchy_path: string;
  original_name: string;
  parent_instance: string;
  source?: {
    file: string;
    line: number;
    column: number;
  };
}
```

## Performance Considerations

### Debug Build Overhead

| Feature | Overhead |
|---------|----------|
| Gate table (static) | ~20 bytes per gate |
| `peek_gate()` lookup | O(n) for n gates |
| Cycle counter | Negligible |
| `.shdb` file | Disk only, not loaded by library |

For a 10,000 gate circuit:
- Gate table: ~200 KB in library
- `peek_gate()`: ~10,000 string comparisons worst case

### Optimization

For large circuits, the compiler can generate a hash table for O(1) gate lookup:

```bash
shdlc -g --gate-hash myCircuit.shdl -c -o libmyCircuit.dylib
```

### Debug vs Release Performance

Release builds (`-O3`, no debug):
- Maximum simulation speed
- No introspection capability

Debug builds (`-g`, `-O1`):
- ~10-20% slower simulation
- Full introspection
- Gate-level debugging

## Python Binding

The Python `shdb` module wraps these C functions:

```python
# Maps to C peek_gate()
def peek_gate(name: str) -> int: ...

# Maps to C get_cycle()  
@property
def cycle(self) -> int: ...

# Uses get_num_gates() + get_gate_info()
def gates(self, pattern: str = "*") -> List[GateInfo]: ...
```

The `.shdb` file is loaded and parsed in Python for hierarchy navigation and source mapping.
