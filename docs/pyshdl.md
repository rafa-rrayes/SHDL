# PySHDL: the Python driver

*The user-facing layer of the SHDL toolchain*

---

## 1. What PySHDL is

`SHDL` compiles an SHDL circuit and drives its simulation from Python. One
class, `Circuit`, owns the whole pipeline end to end: it flattens SHDL to Base
SHDL, runs the SHDLC compiler to generate C, builds a shared library with the
host C compiler, and loads a private copy of it through `ctypes`. You then poke
inputs, step the unit-delay clock, and peek outputs — all in-process.

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    c["A"] = 100
    c["B"] = 55
    c.settle()
    print(c["Sum"])  # 155
```

`SHDL` is part of this repository and is stdlib-only by design. From the repo
root it imports directly:

```python
from SHDL import Circuit
```

You need Python ≥ 3.14, the project's dependencies (`uv sync`), and a C
compiler on `PATH` (clang or gcc). Run everything through uv:

```sh
uv run python my_script.py
```

> Every code block in this guide runs as-is from the repository root, where the
> circuits it loads live under `examples/`.

---

## 2. Quickstart

```python
from SHDL import Circuit

# Load, compile, and drive an 8-bit ripple-carry adder.
with Circuit("examples/adder8.shdl") as c:
    print(repr(c))          # <SHDL.Circuit 'Adder8' (A[8], B[8], Cin) -> (Sum[8], Cout)>
    print(c.inputs)         # ('A', 'B', 'Cin')
    print(c.outputs)        # ('Sum', 'Cout')

    c["A"] = 200            # dict-style poke; bit 0 is the LSB
    c["B"] = 54
    c["Cin"] = 1
    c.settle()             # let every gate level propagate
    print(c["Sum"])         # 255
    print(c["Cout"])        # 0
```

The `with` block is the recommended form: on exit it releases the simulation
and removes the temporary build artifacts. (`close()` does the same and is
idempotent; see [§9](#9-lifecycle-and-build-artifacts).)

---

## 3. Loading circuits

`Circuit` has four constructors, one per kind of input. Construction is always
explicit — PySHDL never sniffs a string's contents to guess what it is.

### `Circuit(path, ...)` — an SHDL file (the front door)

```python
from SHDL import Circuit

c = Circuit("examples/inverter.shdl")
c["A"] = 1
c.step()
print(c["O"])  # 0
c.close()
```

Keyword options (also available on `from_source` and `from_base`):

| Option | Meaning |
|---|---|
| `top=` | Name of the component to build when the file defines several (otherwise the `top`-marked one). |
| `include_dirs=` | Directories searched to resolve `use` imports. |
| `strict=` | Range-validate pokes in Python (default `True`; see [§5](#5-value-policy-strict-and-non-strict)). |
| `build_dir=` | Keep artifacts in this directory instead of a managed temp dir. |
| `keep_artifacts=` | Retain the managed temp dir instead of deleting it on close. |
| `cc=` | C compiler to invoke (default: auto-detected). |
| `cflags=` | Extra flags passed to the C compiler. |

`top` selects a non-marked component from a multi-component file:

```python
from SHDL import Circuit

with Circuit("examples/busOps.shdl", top="SplitByte") as c:
    print(c.inputs)   # ('In',)
    print(c.outputs)  # ('Low', 'High')
```

### `Circuit.from_source(text, ...)` — SHDL held in a string

Use this when the SHDL is generated or embedded, not on disk. `name=` is the
module name the text is written under (it must be a valid identifier);
`include_dirs=` resolves any imports.

```python
from SHDL import Circuit

SOURCE = """\
top component Buf(A) -> (O) {
    g: OR;
    connect { A -> g.A; A -> g.B; g.O -> O; }
}
"""

with Circuit.from_source(SOURCE) as c:
    c["A"] = 1
    c.step()
    print(c["O"])  # 1
```

### `Circuit.from_base(base, ...)` — a Base SHDL artifact

`from_base` dispatches on **type**, never on content: a `str` is *always* Base
SHDL text, and a path object (anything `os.PathLike`, e.g. a `pathlib.Path`) is
*always* a file to read.

```python
from pathlib import Path
from SHDL import Circuit

BASE = """\
component Buf(A) -> (O) {
    g: OR;
    connect { A -> g.A; A -> g.B; g.O -> O; }
}
"""

# A str is artifact text:
with Circuit.from_base(BASE) as c:
    c["A"] = 1
    c.step()
    print(c["O"])  # 1

# A Path is a file to read:
artifact = Path("/tmp/buf.base.shdl")
artifact.write_text(BASE, encoding="utf-8")
with Circuit.from_base(artifact) as c:
    c["A"] = 1
    c.step()
    print(c["O"])  # 1
```

Because the dispatch is typed, `Circuit.from_base("/path/to/file")` does **not**
read that file — it parses the string `"/path/to/file"` as Base SHDL and fails.
Wrap the path in `Path(...)` to load a file.

### `Circuit.from_library(lib_path, *, base=...)` — a prebuilt shared library

Load an already-compiled `.so`/`.dylib`/`.dll` without recompiling. A bare
library exports only the six ABI symbols, so port names, widths, timing, and
init seeds are unrecoverable from it. Pass `base=` (the Base SHDL it was built
from; `str` = text, path object = file) to restore the full metadata surface.

```python
from SHDL import Circuit

# Build once, keeping the artifacts so we can reload them.
with Circuit("examples/adder8.shdl", build_dir="/tmp/adder8-build") as built:
    pass

lib = next(p for p in __import__("pathlib").Path("/tmp/adder8-build").iterdir()
           if p.suffix in (".so", ".dylib", ".dll") and ".copy" not in p.name)
base = "/tmp/adder8-build/Adder8.base.shdl"

from pathlib import Path
with Circuit.from_library(lib, base=Path(base)) as c:
    print(c.inputs)   # ('A', 'B', 'Cin') -- metadata restored
    c["A"], c["B"] = 1, 2
    c.settle()
    print(c["Sum"])   # 3
```

Without `base=`, the circuit degrades explicitly — see
[§7](#7-bare-libraries-without-metadata).

**Which constructor?** Use `Circuit(path)` for the everyday case (a `.shdl`
file). Use `from_source` for SHDL you hold in a string. Use `from_base` to skip
the flattener when you already have a Base SHDL artifact. Use `from_library` to
skip compilation entirely and reuse a prebuilt library.

---

## 4. Poking and peeking

`poke(name, value)` sets an input; `peek(name)` reads any port (input or
output). Dict access is the same thing: `c[name] = value` is `poke`, `c[name]`
is `peek`.

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    c.poke("A", 17)
    c["B"] = 25       # identical to c.poke("B", 25)
    c.settle()
    print(c.peek("Sum"))  # 42
    print(c["Sum"])       # 42 -- same call

    print(c["A"])         # 17 -- an input reads back the value you poked
```

Multi-bit ports take an ordinary `int`; bit 0 is the port's LSB. Reading a port
zero-extends to a Python `int`, so an output is always non-negative.

`in` tests whether a name is a port of either direction:

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    print("A" in c)     # True
    print("Sum" in c)   # True
    print("nope" in c)  # False
```

Unknown names are caught in Python, before reaching C. The error lists what is
available and never silently no-ops:

```python
from SHDL import Circuit, SignalNotFoundError

with Circuit("examples/adder8.shdl") as c:
    try:
        c.poke("Q", 1)
    except SignalNotFoundError as e:
        print(e)  # unknown input port 'Q'; inputs: A, B, Cin
```

`SignalNotFoundError` is also a `KeyError`, so `c["typo"]` behaves like any
mapping miss.

---

## 5. Value policy: strict and non-strict

By default (`strict=True`) every poke is range-validated in Python. The accepted
range for a width-`w` port is `-(2**(w-1)) <= value < 2**w`: the full unsigned
range plus the two's-complement negatives. A negative value encodes as two's
complement within the port width.

```python
from SHDL import Circuit, PortValueError

with Circuit("examples/adder8.shdl") as c:       # 8-bit A: accepts -128..255
    c["A"] = 255
    print(c["A"])  # 255
    c["A"] = -1    # two's complement
    print(c["A"])  # 255
    c["A"] = -128
    print(c["A"])  # 128

    try:
        c["A"] = 256   # out of range for 8 bits
    except PortValueError as e:
        print(e)  # value 256 does not fit 8-bit port 'A' ...
```

`PortValueError` is also a `ValueError`. Non-int pokes raise `TypeError`
(booleans count as ints: `True` pokes 1).

With `strict=False` PySHDL skips the range check and defers to the C ABI's
documented masking — every value is taken modulo `2**width`:

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl", strict=False) as c:
    c["A"] = 256
    print(c["A"])  # 0   -- 256 mod 256
    c["A"] = 257
    print(c["A"])  # 1
    c["A"] = -1
    print(c["A"])  # 255 -- two's complement of -1 in 8 bits
```

The masking is symmetric on read: bits at or above the port width are always 0.
The current mode is exposed as the read-only `c.strict` property.

---

## 6. Stepping, settle, and step_settle

SHDL is a **unit-delay** model: every gate recomputes once per cycle from the
previous cycle's values, so a signal advances exactly one gate level per
`step()`. A result is only fully formed once it has propagated through every
level on its path.

### `step(cycles=1)`

Advance exactly `cycles` cycles (one gate level each). `step(0)` is legal and
does nothing.

```python
from SHDL import Circuit

with Circuit("examples/inverter.shdl") as c:
    c["A"] = 1
    c.step()        # one level is enough for one gate
    print(c["O"])   # 0
```

### `settle()`

`settle()` is exactly `step(timing.max_depth)` — it advances the circuit by its
critical-path depth, the number of cycles that lets *every* gate level finish
propagating. It is the right call for combinational circuits, where that depth
is a true settle count:

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    print(c.timing.max_depth)  # 17 -- the ripple-carry critical path
    c["A"], c["B"] = 255, 1    # exercises the full carry chain
    c.settle()
    print(c["Sum"], c["Cout"])  # 0 1
```

On a circuit with **feedback** (a latch, a ring oscillator), `settle()` is
refused: a feedback loop has no guaranteed fixed point, so `max_depth` is not a
settle count. Advance such a circuit explicitly with `step(n)`.

```python
from SHDL import Circuit, SettleRefusedError

with Circuit("examples/srLatch.shdl") as c:
    print(c.timing.has_feedback)  # True
    try:
        c.settle()
    except SettleRefusedError as e:
        print("refused:", e)  # ... has feedback, so max_depth is not a settle count ...
```

(`settle()` also raises `MetadataUnavailableError` if the circuit's Base SHDL
carries no `timing` block at all.)

### `step_settle(cycles=1)`

`step_settle(n)` is `step(n)` with a fixed-point early exit: it stops as soon as
no gate output changed, and returns how many cycles it actually ran. The result
is observably identical to `step(n)` — it is purely an optimization. On a
combinational circuit it finds the fixed point well before the budget; an
oscillator never reaches one and runs the full count.

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    c["A"], c["B"] = 123, 45
    ran = c.step_settle(10_000)   # huge budget, real depth is small
    print(ran < 10_000)           # True -- stopped at the fixed point
    print(c["Sum"])               # 168
```

---

## 7. Batch simulation with `run_batch`

`run_batch(frames, *, cycles=1, settle=False)` drives many input frames through
one C call — the throughput path. It is observably identical to the equivalent
poke/step/peek loop, minus the per-call FFI overhead.

Each frame is a `Mapping` of input-port name to value. Per frame PySHDL applies
the pokes, advances `cycles` cycles (using the fixed-point early exit when
`settle=True`), and records every output. It returns one `{output: value}` dict
per frame.

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    depth = c.timing.max_depth
    rows = c.run_batch(
        [{"A": 10, "B": 20}, {"A": 100, "B": 28}],
        cycles=depth,
    )
    print([r["Sum"] for r in rows])  # [30, 128]
```

**Hold semantics.** Inputs a frame omits *hold* their previous value (starting
from the circuit's current inputs). Here the second and third frames keep `A`:

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    rows = c.run_batch(
        [{"A": 10, "B": 20}, {"B": 30}, {}],
        cycles=c.timing.max_depth,
    )
    print([r["Sum"] for r in rows])  # [30, 40, 40]  -- A stays 10 throughout
```

The `settle=True` flag swaps the per-frame `step(cycles)` for the fixed-point
`step_settle(cycles)` — same outputs, cheaper on circuits that settle early. The
same Python-side name and value validation applies; an unknown name reports
which frame it was in.

`run_batch` needs port metadata, so it raises `MetadataUnavailableError` on a
bare library (see [below](#8-bare-libraries-without-metadata)).

---

## 8. Bare libraries without metadata

`Circuit.from_library(lib)` *without* `base=` loads a library that carries no
port metadata. The circuit still runs, but degrades explicitly:

- `poke`/`peek` pass names straight through to C. The C unknown-name path
  reports an error and does nothing, so a `peek` of an unknown name returns `0`
  — PySHDL cannot pre-validate.
- `inputs`, `outputs`, `info`, `timing`, `in`, `settle()`, and `run_batch()`
  all raise `MetadataUnavailableError`.
- `strict` defaults to `False`, and requesting `strict=True` raises (width
  validation is impossible without metadata).

```python
from pathlib import Path
from SHDL import Circuit, MetadataUnavailableError

with Circuit("examples/adder8.shdl", build_dir="/tmp/adder8-bare") as built:
    pass
lib = next(p for p in Path("/tmp/adder8-bare").iterdir()
           if p.suffix in (".so", ".dylib", ".dll") and ".copy" not in p.name)

with Circuit.from_library(lib) as bare:        # no base= -> no metadata
    bare.poke("A", 5)
    bare.poke("B", 6)
    bare.step(40)
    print(bare.peek("Sum"))   # 11
    print(bare.strict)        # False
    try:
        bare.inputs
    except MetadataUnavailableError as e:
        print("no metadata:", str(e)[:40], "...")
```

Pass `base=` to get the full surface back, as shown in [§3](#3-loading-circuits).

---

## 9. Introspection

A circuit exposes a read-only view of its Base SHDL metadata. Nothing here
touches the simulation; it is built once at load time.

```python
from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    print(c.name)        # 'Adder8'
    print(c.inputs)      # ('A', 'B', 'Cin')   -- declaration order
    print(c.outputs)     # ('Sum', 'Cout')

    a = c.info.port("A")            # a PortInfo
    print(a.direction)   # 'input'
    print(a.width)       # 8
    print(a.max_value)   # 255
    print(a.min_value)   # -128
    print(len(a.wires))  # 8 -- the single-bit wires, LSB first

    t = c.timing                    # a TimingInfo (or None)
    print(t.max_depth)              # 17
    print(t.has_feedback)           # False
    print(t.is_combinational)       # True

    print(c.info.stats["total_gates"])  # 40
    print(c.info.has_init)               # False
```

`c.info` is a `CircuitInfo` with `.name`, `.inputs`, `.outputs`, `.timing`,
`.init` (a read-only mapping of seeded nets), `.stats` (a read-only mapping of
gate/connection counts), `.description`, and `.has_init`. `.init` and `.stats`
are immutable proxies — assigning into them raises `TypeError`.

Introspection outlives the simulation: `name`, `inputs`, `outputs`, and `info`
still work after `close()`, since they need no library.

---

## 10. Reset

`reset()` returns the circuit to its power-on state: every net all-zero except
the `init` seeds, with inputs cleared. It is idempotent and equivalent to a
fresh load.

```python
from SHDL import Circuit

with Circuit("examples/srLatch.shdl") as c:
    print(c["Q"], c["Qn"])   # 0 1 -- the init-seeded power-on state, not all-zero

    c["S"] = 1
    c.step_settle(20)
    print(c["Q"], c["Qn"])   # 1 0 -- latch set

    c.reset()
    print(c["Q"], c["Qn"])   # 0 1 -- back to power-on
```

---

## 11. Lifecycle and build artifacts

A `Circuit` owns a build directory. By default it is a managed temporary
directory holding the generated `*.base.shdl`, `*.c`, and shared library;
`close()` (or leaving the `with` block) removes it. `close()` is idempotent, and
`__del__` calls it, so a dropped circuit cleans up safely — but the context
manager is the clear, prompt form.

To keep the artifacts for inspection, either set `keep_artifacts=True` (keeps
the managed temp dir) or pass an explicit `build_dir=` (which is never deleted).
`c.build_dir` is where they live.

```python
from pathlib import Path
from SHDL import Circuit

out = Path("/tmp/adder8-artifacts")
with Circuit("examples/adder8.shdl", build_dir=out) as c:
    print(c.build_dir)  # /tmp/adder8-artifacts

# After close, the artifacts remain because build_dir was explicit:
print((out / "Adder8.base.shdl").is_file())  # True
print((out / "Adder8.c").is_file())          # True
```

---

## 12. Error handling

Every PySHDL exception derives from `PySHDLError`, in two branches that mirror a
circuit's life: `CompilationError` (turning source into a loaded library) and
`SimulationError` (driving the loaded circuit).

| Exception | Base | Raised when |
|---|---|---|
| `PySHDLError` | `Exception` | Base of every PySHDL error. |
| `CompilationError` | `PySHDLError` | Any failure from source to a loaded library. |
| `FlattenError` | `CompilationError` | SHDL → Base SHDL flattening failed. Carries `.diagnostic` (the flattener's positioned diagnostic). |
| `CompileError` | `CompilationError` | Base SHDL → C failed (syntax or structural violation). |
| `BuildError` | `CompilationError` | The C compiler failed or was not found. Carries `.argv` and `.stderr`. |
| `SimulationError` | `PySHDLError` | Any failure while driving a loaded circuit. |
| `SignalNotFoundError` | `SimulationError`, `KeyError` | A port name that does not resolve; the message lists the valid names. |
| `PortValueError` | `SimulationError`, `ValueError` | A poke value out of range under strict validation. |
| `SettleRefusedError` | `SimulationError` | `settle()` on a circuit with feedback. |
| `MetadataUnavailableError` | `SimulationError` | A metadata-dependent feature on a bare library (no `base=`). |
| `ClosedCircuitError` | `SimulationError` | Simulation use of a circuit after `close()`. |

`FlattenError` and `BuildError` carry the underlying tool's structured failure
so you never re-parse a message:

```python
from SHDL import Circuit, FlattenError

bad = "top component Bad(A) -> (O) { connect { A -> nope.X; } }"
try:
    Circuit.from_source(bad)
except FlattenError as e:
    print(e.diagnostic.code)   # ErrorCode.E0307
    print(str(e))              # circuit.shdl:1:...: error[E0307]: ...
```

```python
from SHDL import Circuit, BuildError

try:
    Circuit("examples/inverter.shdl", cc="definitely-not-a-compiler")
except BuildError as e:
    print("definitely-not-a-compiler" in str(e))  # True
    print(e.argv)     # the command line attempted (empty if discovery failed)
    print(bool(e.stderr))  # the compiler's stderr, verbatim
```

---

## 13. A complete walkthrough

`examples/interacting.py` is a runnable script that ties the above together —
poke/peek and settle on the adder, a `run_batch`, an introspection printout, and
a latch demo with `step_settle` and `reset`. Run it from anywhere:

```sh
uv run python examples/interacting.py
```

## See also

- [shdl.md](shdl.md) — the SHDL language specification.
- [base_shdl.md](base_shdl.md) — the Base SHDL IR (the `meta` block PySHDL reads).
- [shdlc_goals.md](shdlc_goals.md) — the compiler's ABI contract (masking, lazy
  evaluation, init-seeded power-on) that PySHDL surfaces.
