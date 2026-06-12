# PySHDL — the user-facing Python driver (Phase 2)

Goal: build the `pyshdl/` package (Circuit + info layer + exceptions), its
test suite under `tests/pyshdl/` (V.2 obligations + CNF-5 corpus gate), docs,
and bookkeeping — with zero behavior change to `flattener/`/`shdlc/`.

Baseline: 1644 tests collected, all green; conformance 78 checks / 0 failures.
(Previous phase: repo cleanup — done, see git history bd78af4 and earlier.)

## Design decisions (locked before implementation)

1. **Constructors — explicit, no content sniffing.**
   - `Circuit(path, *, top=None, include_dirs=(), strict=True, build_dir=None,
     keep_artifacts=False, cc=None, cflags=None)` — front door; `path` is a
     `.shdl` file; full in-process pipeline (load → flatten → C → cc → dlopen).
   - `Circuit.from_source(text, *, name="circuit", ...)` — SHDL source text
     (written to a managed temp file so imports resolve from include_dirs).
   - `Circuit.from_base(base, ...)` — Base SHDL; **typed dispatch, not
     sniffing**: `str` is text, `os.PathLike` is a file path.
   - `Circuit.from_library(lib_path, *, base=None, ...)` — prebuilt library;
     optional `base` (same typed dispatch) supplies metadata.
2. **Independence (dlopen trap):** every instance — all four constructors —
   loads a uniquely named *copy* of the library from its own temp dir
   (the `load_fresh_copy` pattern). Two Circuits are always independent.
3. **Value policy:** `strict=True` (default) raises `PortValueError` unless
   `-(2**(w-1)) <= value < 2**w`; negatives encode two's complement.
   `strict=False` defers to the ABI: mask mod 2^w. Both documented + tested.
4. **Bare library (no metadata):** nothing is recoverable from a release lib
   (it exports only the 6 ABI symbols). Explicit degradation: `strict=True`
   without `base` is a constructor error; `inputs`/`outputs`/`info`/
   `settle()`/`run_batch()`/`in` raise `MetadataUnavailableError`; poke/peek
   pass through to the C unknown-name path (documented).
5. **settle():** `step(max_depth)` exactly (charter §4.1); returns None;
   `SettleRefusedError` when `timing.has_feedback`; `MetadataUnavailableError`
   when timing metadata is absent. `step_settle(n) -> int` exposed as is.
6. **run_batch frames:** `Sequence[Mapping[str, int]]`; unspecified inputs
   hold their current value; returns `list[dict[str, int]]` (one per frame).
   Columnar packing to declaration order (= `ports` meta order) is internal.
7. **Exceptions:** `PySHDLError` → `CompilationError` → {`FlattenError`
   (.diagnostic), `CompileError`, `BuildError` (.stderr/.argv)};
   `PySHDLError` → `SimulationError` → {`SignalNotFoundError` (also KeyError,
   lists available names), `PortValueError` (also ValueError),
   `SettleRefusedError`, `MetadataUnavailableError`, `ClosedCircuitError`}.
8. **No new seams needed** in flattener/shdlc: `flatten_program` returns
   `.meta`+`.text`; `build_library`/`Sim`/`parse_base`/`identity_ports`
   cover the rest. Decoupling preserved (pyshdl imports both; they import
   nothing new from each other).

## Plan

- [x] 1. `pyshdl/` package: `errors.py`, `info.py` (PortInfo/TimingInfo/
      CircuitInfo), `circuit.py` (Circuit), `__init__.py` (small `__all__`),
      wheel packages entry in pyproject.
- [x] 2. Tests `tests/pyshdl/` (V.2 + this brief):
      - [x] construction/lifecycle: ctor paths, context manager, close
            idempotent + `__del__`-safe, use-after-close, two-instance
            independence, artifact keep/cleanup (no leaked temp dirs)
      - [x] ports: multi-bit poke/peek, dict access, `in`, unknown-name,
            poke-an-output, strict/non-strict, negatives, zero-extension
      - [x] settle: == step(max_depth) on combinational; refused on feedback
      - [x] reset/init: power-on state fresh + after reset (srLatch, dLatch)
      - [x] batch: ≡ poke/step/peek loop (incl. settle=True), hold semantics
      - [x] boundary catalog: 0–255 pass-through, 0xFFFF patterns, bitwise
            ops, nibble extraction
      - [x] **CNF-5 gate**: corpus replay through the public API, bit-exact
      - [x] oracle lockstep: Circuit vs BaseEval, random stimulus
      - [x] errors: flatten diagnostics, cc stderr, base parse, bare-library
            degradation matrix
      - [x] CPU smoke (optional): load examples/CPU, run a short program
- [x] 3. Docs: `docs/pyshdl.md` user guide (every block runs);
      README quickstart; `examples/interacting.py`.
- [x] 4. Bookkeeping: golden_tests.md V.2 → executed (test IDs/paths) +
      CNF-5 PySHDL wiring noted; SHDL_Project.md §7 PySHDL → Built.
- [x] 5. Verify: full pytest green; ruff check + format --check clean;
      docs examples executed; logical commits.

## Review

Completed 2026-06-12. All five plan items shipped; all eight design
decisions held unchanged through implementation.

**What landed.**
- `pyshdl/` (4 modules, ~700 lines): `Circuit` with the four explicit
  constructors, strict/non-strict value policy, settle/step_settle,
  dict-frame `run_batch` with hold semantics, full introspection from
  `ports` metadata, 11-class exception family, per-instance library
  copies (dlopen independence), owned-temp-dir lifecycle with
  `keep_artifacts`/`build_dir` retention. Stdlib-only, typed, in the
  wheel via pyproject `packages`.
- `tests/pyshdl/` (conftest + 10 modules, **130 tests**): every V.2
  obligation plus CNF-5 — the full conformance corpus (38 cases /
  40 traces) replays through the public API bit-exactly. The directory
  is deliberately NOT a package (a `tests/pyshdl/__init__.py` would
  shadow the `pyshdl` source package under pytest's prepend import
  mode), and all basenames are `test_pyshdl_*` for repo-wide uniqueness.
- Docs: `docs/pyshdl.md` (25 code blocks, each executed), README
  quickstart, runnable `examples/interacting.py`.
- Bookkeeping: golden_tests.md V.2 marked EXECUTED with test paths,
  CNF-5 flipped ⚪→🟡 (PySHDL wired; debug build/backends still open),
  collected-test count 1643→1774, TIM-3 refusal landed; SHDL_Project.md
  §7 PySHDL driver → Built.

**Verification evidence.**
- `uv run pytest -q`: **1766 passed, 8 skipped (pre-existing), 0 failed**
  (baseline 1644 untouched + 130 new; SR16 CPU smoke runs a 4-instruction
  program to HALT with R3 == 42 in 15 s).
- `uvx ruff check`: All checks passed. `uvx ruff format --check`:
  121 files already formatted.
- All doc code blocks and `examples/interacting.py` executed with exit 0.
- No behavior change in `flattener/`/`shdlc/`/`conformance/` (zero edits);
  the two still import nothing from each other.

**Notable catches during the build.**
- Conformance traces deliberately poke over-wide values to pin ABI
  masking, so the CNF-5 replay constructs Circuits with `strict=False`.
- `run_batch`'s C side scatters *every* input port each frame (arming
  dirty even on empty frames), so the loop-equivalence reference pokes
  all inputs per frame — that is the semantics `run_batch` must match.
- `from_base("/path/as/str")` parses the string as source text by design
  (typed dispatch, no sniffing); documented as a footgun in docs §3.
