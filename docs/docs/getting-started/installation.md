---
sidebar_position: 1
---

# Installation

Learn how to install **PySHDL**, the Python library for working with SHDL circuits.

:::info SHDL vs PySHDL
**SHDL** is the language for describing circuits. **PySHDL** is the Python library that parses, compiles, and simulates those circuits.
:::

## Requirements

- Python 3.13 or higher
- pip (Python package manager)
- A C compiler (clang recommended) for circuit simulation

## Install via pip

The easiest way to install PySHDL is using pip:

```bash
pip install PySHDL
```

## Install from source

You can also install PySHDL directly from the source:

```bash
git clone https://github.com/rafa-rrayes/SHDL.git
cd SHDL
pip install -e .
```

## Using uv (recommended)

If you use [uv](https://github.com/astral-sh/uv) for Python package management:

```bash
uv add PySHDL
```

## What PySHDL Provides

Once installed, PySHDL gives you:

### Command Line Tool

```bash
# Compile an SHDL file to C
shdlc compile myCircuit.shdl

# Compile and run
shdlc run myCircuit.shdl
```

### Python API

```python
from SHDL import SHDLCircuit

# Load and simulate a circuit
with SHDLCircuit("adder16.shdl") as circuit:
    circuit["A"] = 42
    circuit["B"] = 17
    circuit.step()
    print(circuit["Sum"])  # 59
```

### Core Modules

| Module | Purpose |
|--------|----------|
| `shdl.flattener` | Convert Expanded SHDL → Base SHDL |
| `shdl.compiler` | Compile Base SHDL → C code |
| `shdl.driver` | Python interface for circuit simulation |
| `shdl.debugger` | Debug info parsing and symbol management |

## Verify Installation

After installation, verify that PySHDL is working:

```bash
shdlc --help
```

Or in Python:

```python
import shdl
print(shdl.__version__)
```

## Next Steps

Now that you have PySHDL installed, let's [build your first circuit](/docs/getting-started/first-circuit)!
