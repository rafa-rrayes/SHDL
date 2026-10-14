# PySHDL

The Python toolchain for [SHDL](https://github.com/rafa-rrayes/SHDL), the Simple Hardware
Description Language. It flattens SHDL to Base SHDL, compiles that to C and a shared library, and
lets you drive the result from Python, gate by gate, one propagation level per cycle.

Requires Python ≥ 3.14 and a C compiler (clang or gcc).

```sh
uv tool install --python 3.14 PySHDL    # or: pip install PySHDL
```

This installs the `SHDL` Python package and four commands: `shdl`, `shdlc`, `shdl-flatten` and
`shdl-conformance`.

## From Python

One class, `Circuit`, runs the whole pipeline (flatten → compile → build → load) in-process and
exposes poke/peek/step, dict access and a context manager:

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    c["A"] = 100            # dict-style poke; bit 0 is the LSB
    c["B"] = 55
    c.settle()             # advance every gate level (combinational depth)
    print(c["Sum"])         # 155
```

See the [Python API guide](https://rafa-rrayes.github.io/SHDL/docs/tools/python-api) and
[`examples/interacting.py`](https://github.com/rafa-rrayes/SHDL/blob/master/examples/interacting.py)
for a runnable walkthrough. The underlying ABI is callable from any language; see
[shdlc_goals.md §3](https://github.com/rafa-rrayes/SHDL/blob/master/docs/shdlc_goals.md) for the
contract (masking, lazy evaluation, init-seeded power-on state).

## Projects and packages: the `shdl` CLI

The `shdl` command manages whole projects and installs circuit libraries from
[Circuit Circus](https://rafa-rrayes.github.io/CCircus), the SHDL package index:

```sh
shdl new counter && cd counter   # scaffold shdl.toml, src/, tests/ — it compiles
shdl add arith                   # vendor a package (+ its deps) into shdl_modules/
shdl build && shdl test          # flatten + compile, then run the test vectors
shdl run                         # poke/peek/step REPL over the live circuit
```

```shdl
use arith::{RippleAdder};        # vendored packages are directly importable
```

Dependencies are pinned in a committed `shdl.lock` (builds never touch the network), and
`shdl publish` walks you through contributing a package back. See the
[CLI guide](https://rafa-rrayes.github.io/SHDL/docs/tools/shdl-cli).

## What's inside

| Path | What it is |
|---|---|
| `flattener/` | SHDL → Base SHDL (lexer, parser, six lowering phases, metadata, `HighEval` reference interpreter) |
| `shdlc/` | Base SHDL → C → shared library (model, codegen, cc driver, `BaseEval` reference interpreter, ctypes harness) |
| `SHDL/` | The user-facing Python driver: `Circuit` runs the pipeline in-process and exposes poke/peek/step (`from SHDL import Circuit`) |
| `shdl_cli/` | The `shdl` project and package manager |
| `conformance/` | Frozen corpus of cases with golden Base SHDL + cycle-by-cycle traces, and its runner |
| `tests/` | The `flattener/`, `compiler/`, `cpu/`, `pyshdl/` and `shdl_cli/` suites |
| `scripts/` | Maintenance tooling (conformance corpus builder) |

The flattener and shdlc are deliberately decoupled: Base SHDL text is the *only* contract between
them, and each side carries its own independent reference interpreter so the two can cross-check
each other.

## Developing

In a checkout of [the repository](https://github.com/rafa-rrayes/SHDL), from this folder
(`pyshdl/`):

```sh
uv sync                          # the toolchain (editable) + pytest and Ruff
uv run pytest                    # full suite
uv run shdl-conformance run      # golden corpus: flatten + compile + trace lockstep
```

From the repository root, `uv run --project pyshdl …` runs the same toolchain on the examples, as
in `uv run --project pyshdl shdl-flatten examples/alu.shdl`.

The suite covers per-phase units, per-raise-site diagnostics (every error's exact position is
pinned), differential fuzzing against two independent oracles, byte-determinism, ABI contracts
under ASAN/UBSAN, and instruction-level lockstep of the example CPU against a golden model.

## Documentation

- [The documentation site](https://rafa-rrayes.github.io/SHDL/): guides, the language reference
  and the tools.
- [SHDL_Project.md](https://github.com/rafa-rrayes/SHDL/blob/master/docs/SHDL_Project.md): the
  project charter (architecture, ecosystem, build sequence).
- [shdl.md](https://github.com/rafa-rrayes/SHDL/blob/master/docs/shdl.md),
  [base_shdl.md](https://github.com/rafa-rrayes/SHDL/blob/master/docs/base_shdl.md),
  [shdlc_goals.md](https://github.com/rafa-rrayes/SHDL/blob/master/docs/shdlc_goals.md) and
  [golden_tests.md](https://github.com/rafa-rrayes/SHDL/blob/master/docs/golden_tests.md): the
  normative specs and the verification map.

## License

GPL-3.0-or-later.
