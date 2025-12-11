---
sidebar_position: 5
---

# PySHDL Internals

PySHDL is the Python implementation of the SHDL toolchain. This page documents its internal architecture and module structure.

## Package Structure

```
shdl/
├── __init__.py          # Public API exports
├── errors.py            # Shared exception classes
├── flattener/           # Expanded SHDL → Base SHDL
│   ├── lexer.py         # Tokenizer
│   ├── parser.py        # Parser
│   ├── ast.py           # AST node definitions
│   └── flattener.py     # Flattening logic
├── compiler/            # Base SHDL → C code
│   ├── lexer.py         # Base SHDL tokenizer
│   ├── parser.py        # Base SHDL parser
│   ├── ast.py           # Base SHDL AST
│   ├── analyzer.py      # Semantic analysis
│   ├── codegen.py       # C code generation
│   ├── compiler.py      # Compilation orchestration
│   └── cli.py           # Command-line interface
└── driver/              # Python ↔ C interface
    ├── circuit.py       # SHDLCircuit class
    └── exceptions.py    # Driver-specific errors
```

## Module Overview

### Flattener (`shdl.flattener`)

The flattener transforms Expanded SHDL (with generators, expanders, hierarchy) into Base SHDL (flat, primitive-only).

#### Key Components

| Module | Purpose |
|--------|---------|
| `lexer.py` | Tokenizes Expanded SHDL source code |
| `parser.py` | Parses tokens into an AST |
| `ast.py` | Defines AST node classes for Expanded SHDL |
| `flattener.py` | Implements the 5-phase flattening algorithm |

#### Public API

```python
from SHDL import parse_file, Flattener, flatten_file

# Parse SHDL file into AST
module = parse_file("adder.shdl")

# Create flattener and flatten a component
flattener = Flattener(include_paths=["./components"])
base_shdl = flattener.flatten(module, "Adder16")

# Or use the convenience function
base_shdl = flatten_file("adder.shdl", component="Adder16")
```

### Compiler (`shdl.compiler`)

The compiler transforms Base SHDL into optimized C code.

#### Key Components

| Module | Purpose |
|--------|---------|
| `lexer.py` | Tokenizes Base SHDL |
| `parser.py` | Parses Base SHDL into AST |
| `ast.py` | Base SHDL AST node definitions |
| `analyzer.py` | Semantic analysis, connection graph building |
| `codegen.py` | C code generation with bit-packing |
| `compiler.py` | Orchestrates the compilation pipeline |

#### Public API

```python
from SHDL import compile_base_shdl, compile_shdl_file

# Compile Base SHDL string to C
c_code = compile_base_shdl(base_shdl_source)

# Compile SHDL file (handles flattening automatically)
c_code = compile_shdl_file("adder.shdl", component="Adder16")
```

### Driver (`shdl.driver`)

The driver provides a high-level Python interface for compiled circuits.

#### Key Components

| Module | Purpose |
|--------|---------|
| `circuit.py` | `SHDLCircuit` class for circuit simulation |
| `exceptions.py` | Driver-specific exception classes |

#### Public API

```python
from SHDL import SHDLCircuit

# Create and use a circuit
circuit = SHDLCircuit("adder16.shdl")
circuit.poke("A", 100)
circuit.poke("B", 50)
circuit.step()
result = circuit.peek("Sum")

# Use as context manager
with SHDLCircuit("adder16.shdl") as circuit:
    circuit["A"] = 100
    circuit["B"] = 50
    circuit.step()
    print(circuit["Sum"])
```

## Error Handling

All SHDL errors inherit from a base `SHDLError`:

```python
from SHDL import SHDLError, LexerError, ParseError, FlattenerError

try:
    circuit = SHDLCircuit("broken.shdl")
except LexerError as e:
    print(f"Lexer error: {e}")
except ParseError as e:
    print(f"Parse error: {e}")
except FlattenerError as e:
    print(f"Flattener error: {e}")
except SHDLError as e:
    print(f"SHDL error: {e}")
```

### Error Types

| Error | Source | When |
|-------|--------|------|
| `LexerError` | Lexer | Invalid tokens, unexpected characters |
| `ParseError` | Parser | Invalid syntax |
| `FlattenerError` | Flattener | Undefined components, invalid ranges |
| `CompilationError` | Driver | C compilation failures |
| `SimulationError` | Driver | Runtime simulation errors |
| `SignalNotFoundError` | Driver | Invalid signal name in poke/peek |

## AST Node Types

### Expanded SHDL AST

```python
from SHDL import (
    Module, Component, Port, Instance, Constant, 
    Connection, Signal, IndexExpr, Generator, Import
)

# Module contains components
module = parse_file("adder.shdl")
for component in module.components:
    print(f"Component: {component.name}")
    
    # Access ports
    for port in component.input_ports:
        print(f"  Input: {port.name}[{port.width}]")
    
    # Access instances
    for instance in component.instances:
        print(f"  Instance: {instance.name}: {instance.component_type}")
```

### Base SHDL AST

The compiler uses a simpler AST for Base SHDL:

```python
from SHDL.compiler import BaseSHDLParser

parser = BaseSHDLParser()
module = parser.parse(base_shdl_source)

for component in module.components:
    print(f"Primitive instances: {len(component.instances)}")
```

## Semantic Analysis

The `SemanticAnalyzer` validates Base SHDL and builds a connection graph:

```python
from SHDL.compiler import analyze

result = analyze(component)

if result.has_errors:
    for error in result.errors:
        print(f"Error: {error}")
else:
    print(f"Valid circuit with {len(result.gates)} gates")
```

### Analysis Result

```python
@dataclass
class AnalysisResult:
    component: Component
    gates: dict[str, GateInfo]      # Instance name → gate info
    connections: list[Connection]    # All connections
    input_ports: list[PortInfo]     # Input port metadata
    output_ports: list[PortInfo]    # Output port metadata
    errors: list[Error]             # Semantic errors
    warnings: list[Warning]         # Warnings
```

## Code Generation

The `CodeGenerator` produces optimized C code:

```python
from SHDL.compiler import generate

c_code = generate(analysis_result)
```

### Generated Code Features

1. **Bit-packed state** - Gates grouped by type in 64-bit words
2. **Lane assignment** - Each gate instance gets a unique bit position
3. **SIMD-style evaluation** - Single operations evaluate many gates
4. **Output extraction** - Functions to extract multi-bit outputs

## Extending PySHDL

### Adding a New Primitive

To add a new primitive gate type:

1. Add to `PRIMITIVE_GATES` in `flattener/flattener.py`
2. Add to grammar in `compiler/parser.py`
3. Add code generation in `compiler/codegen.py`

### Custom Include Paths

```python
from SHDL import SHDLCircuit

circuit = SHDLCircuit(
    "main.shdl",
    include_paths=["./components", "./lib"]
)
```

### Keeping Generated Libraries

By default, compiled libraries are deleted. To keep them:

```python
circuit = SHDLCircuit(
    "adder.shdl",
    keep_library=True,
    library_dir="./build"
)
print(f"Library at: {circuit.library_path}")
```

## Performance Considerations

### Compilation Caching

Currently, PySHDL recompiles circuits on each instantiation. For repeated use, consider:

```python
# Compile once, reuse
circuit = SHDLCircuit("adder.shdl", keep_library=True, library_dir="./cache")

# Later, load the cached library
# (Not yet implemented - future feature)
```

### Optimization Levels

Control C compiler optimization:

```python
circuit = SHDLCircuit(
    "adder.shdl",
    optimize=3,  # -O3 (default)
    cc="clang"   # Compiler to use
)
```

### Large Circuits

For circuits with many gates:
- Bit-packing handles up to 64 gates per chunk efficiently
- Beyond 64 gates of one type, multiple chunks are used
- Memory usage scales linearly with gate count
