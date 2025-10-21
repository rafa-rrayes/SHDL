# SHDL Compiler

Python utilities for compiling SHDL (Simple Hardware Description Language) components into C source code. The included compiler flattens hierarchical components, expands multi-bit signals, and generates a self-contained C file that can be built with the provided runtime in `defaults.c`.

## Getting Started
- Ensure Python 3.10+ is available (only the standard library is required).
- Optionally create a virtual environment: `python3 -m venv .venv && source .venv/bin/activate`.
- Explore the sample components in `SHDL_components/` and the top-level design in `new_SHDL.shdl`.

## Compiling a Component
The compiler expects a SHDL source file and a C runtime template containing the `// LE CODE` placeholder.

```bash
python compiler.py -i new_SHDL.shdl -o build/new_SHDL.c -d defaults.c
```

The generated file contains the flattened netlist and can be compiled with any C toolchain together with your preferred runtime glue code.

## Repository Layout
- `compiler.py` – command-line compiler for SHDL components.
- `defaults.c` – baseline C runtime template with the `// LE CODE` insertion point.
- `SHDL_components/` – reusable primitive and composite SHDL components.
- `generators.py` – helper scripts for producing SHDL assets.
- `todo.md` – notes and future enhancements.

## Contributing
Feel free to open issues or submit pull requests for bug fixes, new components, or tooling improvements. Before submitting changes, format your code with sensible defaults and run any project-specific scripts you add.
