# Task: Build PySHDL — the user-facing Python library for SHDL

## Context

This repo is the SHDL toolchain: `flattener/` lowers SHDL source to Base SHDL (a flat single-bit netlist + JSON metadata), and `shdlc/` compiles Base SHDL to C and builds a shared library exposing a stable simulation ABI. Both are complete, hardened, and verified (~1640 tests, frozen conformance corpus, dual oracles, fuzzing, a verified 16-bit CPU example). The compiler is ready. **Your task is to build PySHDL** — the ergonomic Python library through which, per the project charter, "99% of users will interact with SHDL."

Read these first (in `docs/`; if not there, they are at the repo root):
- `SHDL_Project.md` §4.1 — the charter definition of PySHDL. This is your product spec.
- `golden_tests.md` — section "V.2 PySHDL" (your pinned test obligations) and CNF-5 (the conformance corpus is your acceptance gate).
- `shdlc_goals.md` §3 — the release ABI contract you are wrapping. Read it in full.
- `base_shdl.md` — the metadata section (`ports`, `timing`, `init`, `hierarchy`, …) you will consume.

For UX inspiration ONLY, study the OLD project's driver (read-only; it is a previous, broken-by-our-standards implementation — take the ergonomics, not the code):
- `/Users/Rafa/Code/Python/SHDL/src/SHDL/driver/circuit.py` — the old `Circuit` class.
- `/Users/Rafa/Code/Python/SHDL/docs/docs/getting-started/using-pyshdl.md` — the old user guide; the feel we want.
- Known old flaws to avoid: fragile file-vs-string content sniffing, no value masking/validation, leaked temp files, rigid ad-hoc ctypes, one monolithic `__init__` exporting ~80 names.

## What already exists (build on these — do not reimplement)

In-process pipeline seams (no subprocess calls needed anywhere):
- `flattener.loader.load_program(main_path, include_dirs)` → `Program` (resolves imports: importing file's directory first, then include dirs).
- `flattener.pipeline.select_top(program, top)` and `flattener.pipeline.flatten_program(...)` → `FlattenOutput` (Base SHDL text). Structured diagnostics come from `flattener.diagnostics`.
- `shdlc.compile.compile_text(base_text)` → `(Circuit, c_src)`; `shdlc.compile.build_library(base_text, out_path)` → built shared library.
- `shdlc.cc`: `find_cc()`, `build_shared(...)`, `lib_suffix()`, `CCError`.
- `shdlc.harness`: `Sim` (complete ctypes binding of the release ABI: `reset/poke/peek/step/step_settle/run_batch`), `load_fresh_copy` (see "traps" below), `STRICT_CFLAGS`, `make_oracle` → `BaseEval` reference interpreter.
- `conformance/` — corpus of cases with frozen cycle-by-cycle traces + a runner.

## The release ABI you are wrapping (summary; `shdlc_goals.md` §3 is authoritative)

- `poke(name, value)` / `peek(name)` address **user-facing multi-bit port names** from `ports` metadata, case-sensitively. The C side already does multi-bit packing: bit 0 of the uint64 = LSB of the port.
- Poke masks the value **mod 2^width**; peek zero-extends above the width. **Max port width is 64 bits** (compiler-enforced).
- Peek is lazy: if inputs changed since the last evaluation, peek runs exactly one evaluation cycle first. Fresh load and `reset()` land on the **power-on state**: all-zero except `init` metadata seeds.
- `step(cycles)` advances exactly that many unit-delay cycles. `step_settle(cycles)` is `step` with fixed-point early exit, returns cycles actually run — observably identical, purely an optimization.
- `run_batch(in, out, count, cycles, settle)` drives many input frames in one C call (one uint64 per input port per frame, declaration order; one tuple of outputs per frame). This is the throughput path (~5–7× in benchmarks).
- Unknown signal names at the C level take an error-and-do-nothing path — PySHDL must never rely on that: validate names in Python first.

## The product

A new top-level package `pyshdl/` providing, at minimum:

```python
from pyshdl import Circuit

with Circuit("examples/adder8.shdl") as c:   # flatten + compile + load, in-process
    c["A"] = 100          # dict-style poke, multi-bit
    c["B"] = 55
    c.step()
    print(c["Sum"])       # dict-style peek
```

### Construction
- `Circuit(path, *, top=None, include_dirs=(), build_dir=None, keep_artifacts=False, …)` where `path` is a `.shdl` file → full in-process pipeline (load → flatten → compile C → cc → dlopen).
- Explicit alternate constructors instead of content sniffing (old project's mistake): e.g. `Circuit.from_source(text)`, `Circuit.from_base(text_or_path)`, `Circuit.from_library(lib_path, base=…)`. Exact names/signatures are yours to design — the requirements are: no magic detection; every path is explicit and typed; compiling from a `.shdl` path is the front-door convenience.
- **Metadata availability:** when starting from `.shdl`/Base SHDL you have the meta JSON in hand. A bare prebuilt library has no metadata — investigate what is recoverable and design this explicitly (e.g. `from_library` takes an optional Base SHDL path for metadata; without it, document precisely which features degrade — widths, `settle()`, port listing). Do not guess silently.

### Simulation surface
- `poke(name, value)` / `peek(name)` / `step(n=1)` / `reset()` — thin, fast wrappers (these are hot paths; no per-call allocation beyond the encode).
- Dict-style `c[name]` get/set, `name in c`, and a context manager; `close()` is idempotent and `__del__`-safe.
- `settle()` — per the charter: advances **exactly `max_depth` cycles** (from `timing` metadata) for combinational circuits, and is **refused** (raise a dedicated exception) when `timing.has_feedback` is true.
- `step_settle(n)` exposed (or `step(n, settle=True)` — your call), returning cycles actually run.
- An ergonomic `run_batch` wrapper: accept frames as sequences of dicts (or a columnar form — design it), map to/from port order internally, return per-frame output records. Must be the documented throughput path.
- Value validation: by default, **raise** on a poke that doesn't fit the port (this is an educational tool — "value 256 doesn't fit 8-bit port 'A'" is a feature), with an opt-out (`strict=False` or similar) that defers to the ABI's documented masking. Decide and document negative-integer handling (e.g. two's-complement convenience for `-1` on an n-bit port) — whatever you choose, test it and write it down.
- Unknown port names raise a Python exception with the available names listed — before reaching C.

### Introspection
- `c.name`, `c.inputs` / `c.outputs` (port names), and a `PortInfo`/`CircuitInfo` layer (name, width, max value, direction) built from `ports` metadata.
- Expose `timing` (max_depth, has_feedback), `init` presence, and basic stats — read straight from the metadata, no recomputation.

### Errors
A small exception family in `pyshdl` (e.g. base `PySHDLError`; flatten/compile errors carrying the flattener's structured diagnostics in readable form; cc build errors carrying compiler stderr; simulation/lookup errors; the settle-refused error). Old project's family (`CompilationError`, `SimulationError`, `SignalNotFoundError`) is a reasonable shape.

### Package hygiene
- Stdlib-only (ctypes), typed, `from __future__ import annotations`, ruff-clean, matching the existing codebase's style and docstring conventions.
- A deliberately **small** `__all__` — the old project exported ~80 names flat; do not repeat that. `Circuit`, the info classes, the exceptions, `__version__`.
- Add `pyshdl` to the wheel packages in `pyproject.toml`. No new runtime dependencies.

## Known traps (learned the hard way in this codebase — respect them)

1. **dlopen caches by path.** Loading the same library file twice shares one global simulation state. Every `Circuit` instance must load its library from a unique filesystem path (see `load_fresh_copy` in `shdlc.harness` for the established pattern). Two `Circuit`s over the same source MUST be independent simulations — test this.
2. **Temp lifecycle.** Build artifacts go in a managed temp dir, cleaned on `close()`; `keep_artifacts`/`build_dir` retains them for inspection. No leaked files (the old project leaked).
3. **Power-on state ≠ all-zero.** `reset()` returns to the init-seeded power-on state (AMB-39 resolution). Sequential examples (`srLatch.shdl`, `dLatch.shdl`) rely on this — use them in tests.
4. **Don't break the decoupling.** `pyshdl` may import from both `flattener` and `shdlc`; those two must not gain imports of each other. If you need a seam that doesn't exist (e.g. a cleaner flatten-text-from-path helper), add it **additively** with its own tests and note it in your report.

## Tests (new directory `tests/pyshdl/`)

The pinned obligations from `golden_tests.md` V.2 — implement all of them:
- Multi-bit poke/peek via `ports` metadata.
- `settle()` = `step(max_depth)` on combinational circuits (assert equivalence against explicit stepping); refused with the dedicated exception when `has_feedback`.
- Power-on reset honoring `init` (fresh load AND after `reset()`).
- Context manager and dict-style access.
- The legacy "comprehensive" boundary catalog at the Python API: pass-through of 0–255, 0xFFFF patterns, bitwise-op circuits, nibble extraction.

Plus, required by this task:
- **CNF-5 acceptance gate:** replay conformance-corpus cases through the *public PySHDL API* and match the frozen traces bit-exactly. This is the single most important test — the corpus is the ground truth.
- Two-instance independence (trap #1 above).
- `run_batch` wrapper ≡ equivalent poke/step/peek loop, including with `settle=True`.
- Oracle lockstep: a few fixtures driven simultaneously through `Circuit` and `BaseEval` (`make_oracle`) with random stimulus.
- Error paths: unknown name, out-of-range poke (strict and non-strict), flatten error surfaces diagnostics readably, cc failure surfaces stderr, settle-refused, use-after-close.
- Fixtures: use `examples/*.shdl` (adder8, alu, mux, srLatch, dLatch, ringClock for the feedback/refusal cases). Optional but valuable: an SR16 CPU smoke test (load `examples/CPU`, run a short program).
- All existing tests stay green and untouched.

## Documentation

- `docs/pyshdl.md` — a user guide modeled on the old `using-pyshdl.md` (loading, poking/peeking, multi-bit, settle, batch, errors, artifact keeping) but truthful to the real API. Every code block must actually run.
- README: add a PySHDL quickstart section near the top — this is now the primary way in.
- A runnable `examples/interacting.py` (or similar) demonstrating the API against shipped examples.
- Bookkeeping: in `golden_tests.md`, mark the V.2 obligations executed with the test IDs/paths; in `SHDL_Project.md` §7 status table, flip "PySHDL driver" from Planned to Built; maintain `tasks/todo.md` per the project workflow (plan first, check off, review section).

## Verification gate

1. `uv run pytest` — entire suite green (old + new), no existing test modified in substance.
2. The CNF-5 corpus-replay test passes bit-exactly.
3. `uvx ruff check` / `uvx ruff format --check` — clean.
4. The docs guide's examples execute as written.
5. No new runtime deps; `flattener`/`shdlc` behavior unchanged (additive seams only, each tested).
6. Logical commits with clear messages.

## Out of scope
- SHDB debugger and the debug build (charter FUT V.3 — later layer).
- VCD export, waveforms, stdlib package, testbench runner (`.shtb`), backends, performance tiers.
- Publishing to PyPI, Python-version widening (floor stays >=3.14).

## Final report
The API you shipped (signatures of the public surface), design decisions made where this brief left choices open (constructor shapes, negative-int policy, metadata-degradation policy, batch frame format) with one-line rationales, test inventory mapped to the V.2/CNF-5 obligations, and verification evidence.
