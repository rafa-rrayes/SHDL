# SHDL → Base SHDL Flattener — Build Checklist

Plan reference: approved implementation plan (16 steps). Each step lands with its tests passing.

- [x] 1. Scaffolding: pyproject build config, package skeleton, source.py, diagnostics.py (+ tests)
- [x] 2. Lexer: comments (3 forms, keep leading doc), 0x/0b/dec literals, all operators, positions
- [x] 3. AST + parser: full §13 grammar incl. top, params, name templates, ranges, when/else, concat/replication, slices, init
- [x] 4. Loader (phase 1): module resolution, -I, import cycles (E0702), missing module/name (E0701/E0703)
- [x] 5. expr.py: precedence, integer /, div-by-zero, unbound identifiers
- [x] 6. Pre-mono validation: dup/reserved/primitive-shadow names, one connect, ≤1 init, ≤1 top, constant overflow (E0801)
- [x] 7. Phase 2 — monomorphization: defaults, positional/named, dependent params, loop-var-dependent args, dedup, E09xx
- [x] 8. Phase 3 — generator/conditional expansion: multi-ranges, nesting, open-ended bounds, when/else, scoping
- [x] 9. Phase 4 — expander: vectors, indices, slices, concat, replication, §6.5.2 exact expansion, E0401/E0402
- [x] 10. Phase 5 — constants: referenced-bits-only, unbounded-zero high bits, NAME_bitK, collision diagnostic
- [x] 11. Phase 6 — hierarchy flattening + netlist: inlining, prefixing, pass-throughs, alias cycles, ports, init, E05xx
- [x] 12. Timing: depths, SCC feedback (Clock, SRLatch), critical path, output_depths (module written; verified on Add2: max_depth=5, Sum_1_=2/Sum_2_=4/Cout=5, real-edge critical path)
- [x] 13. Metadata + emitter: all 10 blocks, canonical JSON, cross-check names exist in core (verify_meta runs in pipeline)
- [x] 14. Pipeline + CLI: --top, -I, -o, --timestamp, SOURCE_DATE_EPOCH, top selection rules (smoke-tested on add2 fixture)
- [x] 15. Evaluators + equivalence: baseshdl parser, base_eval, high_eval, random-vector trace equality
- [x] 16. E2E + hardening: determinism byte-compare, §3.7 conformance, diagnostics matrix, ruff clean

Deviation from plan layout: no separate `netlist.py` — its responsibilities landed in
`phases/expander.py` (per-component connection validation) and `phases/flatten.py` (FlatNetlist).

## Review

**Final state: 211 tests passing, ruff clean, deterministic output verified.**

Test suite: 18 files. Unit coverage per stage (lexer, parser, loader, expr,
validate, monomorphize, expand, expander, constants, flatten, timing,
metadata, emit, cli), plus five cross-cutting suites:

- `test_equivalence.py` — dual reference evaluators: `BaseEval` interprets the
  emitted Base SHDL text, `HighEval` independently interprets the phase-3
  model via union-find alias classes. Per-cycle trace equality over random
  vectors (13 combinational fixtures with functional oracles, exhaustive
  Add2), scripted feedback traces (SRLatch set/hold/reset, 20-stage Clock
  ring), settle-fixpoint and settle-refused-under-feedback checks.
- `test_diagnostics_matrix.py` — one positioned trigger per diagnostic code,
  pinned to the ErrorCode enum by a completeness assert. E0504 (structurally
  unreachable through the pipeline: role checks partition sources from
  destinations) exercised by monkeypatching `_check_role` out.
- `test_spec_examples.py` — order-insensitive conformance against the §3.7
  Add2 listing (verbatim), §4.4 hierarchy ports, resolved §4.7 timing.
  Documents that §4.9's "22 connections" contradicts §3.7's own 23.
- `test_determinism.py` — double-run byte-compare over all fixtures,
  SOURCE_DATE_EPOCH pinning.
- `test_emit.py` — every fixture re-parsed with the independent `baseshdl`
  reader; meta JSON round-trips.

Bugs found by the suite (all in previously "done" steps — the suite earned
its keep):

1. **E0311 never fired** (`monomorphize.py`): the spec-memo check ran before
   the recursion-stack check, but a spec registers in `mono.specs` *before*
   its body walk finishes, so a recursive instance hit the memo and returned
   silently → infinite recursion in flatten. Fix: check the stack first.
2. **Multi-range bare values misread** (`expand.py`): `[1:2, 4, 5:5]`
   expanded `4` as the count form 1..4 instead of the single value 4
   (spec §7.1: `[1:4, 8, 12:16]` includes just 8). Fix: count form only
   applies to a sole bare range.
3. Two test-side fixes: `N{x}` asserts the parser's documented tie-break
   (name template; identifier-count replication needs signal-only contents
   like `N{x.O, y}`), and an init-block unpacking typo.

---

# Phase 1 — Base SHDL → C Compiler (shdlc) — Build Checklist

Plan reference: approved Phase-1 plan (Base SHDL → readable C → shared
library exporting the release ABI `reset`/`poke`/`peek`/`step`; unit-delay
two-buffer model per shdl.md §11 / shdlc_goals.md §2; no optimizations).

- [x] 0. Rename: flattener package `shdlc/` → `flattener/`, console script → `shdl-flatten`
      (distribution name stays `shdlc`); untracked committed `__pycache__`, added `.gitignore`
- [x] 1. Compiler skeleton: new `shdlc/` package; `baseshdl.py` + `sim/base_eval.py` moved
      in (consumer-side modules); frozen seams (model dataclasses, cc/compile signatures)
- [x] 2a. `model.py`: `build_circuit` — 8-rule validation (name uniqueness, endpoint
      resolution, pin arity, single drivers, completeness, alias-chain resolution to
      ultimate drivers, ports incl. width 1..64, init resolution; strict on passthrough
      seeds where BaseEval was lenient) — 54 tests
- [x] 2b. `cc.py`: discovery (`--cc` → `$CC` → cc/clang/gcc, shlex-split), suffix per
      platform, CCError with argv + compiler stderr verbatim — 21 tests
- [x] 2c. `codegen.py`: per-gate emitted C (one line per gate, named enum indices,
      gate-name comments), two-buffer tick with single pointer-swap commit,
      recompute_outputs after commit, `^ 1u` NOT, VCC/GND recomputed per tick,
      per-bit scatter/gather (no width-64 UB), SHDLC_API on exactly the 4 ABI fns,
      `__GNUC__` constructor → reset, byte-deterministic — 29 structural tests
- [x] 2d. Verification suite: ctypes harness (RTLD_LOCAL, per-instance dylib copies),
      DualSim lockstep vs BaseEval (raw pokes to lib / masked to oracle), STRICT_CFLAGS
      (-Wall -Wextra -Werror -pedantic) on every test build, fuzz generator
      (leveled DAG + feedback rewires + random ports/init, self-checked via BaseEval)
- [x] 3. Integration: `compile.build_library`, `shdlc` CLI (Base or .shdl input,
      --base/--shdl, -o, --emit-c, --no-build, --cc; --top/-I rejected for Base) —
      full suite green on first integrated run
- [x] 4. Adversarial verification: 4 read-only reviewers + soak
      (SHDLC_FUZZ=100 × 500 cycles, SHDLC_DIFF_CYCLES=1000 — green)
- [x] 5. Wrap-up: docs, this section, final suite run

## Review

**Final state: 435 tests passing (211 flattener + 224 compiler), ruff clean,
soak green, byte-deterministic C verified across processes.**

Compiler suite: 21 files. Semantics pinned cycle-by-cycle against BaseEval
(the flattener-verified oracle): primitives incl. cycle-0 zeros and the
VCC→NOT trace `[0,1,0,0,...]`; anti-settling (adder8 per-cycle Sum trace, ≥8
distinct values, Cout 0@15/1@16); srlatch exact transient traces incl.
Q==Qn states mid-flip; 20-stage ring one-hot rotation; reset/init (constructor
seeds live at load, idempotence, reset==fresh-load); lazy-peek lifecycle
(exactly-one-hidden-tick pinned via the clock-ring thermometer counter);
LSB-first scatter/gather, masking, 64-bit ports; per-handle independence of
simultaneously loaded libraries; `nm -gU` = exactly the 4 ABI symbols;
differential + fuzz lockstep on every fixture and random netlists.

Adversarial review (4 independent reviewers, all core claims HOLD; one
reviewer built a topological-settle mutant and confirmed three independent
assertions kill it). Confirmed findings, all fixed:

1. **uint16_t wire-table ceiling**: >65535 input wires would silently
   truncate initializers under release cflags (no -Werror). Fix: ModelError
   at the boundary (`test_too_many_input_wires_rejected`).
2. **Oracle bug — BaseEval._seeded_gate was single-hop**: a multi-hop
   output-alias chain (`g.O -> W2; W2 -> W1` with `init {"W1": …}`) silently
   dropped the seed in the oracle while the compiler applied it correctly
   (spec-correct). Fix: follow the chain; error on passthrough/unresolvable
   keys. Regression: `test_multi_hop_alias_init_seeds_driving_gate`.
3. **Mutation-testing gaps** (code was correct, behavior unpinned):
   `dirty = 0` deletion from reset() survived the suite → pinned by
   poke→reset→peek; unknown-name poke arming dirty would have survived →
   pinned via the clock counter; negative step pinned; deterministic
   scrambled-order meta.ports regression added (was fuzz-only coverage).

Known limitations (documented, deliberate): load-time constructor is
`__GNUC__`/`_WIN32`-gated (MSVC would need an explicit reset() before first
peek); duplicate/shared wires across port groups are permitted by the spec
and behave identically (last-write-wins) in lib and oracle, but are
unspecified in shdlc_goals.md; `peek` of an output is a mutating read when
dirty (spec-mandated single evaluation).

---

# Perf fixes — large-circuit flatten + compile (2026-06-10)

Diagnosis (RAM256, 37,429 gates): `flatten_program` 9.7s — 8.1s in quadratic
`add_line` list-dedup (worst bucket: 32,768 gates on ram.shdl:24, ~1.9B string
compares); `build_library` ~58s — 56s of it clang -O2, 87% in the Machine
Instruction Scheduler on the single 37k-statement tick() basic block of
`uint8_t` (char) stores through global pointers (char aliases everything →
quadratic dependence graph). Validated remedy: restrict *parameters* +
noinline chunks of ~1024 → 10.7s (-O2); block-scope restrict locals only
reach 32.8s — LLVM exploits parameter noalias far better. `-O0` builds in
1.1s. Sim runtime itself fine (full probe 0.8s on a prebuilt dylib).

- [ ] 1. flatten: ordered-set dedup in `add_line` (`phases/flatten.py`);
      emitted text byte-identical on all fixtures + RAM256 (hash compare)
- [ ] 2. codegen: chunked tick for >1024-gate circuits — SHDLC_NOINLINE chunk
      fns taking `(const uint8_t *restrict c, uint8_t *restrict n)` (`n`-only
      when a chunk reads no gate outputs); ≤1024 gates byte-identical to today
- [ ] 3. tests: chunk-path structural tests (threshold boundary, statement
      order across chunks, n-only signature, STRICT_CFLAGS build) +
      differential behavioral test on a >1024-gate netlist
- [ ] 4. verify: RAM256 flatten ~1.6s, -O2 build ~11s, probe-equivalent
      behavior vs pre-fix dylib; full pytest + ruff green
- [ ] 5. review section + memory updated

## Review

(pending)

---

# Phase 2 — Conformance Suite — Build Checklist

Plan reference: agent assignment "Build the SHDL Conformance Suite"
(SHDL_Project.md §4.13). Freezes the observable contract: SHDL → Base SHDL
byte-exact goldens (Tier A), ABI-level golden traces (Tier B), ABI contract
edges (Tier C). All golden values from BaseEval / hand-derivation, never
from the C implementation under test.

## Design decisions (made up front)

- **Layout**: `conformance/` is a Python package holding the data corpus
  (`MANIFEST.json`, `conformance.md`, `cases/<name>/`) and the runner
  subpackage (`conformance/runner/`). Console script `shdl-conformance`.
- **Cases are self-contained**: every `.shdl` source a case imports is
  copied into the case directory (corpus outlives `examples/`).
- **Tiers B/C compile the frozen `expected.base.shdl`**, not a fresh
  flatten. Tier A separately asserts flatten(circuit.shdl) == frozen bytes;
  together they chain the pipeline, and a third-party compiler can consume
  base+traces without the SHDL front-end. (Deliberate deviation from the
  assignment's "flatten, build_library" phrasing — documented rationale in
  conformance.md.)
- **Trace format**: JSON, `trace_format: 1`, ordered `ops` list of
  `reset` / `poke {signal, value}` / `step {cycles}` / `expect {signal,
  value}`; every trace must begin with `reset`. `expect` is an ABI `peek`
  plus comparison (hidden-tick-iff-dirty semantics apply and are part of
  the contract under test).
- **Oracle adapter**: `conformance.runner.oracle.OracleSim` wraps BaseEval
  with the documented ABI dirty/lazy-peek rules (shdlc_goals.md §3.1,
  harness docstring). It generates all trace expect values and is itself
  cross-checked against the compiled C by `verify-oracle` lockstep.
- **Lockstep**: verify-oracle replays each trace against OracleSim + Sim
  simultaneously, comparing every port after reset / every cycle / every
  expect. This generalizes DualSim's clean-point-only rule (DualSim cannot
  follow hidden ticks); DualSim itself stays serving the unit tests.
- **Harness reuse**: move `Sim`, `load_fresh_copy`, `STRICT_CFLAGS`,
  `identity_ports`, `parse_with_ports`, `make_oracle` into importable
  `shdlc/harness.py`; `tests/compiler/harness.py` re-exports (435 tests
  untouched).
- **Determinism**: flatten timestamp pinned suite-wide to
  `2026-01-01T00:00:00Z` (MANIFEST `flatten_timestamp`); reports carry no
  wall-clock times or temp paths; all listings sorted.

## Checklist

- [x] 1. Harness refactor: `shdlc/harness.py` + re-export shim; full suite green
- [x] 2. Runner package: schema/loader (strict, loud on missing artifacts),
      OracleSim, executor (replay/fill/lockstep), tier runners, deterministic
      report, CLI (`run`, `verify-oracle`, `regen --case`, `list`);
      pyproject console script + package registration
- [x] 3. Corpus (~24 cases): degenerate (inverter, passthru, wide64),
      primitives/derived (fullAdder, gates-demo), adders (add2, adder8
      ripple-watch, add100, adderN multi-binding), const (const-bits,
      const-vcc-cycle0), wiring (splitByte, busOps, concatDemo), select
      (mux2, muxN4, comparator), state (srlatch, dlatch, registerN,
      ringClock, clock20 tick-counter), hierarchy (pipe, repeater),
      composite (alu, cpu-rege if it flattens) — landed as 32 cases
- [x] 4. Tier C ABI traces: poke-mask, peek-hidden-tick-iff-dirty (incl.
      repoke re-arms), peek-input-never-ticks/preserves-dirty, step(0),
      reset idempotence + init seeding, __VCC__ cycle-0
- [x] 5. Goldens generated (flatten + OracleSim fill), each case verified
      against compiled C as authored
- [x] 6. MANIFEST.json with feature-coverage map; runner validates coverage
      of the required feature list and manifest↔disk consistency both ways
- [x] 7. conformance.md: layout, schemas (case/trace/manifest), worked
      example, provenance + regen + versioning policy, third-party guide
- [x] 8. tests/test_conformance.py: integrity + per-case Tier A + per-trace
      C / oracle / lockstep, compile-once-per-case
- [x] 9. Acceptance: full pytest green (435 + new), run twice byte-identical,
      verify-oracle green, delete-a-golden fails loudly, coverage map
      complete, SHDL_Project.md §7 updated, review section below

## Review — Phase 2 (Conformance Suite) — 2026-06-10

**Landed.** Suite v1.0.0: 32 cases, 34 traces, 36/36 required features
covered. `conformance/` package (corpus + runner), `shdl-conformance` CLI,
`conformance/conformance.md`, `tests/test_conformance.py` (68 tests),
`scripts/build_conformance_corpus.py` kept as the authoring provenance
record (maintenance goes through `regen`, never this script).

**Acceptance evidence (all run this session):**

1. `uv run pytest`: **553 passed, 2 failed** — the 2 failures are the
   pre-existing `tests/cpu/test_ram.py` value-asserts in untracked WIP CPU
   work (known RAM decode bug, predates this phase; verified the fixture
   imports my shim re-exports verbatim). All 435 baseline + compiler tests
   untouched and green; 68 new conformance tests green.
2. `shdl-conformance run`: 66 checks (32 Tier A + 34 traces), 0 failures.
   Run twice → reports byte-identical (`diff` clean).
3. `shdl-conformance verify-oracle`: 34 checks, 0 failures (goldens
   re-derivable from OracleSim + oracle/C lockstep agreement).
4. Coverage map: no uncovered required feature (enforced in `load_suite`,
   exercised by the integrity test).
5. Deleting a golden fails loudly by name: demoed for both
   `expected.base.shdl` and a trace file → exit 1,
   `missing golden artifact: conformance/cases/<...> (listed in <case.json>)`.
6. `regen --case mux2` dry run: "unchanged / nothing to do", writes nothing.
7. Every golden's provenance recorded in `case.json` (`provenance.expected_base`
   / `provenance.traces`) + per-trace `provenance` string.

**Bugs found & fixed during bring-up (all in new code; flattener/shdlc
untouched per ground rules):**

- Previous session's harness refactor was never persisted — re-executed it
  for real (`shdlc/harness.py` + re-export shim).
- schema.py counted `expected.base.shdl` as an unlisted source
  (glob overlap); fixed by excluding `expected_base.name`.
- suite.py `CaseBuild` never created its per-case work dir → all B/C
  builds failed with ENOENT; one-line `mkdir(parents=True)`.

**No spec ambiguities or implementation divergences surfaced** — no known
divergences to record; the C implementation matches BaseEval+ABI oracle at
every observation across the corpus.

**Deviation (documented in conformance.md §3):** Tiers B/C compile the
frozen `expected.base.shdl`, not a fresh flatten — flattener regressions
isolate to Tier A; backend regressions to B/C.

---

# 2026-06-10 — Profile SR16 mul.s (lab-journal style)

Journal: `examples/CPU/profiling/journal.md`. Each experiment recorded as it runs.

- [x] Exp 0: Baseline — netlist size, tick accounting, end-to-end wall time of stock run
- [x] Exp 1: ABI microbenchmarks — ns/tick, step/peek/poke per-call overhead, name-scan order
- [x] Exp 2: cProfile of full run — wall-time share of step/peek/poke vs Python
- [x] Exp 3: Per-asm-op cycle census — clocks + wall time per opcode
- [x] Exp 4: Settle-margin search — min T_SETTLE that stays golden-correct, speedup
- [x] Exp 5: Host-overhead reduction — leaner Python clock loop; native C driver
- [x] Exp 6: Multiplication throughput shootout — algorithms × driver variants → mults/sec
- [x] Review section + journal conclusions

## Review (profiling session)

All experiments in `examples/CPU/profiling/journal.md`; scripts alongside it. Headlines:
- Stock mul.s = 456 ms (2.2 mults/s); 99.4% of wall time is `step()` (23.2 µs/tick × 19,500 ticks).
- Clock budget: stable minimum settle=29/cap=16/gap=4 (69 ticks vs stock 240, 3.5×) — but settle
  26–28 is a tick-parity-flickering marginal band, found via worst-case-operand lockstep (new lesson).
- Asm op costs: pure clock count (POP/RET 3, rest 2). Best generic mul: shift-add 54 clocks.
- Peak: 38 mults/s single-core, 325/s on 10 processes (~150× vs stock). Driver budgets left untouched.

# Batch ABI + fixed-point settle (step_settle / run_batch)

Additive release-ABI extension; step()/poke()/peek()/reset() byte-semantics untouched.

- [x] codegen.py: emit `step_settle(int) -> int` (tick + memcmp(cur,nxt) fixed-point exit) and
      `run_batch(in, out, count, cycles, settle)` (poke-scatter / step / peek-gather per frame)
- [x] shdlc_goals.md §3.1: document the two new entries
- [x] ABI-pin tests: test_codegen section order + API list, test_symbols export set
- [x] new tests/compiler/test_batch_settle.py: step-vs-settle twin equivalence, oscillator runs
      full budget, settle return values, run_batch == scalar sequence (both modes, cycles=0 lazy
      tick, count=0)
- [x] shdlc/harness.py Sim: bind + wrap step_settle / run_batch
- [x] sr16tools/driver.py: opt-in fast_settle=True (step() routes through step_settle)
- [x] bench_adder16.py: three timed modes (python loop / batch exact / batch settle)
- [x] verify: compiler suite, cpu suite, conformance, bench numbers, SR16 mul.s timing

# Compile-time 10x plan (measured 2026-06-11, RAM256 37,429 gates, 10-core M-series)

Baseline 10.55s total: flatten 0.63 / emit+parse+gen 0.72 / clang -O2 9.16.
All numbers below measured via /tmp experiments on the real generated C.

- [x] 1. Table-driven reset(): replace 16,384 per-seed stores with static
      `{uint32_t wire; uint8_t val;}` table + loop (codegen.py — uint32:
      gate slots are uncapped, unlike the uint16 input-wire tables). LANDED:
      release build 10.55s→9.13s. Verified: compiler suite 240, conformance
      68, reset pins in test_codegen.py updated to the table form.
- [ ] 2. Multi-TU emission + parallel cc: emit chunk functions into K .c files
      + common header, compile with N parallel `cc -c`, link (codegen.py,
      cc.py, compile.py). cc step 9.16s→1.34s measured. Verify conformance +
      bench unchanged.
- [ ] 3. In-memory handoff: build shdlc Circuit straight from FlatNetlist;
      emit .bshdl text only when requested. Saves 0.66s (emit 0.12 +
      parse_base 0.54). Keep text path as the conformance interchange.
- [ ] 4. Build-only fast path: skip compute_timing (0.17s) + meta build/verify
      (~0.15s) when compiling to a dylib without metadata consumers.
- [ ] 5. Warm-build caching: per-TU object cache keyed by content hash (or
      ccache in cc.py) + whole-artifact cache (hash → dylib). Warm rebuild
      ≈ link-only.
- [x] Dev profile: `shdlc --dev` compiles with -O0 (DEV_CFLAGS in cc.py;
      rejected with --no-build). LANDED: RAM256 build 9.13s→2.87s via CLI.
      Verified: 561-op random lockstep (writes/reads/settles/resets) of the
      -O0 dylib against -O2 — bit-identical. Opt-in only; -O2 stays default
      (sim throughput). -O1 chunks 0.60s vs -O2 0.84s per TU: revisit with #2.

## Review (batch ABI + fixed-point settle)

Purely additive release-ABI extension; existing four entries byte-semantics untouched.
- `step_settle(n) -> int`: tick + memcmp(cur, nxt) — after the swap nxt[] holds the previous
  cycle, so one compare detects the fixed point with zero changes to tick() emission.
  Oscillators never compare equal (full budget); proving an existing fixed point costs 1 tick.
- `run_batch(in, out, count, cycles, settle)`: per frame poke-scatter / step or step_settle /
  peek-gather, replicating lazy-peek (dirty) semantics exactly. No strings on the hot path.
- Full suite 609 passed (compiler + cpu + conformance). New tests/compiler/test_batch_settle.py
  pins twin-sim equivalence, oscillator full-budget, settle return values, lazy-tick edge cases.
- Adder16 bench (100k adds, settle budget 35): scalar 420k adds/s -> batch 1.08M (2.6x) ->
  batch+settle 3.0M adds/s, 333 ns/add (7.2x). All modes verified against Python.
- SR16 `fast_settle=True` driver opt-in: mul/popcount/maxarray match golden + exact mode
  bit-for-bit (cycles, regs, pc, mem); 4.5-5.4x wall clock (mul.s 454 -> 98 ms).

## Review (golden_tests.md exhaustive audit revision, 2026-06-12)

Full re-derivation of every claim in golden_tests.md from primary sources (4 spec docs read in
full; 15 parallel auditors + adversarial skeptic verification per change; 59 agents total).
Document revised in place (492 -> 630 lines). Headlines:
- 31 status corrections (16 downgrades incl. FLT-4 "CPU hits depth>=10" — measured max is 6;
  9 upgrades incl. ABI-8 — the 64/65 boundary test already exists; 6 in-place qualifier fixes).
- 69 new obligation rows (LEX-9..11, PAR-10..12, VAL-8/9, MON-8, GEN-12..14, EXP-11..13,
  CON-7/8, FLT-9..11, IMP-7..11, MET-10/11, DET-6/7, TIM-6/7, DIA-8/9, SIM-11, ABI-11..19,
  CCT-9..19, FUZ-8, CNF-6..9, SCL-7, ROB-5/6, CPU-7..13).
- 29 new ambiguities (AMB-13..41), incl. 5 outright spec contradictions (import search order,
  stdgates primitive import, ConstantDecl width grammar, reset semantics, ABI surface drift).
- 5 reproduced live crashes violating crash closure: invalid UTF-8 (both CLIs), malformed meta
  JSON (shdlc), garbage SOURCE_DATE_EPOCH, lexer `²` int() ValueError, 400-deep RecursionError.
- Authoritative counts established: 99 raise err( sites (was "~70"), 58/99 executed; 41 codes
  confirmed; 35 ModelError sites (30 tested); 22 bare asserts + 25 raise-AssertionError guards;
  609 collected tests.

---

# Golden Test Suite Build (2026-06-12)

Plan: execute the gap register of `golden_tests.md` (P0 + P1 + local P2) via parallel
work packages with strict disjoint file ownership. Baseline: 609 passed.

## Phase 1 — implementation fixes + owned-domain tests (parallel)
- [x] WP-A flattener frontend: crash closure (LEX-9/10, PAR-8, SOURCE_DATE_EPOCH, AMB-14/15/29),
      LEX-3/6/7/8/11, PAR-1/4/7/9/10/11/12, IMP-4/5/7/8/9/10/11, DET-4 idempotence, DIA-9
- [x] WP-B shdlc side: CCT-7/8/9/10/11/12/13/15/17/18/19, ABI-4/6/7/8/12/13/14/15/16/17/19,
      SIM-6/10/11, AMB-32/33/34/35/36, ROB-2 (deferred: ABI-13 Linux ELF variant)
- [x] WP-C spec amendments: all AMB-1..41, DIA-4/5/6 policy pins, SCL-6 limits, AMB-37/38/39/41
- [x] WP-D flattener phases: VAL-1/2/5/8/9, MON-2/3/5/6/7/8, GEN-1/3/5/7/8/10/11/12/13/14,
      EXP-5/6/8/9/10/11/12/13, CON-2/4/7/8, FLT-4/6/7/8/9/10/11, ROB-1/5 classification
- [x] WP-E flattener output: MET-4/7/8/9/10/11 (public validator, ROB-3), DET-3/6/7, TIM-5/6/7
      (DET-6 bare-stdout half closed in the follow-up pass: UTF-8 via sys.stdout.buffer)

## Phase 2 — adversaries, corpus, scale (parallel, after Phase 1)
- [x] WP-F DIA-2 per-raise-site matrix + DIA-3/7/8 format/message/position accuracy
- [x] WP-G FUZ-3 SHDL-source fuzzer
- [x] WP-H FUZ-4 no-crash fuzzer + FUZ-5 generalization + FUZ-8 docstring
- [x] WP-I conformance: CNF-4 additions, CNF-6/7/8/9
- [x] WP-J CPU tier: CPU-8 freeze, CPU-11/12/13
- [x] WP-K scale: SCL-3/4/5/7 + range-bomb cap; CI workflow (deferred: CCT-6 Linux CI unproven;
      SCL-7 replication-count guard closed in the follow-up pass)

## Phase 3 — verification loop until full suite green
- [x] Full suite green: 1643 collected, 0 failed (verify result {"all_passed":true,"total":1643})

## Phase 4 — golden_tests.md status update + review here
- [x] golden_tests.md statuses updated; review below

Safety: pre-run working-tree snapshot at /tmp/shdlc-pre-golden-baseline.patch

## Review — Golden Test Suite Build (2026-06-12)

**Final state: 1644 collected tests, 0 failed (baseline 609 → +1035 tests, +~8.3k test lines).**
Eleven work packages with strict disjoint file ownership + a verify/fix loop, plus a follow-up
pass that closed four of the packages' cross-ownership residuals (see below). Every domain row
in `golden_tests.md` Domains A–T and W is now ✅ except 3 precisely-named partials and 1 optional
❌ (FUZ-7). Conformance corpus grew v1.0.0 (32/34) → v1.1.0 (38 cases / 40 traces).

**Major behavior changes landed (root-cause source fixes, all minimal):**
- *Crash closure* — five reproduced live crashes fixed on the flattener side: lexer pinned
  ASCII-only (`²`→`int()` ValueError closed, E0101); loader decodes UTF-8 in a try → positioned
  E0101 (invalid-UTF-8); `SOURCE_DATE_EPOCH` garbage → structured E0001; parser nesting cap
  MAX_NESTING_DEPTH=200 → E0201 (400-deep RecursionError closed); shdlc `meta` JSON wrapped in
  BaseParseError (raw JSONDecodeError closed).
- *Caps* — `MAX_RANGE_VALUES=1_000_000` guards the four range_values sites → E0601 (range-bomb
  `[1:10⁹]` now sub-ms instead of OOM); mirrors the compiler-side `_MAX_INPUT_WIRES`.
- *New diagnostics (all reusing existing codes, no new ErrorCode)* — E0701 for AMB-27 resolved-
  path mismatch + AMB-28 case-mismatch; AMB-34 rejects duplicate input-wire refs in meta.ports;
  AMB-35 requires both port direction keys; AMB-32/ABI-16 NULL-name guard in generated C.
- *New public API* — `metadata.validate_meta` + `MetaValidationError` (MET-7/ROB-3, survives
  `python -O`); the AMB-29 trailing-`meta`-block parser production (unblocks DET-4); `parser.
  MAX_NESTING_DEPTH`; `expand.MAX_RANGE_VALUES`.
- *Spec amendments* — all 41 AMBs amended into shdl.md/base_shdl.md/shdlc_goals.md as native
  prose; DIA-4/5/6 pinned as V1 non-goals (fail-fast, no warnings, no suggestions, §14.1);
  SCL-6 limits documented (max port width 64, max input wires 65535, gates deliberately uncapped).

**Bugs the new adversaries found:** the FUZ-3 SHDL-source fuzzer and the FUZ-4 no-crash
campaigns (SHDLC_NOCRASH=2000 + 66k out-of-band inputs, high-vs-base 1000/1000) surfaced **no
real flattener or oracle divergences** — the only failures were the FUZ-3 generator's own
valid-by-construction bugs (fixed at source) and the FUZ-5 adversary's dirty-flag model desync
(the C `run_batch` leaves dirty SET only when nframes>0 ∧ cycles≤0 ∧ zero output ports; the old
adversary cleared it on any framed batch — fixed to model the per-frame state machine exactly).
That the adversaries found no implementation bugs is itself the strongest evidence the prior
suite was already sound.

**Closed in the follow-up pass (were cross-ownership residuals):**
- *ROB-6 / LEX-10 (shdlc side)* — `shdlc/cli.py` now reads bytes and decodes with a structured
  BaseParseError naming the byte offset; the STRICT xfail flipped to a regular passing test.
- *DET-6* — `flattener/cli.py` writes stdout as UTF-8 via `sys.stdout.buffer`; the
  bare-stdout-under-C-locale xfail flipped to a regular passing test.
- *ROB-1* — `codegen.py`'s unknown-gate-type `ValueError` converted to a commented
  internal-invariant `AssertionError` (route a; unreachable past parse_base + model validation).
- *SCL-7* — `_guard_span` added at expand.py's RRepl resolve site; literal-count replication
  bombs (`{10⁹{Sign}}`) now fail fast with the cap's E0601 (pinned in test_scale.py).

**Open / residual (honest list, by ID):**
- *DET-4* — idempotence is pinned on the structural core of plain-identifier fixtures only;
  bus-port fixtures emit `X_1_` names that re-flattening rightly rejects (E0304) — by design.
- *CCT-6 / ABI-13 (Linux) / FUZ-6 / coverage gate* — ci.yml + nightly.yml authored and
  YAML-validated, but the Linux/gcc + Linux/clang generated-C builds, the ELF export-set
  variant, the soak job, and the coverage ratchet are all UNPROVEN until one real CI pass.
- *FUZ-7* — mutation testing remains optional/post-V1 (❌ by design).
