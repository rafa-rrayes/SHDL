# SHDL

SHDL (Simple Hardware Description Language) is an educational, gate-level
hardware description language and simulation toolchain. Its founding principle
is **fidelity**: circuits simulate gate by gate, one propagation level per
cycle (the unit-delay model), and no tool in the chain is allowed to collapse
or shortcut that structure. You describe hardware out of AND/OR/NOT/XOR; you
watch signals ripple through it.

## The two languages

**SHDL** is the authoring language: reusable hierarchical components,
multi-bit ports, compile-time parameters, generators and conditionals for
repetitive structure, bit slices and concatenation, named constants, optional
initial state, and imports. Specified in [docs/shdl.md](docs/shdl.md).

**Base SHDL** is the intermediate representation every tool consumes: a flat
netlist of single-bit wires over exactly six primitives — `AND`, `OR`, `NOT`,
`XOR`, `__VCC__`, `__GND__` — plus a JSON metadata section (multi-bit port
groups, hierarchy, source maps, timing, constants, init seeds). Specified in
[docs/base_shdl.md](docs/base_shdl.md).

## Pipeline

```
 .shdl source
      │
      ▼
  Flattener        six phases: strip, monomorphize, expand generators,
      │            expand slices, materialize constants, flatten hierarchy
      ▼
  Base SHDL        single-bit primitive netlist + JSON metadata
      │
      ▼
  SHDLC            generates C (two-buffer compute/commit cycle),
      │            builds a shared library with a stable ABI
      ▼
  libcircuit       reset() / poke() / peek() / step()
                   (+ step_settle() / run_batch() throughput paths)
```

## Quickstart

Requires Python ≥ 3.14 and a C compiler (clang or gcc).

Install the released package from PyPI to get the `pyshdl` driver and the
`shdlc` / `shdl-flatten` / `shdl-conformance` CLIs:

```sh
pip install PySHDL          # or: uv add PySHDL
```

Or work from a clone with [uv](https://docs.astral.sh/uv/):

```sh
uv sync

# Flatten SHDL to Base SHDL (inspect the IR)
uv run shdl-flatten examples/fullAdder.shdl

# Compile straight from SHDL source to a shared library
uv run shdlc examples/fullAdder.shdl -o fullAdder.dylib
```

Drive a circuit from Python with **PySHDL** — one class, `Circuit`, runs the
whole pipeline (flatten → compile → build → load) in-process and exposes
poke/peek/step plus dict access and a context manager:

```python
from pyshdl import Circuit

with Circuit("examples/adder8.shdl") as c:
    c["A"] = 100            # dict-style poke; bit 0 is the LSB
    c["B"] = 55
    c.settle()             # advance every gate level (combinational depth)
    print(c["Sum"])         # 155
```

See [docs/pyshdl.md](docs/pyshdl.md) for the full guide, and
[examples/interacting.py](examples/interacting.py) for a runnable walkthrough
(`uv run python examples/interacting.py`). The underlying ABI is callable from
any language; see [docs/shdlc_goals.md](docs/shdlc_goals.md) §3 for the full
contract (masking, lazy evaluation, init-seeded power-on state).

## Repository layout

| Path | What it is |
|---|---|
| `flattener/` | SHDL → Base SHDL (lexer, parser, six lowering phases, metadata, `HighEval` reference interpreter) |
| `shdlc/` | Base SHDL → C → shared library (model, codegen, cc driver, `BaseEval` reference interpreter, ctypes harness) |
| `pyshdl/` | The user-facing Python driver: `Circuit` runs the pipeline in-process and exposes poke/peek/step (`from pyshdl import Circuit`) |
| `conformance/` | Frozen corpus of cases with golden Base SHDL + cycle-by-cycle traces, and its runner |
| `tests/` | `flattener/`, `compiler/`, and `cpu/` suites (~1640 tests) |
| `examples/` | Small circuits (adders, latches, mux, ALU) and a complete, verified 16-bit CPU (`examples/CPU/`) |
| `docs/` | The normative specs and the verification map |
| `scripts/` | Maintenance tooling (conformance corpus builder) |

The flattener and shdlc are deliberately decoupled: Base SHDL text is the
*only* contract between them, and each side carries its own independent
reference interpreter so the two can cross-check each other.

## Testing

```sh
uv run pytest                    # full suite
uv run shdl-conformance run      # golden corpus: flatten + compile + trace lockstep
```

The suite covers per-phase units, per-raise-site diagnostics (every error's
exact position is pinned), differential fuzzing against two independent
oracles, byte-determinism, ABI contracts under ASAN/UBSAN, and instruction-
level lockstep of the example CPU against a golden model.

## Documentation

- [docs/SHDL_Project.md](docs/SHDL_Project.md) — project charter: architecture, ecosystem, build sequence.
- [docs/shdl.md](docs/shdl.md) — the SHDL language specification.
- [docs/base_shdl.md](docs/base_shdl.md) — the Base SHDL IR specification.
- [docs/shdlc_goals.md](docs/shdlc_goals.md) — the compiler's obligations and ABI contract.
- [docs/golden_tests.md](docs/golden_tests.md) — the verification map tying every spec obligation to tests.

## Status

The flattener, the SHDLC compiler (release ABI), the conformance suite, and
**PySHDL** — the user-facing Python driver (`from pyshdl import Circuit`) — are
complete and green. Next up are the debug build and the SHDB debugger — see the
build sequence in the charter.
