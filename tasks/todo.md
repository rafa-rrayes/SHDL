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
