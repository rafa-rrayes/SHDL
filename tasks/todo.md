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
