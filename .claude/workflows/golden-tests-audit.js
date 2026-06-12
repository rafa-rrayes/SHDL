export const meta = {
  name: 'golden-tests-audit',
  description: 'Exhaustive audit of golden_tests.md against specs, code, and tests',
  phases: [
    { title: 'Audit', detail: '15 parallel auditors: domains, specs, robustness, adversarial, consistency' },
    { title: 'Verify', detail: 'independent skeptic per proposed status change' },
  ],
}

const AUDIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status_checks', 'new_obligations', 'doc_errors', 'new_ambiguities', 'notes'],
  properties: {
    status_checks: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id', 'doc_status', 'verdict', 'proposed', 'reason', 'evidence'],
      properties: {
        id: { type: 'string' },
        doc_status: { type: 'string', description: 'status emoji + qualifier exactly as in the doc' },
        verdict: { type: 'string', enum: ['confirmed', 'change'] },
        proposed: { type: 'string', description: 'new status text incl. emoji and named hole(s); empty string if confirmed' },
        reason: { type: 'string' },
        evidence: { type: 'array', items: { type: 'string' }, description: 'path:line or path:line-range — note. REQUIRED even for confirmed rows: cite the test that justifies the status.' },
      } } },
    new_obligations: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['domain', 'obligation', 'suggested_status', 'reason', 'evidence'],
      properties: {
        domain: { type: 'string', description: 'three-letter domain code, e.g. LEX' },
        obligation: { type: 'string', description: 'row text for the new obligation, same tone as existing rows' },
        suggested_status: { type: 'string' },
        reason: { type: 'string' },
        evidence: { type: 'array', items: { type: 'string' } },
      } } },
    doc_errors: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['where', 'claim', 'actual', 'evidence'],
      properties: {
        where: { type: 'string', description: 'location in golden_tests.md (section / row)' },
        claim: { type: 'string' },
        actual: { type: 'string' },
        evidence: { type: 'array', items: { type: 'string' } },
      } } },
    new_ambiguities: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['description', 'spec_ref', 'proposed_resolution'],
      properties: {
        description: { type: 'string' },
        spec_ref: { type: 'string' },
        proposed_resolution: { type: 'string' },
      } } },
    notes: { type: 'string' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['upheld', 'final_status', 'explanation', 'evidence'],
  properties: {
    upheld: { type: 'boolean', description: 'true if the proposed status change survives adversarial scrutiny' },
    final_status: { type: 'string', description: 'what the status should actually be (may differ from both doc and proposal)' },
    explanation: { type: 'string' },
    evidence: { type: 'array', items: { type: 'string' } },
  },
}

const PRE = `You are one auditor in a multi-agent audit of /Users/Rafa/Code/Python/shdlc/golden_tests.md — the authoritative coverage plan for the SHDL golden test suite. Repo root: /Users/Rafa/Code/Python/shdlc (a Python project; flattener/ lowers SHDL to Base SHDL, shdlc/ compiles Base SHDL to C, tests/ is pytest, conformance/ is a frozen corpus).

FIRST read /Users/Rafa/Code/Python/shdlc/golden_tests.md in full so you understand the document's structure, ID scheme, status legend (✅ covered / 🟡 partial with named holes / ❌ missing / ⚪ blocked), and tone.

VERIFICATION STANDARD — treat every claim as unverified until you re-derive it:
- A row is ✅ only if you can cite a specific test function that ACTUALLY ASSERTS the described behavior (file:line). A test that merely exercises nearby code does not count.
- 🟡 requires both halves to be true: the covered part really covered (cite it) AND the named hole really a hole (search for a test covering it and fail to find one).
- ❌ requires that NO test covers it. Search hard (grep across tests/ and conformance/ with several keyword variants) before confirming. If you find real coverage, propose an upgrade.
- When uncertain whether something is covered, propose 🟡 with the specific hole named. NEVER weaken or drop an obligation to make a status look better.
- Count raise sites by READING the code (calls may span multiple lines; grep alone undercounts attribution per error code).
- Evidence strings must be "path:line — short note". Give evidence for confirmed rows too.

Also sweep your assigned implementation files for raise sites, branches, edge cases, env vars/config flags, and public behaviors that NO existing row in your domains mentions — report each as a new_obligation (write the row text in the doc's terse style). Report factual errors in the doc (wrong counts, wrong file names, wrong claims) as doc_errors. Report any genuine spec ambiguity you discover as new_ambiguities (the doc's Domain U is the ambiguity register; check it doesn't already contain yours).

Your final output is structured data consumed by an orchestrator, not prose for a human.`

const AUDITS = [
  { key: 'lex-par', prompt: PRE + `

YOUR DOMAINS: A (LEX-1..LEX-8) and B (PAR-1..PAR-9).
Implementation: flattener/lexer.py, flattener/parser.py, flattener/source.py, flattener/ast_nodes.py.
Tests: tests/test_lexer.py, tests/test_parser.py, tests/test_diagnostics_matrix.py, tests/helpers.py (and anywhere else grep leads).
Specific checks: (a) LEX-3 claims uppercase 0X/0B prefixes are untested — also check whether the LEXER even implements them (if not, that's a doc_error-worthy nuance: the row is an implementation gap, not just a test gap). (b) LEX-6 names six E0101 raise-site categories with per-site ✅/❌ — verify each against lexer.py's actual raise sites and the tests. (c) PAR-6 claims "7 sites in parser.py" for E0201 — count the actual E0201 raise sites in parser.py and which are tested. (d) PAR-1 claims positive coverage of EVERY EBNF production in shdl.md §13 — spot-check the riskiest productions (nested replication is PAR-4; check e.g. empty port lists, mixed args, bare {A} concat, [{expr}] index). (e) PAR-8/PAR-9 holes. Also look for lexer/parser behaviors with no row at all: CRLF/BOM/tabs handling, doc-comment capture rules, number-literal edge cases, error positions.` },

  { key: 'val-mon', prompt: PRE + `

YOUR DOMAINS: C (VAL-1..VAL-7) and D (MON-1..MON-7).
Implementation: flattener/validate.py, flattener/phases/monomorphize.py, flattener/expr.py (param expression evaluation).
Tests: tests/test_validate.py, tests/test_monomorphize.py, tests/test_diagnostics_matrix.py.
Specific checks: (a) VAL-1: are accept-side boundary names (X_2, X_2_3, _x) really untested? (b) VAL-2: exactly which primitives' shadowing is tested? (c) VAL-6 claims "all 8 raise sites in expand.py" for E0306/E0307 — count actual E0306/E0307 raise sites (note: they may live in validate.py, expand.py and elsewhere; attribute precisely) and which are tested. (d) VAL-5 case sensitivity — search hard for any test with MyGate/mygate-style coexistence. (e) MON-2 full E09xx matrix — verify each code's test actually asserts code+position. (f) MON-5/MON-6 — verify the covered/hole split. Also sweep validate.py and monomorphize.py for checks with no obligation row.` },

  { key: 'gen-exp', prompt: PRE + `

YOUR DOMAINS: E (GEN-1..GEN-11) and F (EXP-1..EXP-10).
Implementation: flattener/phases/expand.py (generators/conditionals), flattener/phases/expander.py (slices/concat/replication), flattener/expr.py.
Tests: tests/test_expand.py, tests/test_expander.py, tests/test_expr.py, tests/test_diagnostics_matrix.py.
Specific checks: (a) GEN-6 claims E0601 has 8 raise sites — count them precisely and which are triggered by tests. (b) GEN-8 claims only == and && are tested among conditional operators — grep the tests for each of != < <= > >= and || in when-conditions. (c) GEN-9 claims division truncation direction INCLUDING negative operands is pinned — find the test asserting negative-operand division (and check what Python's // vs C truncation would do in expr.py: this is a classic silent-wrongness spot; if expr.py uses Python // semantics on negatives and a test pins "C-style toward zero", reconcile which is true). (d) EXP-7 claims E0505 has 6 raise sites all covered — count and verify. (e) EXP-9 self-connection E0504 "matrix only" — check what exists. (f) EXP-5 degenerate slice [k:k], EXP-10 concat both sides — search hard before confirming ❌. Also sweep expander.py/expand.py for behaviors with no row (e.g. replication of multi-item groups, nested concat handling, slice on instance ports, open-range governing-signal selection logic).` },

  { key: 'con-flt-imp', prompt: PRE + `

YOUR DOMAINS: G (CON-1..CON-6), H (FLT-1..FLT-8), I (IMP-1..IMP-6).
Implementation: flattener/phases/constants.py, flattener/phases/flatten.py, flattener/loader.py, flattener/pipeline.py.
Tests: tests/test_constants.py, tests/test_flatten.py, tests/test_loader.py, tests/test_spec_examples.py, tests/test_diagnostics_matrix.py.
Specific checks: (a) CON-2: what bit indices are actually tested against the spec §8.1 truth table? (b) CON-4 ZERO=0 — check what constants.py actually does for value 0 (width inference of 0) and whether any test pins it. (c) FLT-6 claims E0A01 has 4 raise sites all covered — count and verify; same for E0A02/E0A03. (d) FLT-2 alias cycle E0506 — verify the test. (e) IMP-4 diamond imports — search hard in tests/test_loader.py and fixtures for a diamond-shaped import test before confirming ❌. (f) IMP-1 search order (file's directory shadows -I dirs) — verify a test actually asserts the SHADOWING order, not just that -I works. (g) FLT-8 — check tests/cpu/test_poweron.py covers the instance and that no minimal pinned case exists in tests/. Also sweep loader.py for behaviors with no row (self-import, importing a primitive, use-after-component, duplicate use of same module, importing same name twice).` },

  { key: 'met-det-tim', prompt: PRE + `

YOUR DOMAINS: J (MET-1..MET-9), K (DET-1..DET-5), L (TIM-1..TIM-5).
Implementation: flattener/metadata.py, flattener/emit.py, flattener/timing.py.
Tests: tests/test_metadata.py, tests/test_emit.py, tests/test_determinism.py, tests/test_timing.py, tests/compiler/test_determinism.py (DET-5), tests/test_spec_examples.py.
Specific checks: (a) MET-4: is the gates/lines mutual-consistency check really only spot checks, or is there a property test over all fixtures? (b) MET-7: confirm the internal asserts in metadata.py and absence of a public validator. (c) MET-8/MET-9 — search for unknown-key tolerance tests and monitors-block tests (does the flattener even emit monitors? check metadata.py). (d) DET-2 SOURCE_DATE_EPOCH — verify implementation (emit.py? metadata.py doc.flattened_at) AND test. (e) DET-3 — confirm the compiler side has a fresh-process PYTHONHASHSEED test and the flattener side doesn't. (f) DET-4 idempotence — search hard. (g) TIM-5 tightness — confirm sufficiency is tested and tightness (step(max_depth-1) differs on some input) is not. Also sweep timing.py and metadata.py for behaviors with no row (e.g. output_depths for feedback circuits, critical_path under feedback, depth of constant-only outputs).` },

  { key: 'dia', prompt: PRE + `

YOUR DOMAIN: M (DIA-1..DIA-7). You are also the authoritative raise-site counter for the whole audit.
Implementation: flattener/diagnostics.py, flattener/cli.py, flattener/__main__.py.
Tests: tests/test_diagnostics_matrix.py, tests/test_cli.py.
Specific checks: (a) DIA-1: verify the completeness assertion really compares tested codes against the FULL ErrorCode enum, that all 41 codes have triggers, and that position validity (line>=1, col>=1) is asserted. (b) DIA-2 claims "~70 raise sites" — produce the authoritative count: read every file in flattener/ (including phases/ and sim/) and count 'raise err(' call sites per file and per ErrorCode (multi-line aware). Orchestrator's mechanical grep found 99 total across: expr.py 2, lexer.py 6, loader.py 6, parser.py 9, pipeline.py 2, validate.py 12, monomorphize.py 12, flatten.py 12, expander.py 14, expand.py 23, constants.py 1 — verify and attribute each to its ErrorCode, and estimate how many distinct sites the diagnostics matrix actually exercises. (c) DIA-3: verify the CLI format test asserts file:line:col: error[CODE]: message, exit code 1, and the OSError path. (d) DIA-7: list exactly which codes have message-substance assertions today. Also check: does any test assert diagnostic POSITION ACCURACY (the position points at the offending token, not just any valid position)? If not, that is a new_obligation candidate.` },

  { key: 'sim-abi', prompt: PRE + `

YOUR DOMAINS: N (SIM-1..SIM-10) and O (ABI-1..ABI-10).
Implementation: shdlc/codegen.py (the generated C's ABI), shdlc/harness.py, tests/compiler/harness.py, shdlc/sim/base_eval.py (the oracle).
Tests: tests/compiler/test_primitives.py, test_propagation.py, test_feedback.py, test_reset_init.py, test_lazy_peek.py, test_ports.py, test_edge_cases.py, test_symbols.py, test_independence.py, test_chunked.py.
Specific checks: (a) SIM-2 __VCC__ cycle-0 anti-preload pin — find the exact assertion. (b) SIM-3 Cout flips exactly at cycle 16 — find it. (c) SIM-6 order independence claims ❌ ("today only implied") — but tests/compiler/test_independence.py exists; read it carefully: does it permute declaration order and compare traces? If yes this is an UPGRADE the doc missed. (d) SIM-5 ring oscillator exact period — find it. (e) ABI-4 step negative — check codegen.py's step implementation and whether any test asserts it. (f) ABI-5 unknown-signal stderr — find the test. (g) ABI-9 two copies of same circuit via dlopen cache-busting — find it in the harness. (h) ABI-10 zero-port/zero-gate circuits — find them. (i) SIM-10 2-state guarantee — check the masking in generated C. Also sweep the generated-C ABI surface in codegen.py for behaviors with no row (e.g. poke on an OUTPUT name, peek on unknown vs empty string, NULL signal name, repeated poke same cycle, get_cycle absence in release).` },

  { key: 'cct-fuz-scl', prompt: PRE + `

YOUR DOMAINS: P (CCT-1..CCT-8), Q (FUZ-1..FUZ-7), S (SCL-1..SCL-6).
Implementation: shdlc/codegen.py, shdlc/cc.py, shdlc/compile.py, shdlc/model.py, shdlc/baseshdl.py, shdlc/cli.py.
Tests: tests/compiler/test_codegen.py, test_cc.py, test_chunked.py, test_optlevels.py, test_determinism.py, test_differential.py, test_fuzz.py, fuzz_gen.py, test_frontend_errors.py, test_model.py, test_cli.py, conftest.py.
Specific checks: (a) CCT-2 CC discovery precedence — verify tests cover CC env var, PATH search, and the precedence order. (b) CCT-3 STRICT_CFLAGS — verify the flags and that EVERY test build uses them (check conftest/harness). (c) CCT-7 claims ~40 negative cases — count the actual negative cases in test_frontend_errors.py and test_model.py. (d) CCT-8 — enumerate ModelError raise sites in model.py/baseshdl.py and which are exercised. (e) FUZ-2 — verify the fuzzer's range (5-80 gates? feedback?), self-check against BaseEval, env scaling (SHDLC_FUZZ). (f) FUZ-5 — what action-sequence randomization exists. (g) SCL-1 >1024-gate chunked — verify. (h) SCL-6 wire-index cap — find the cap in the code (codegen.py or model.py) and whether any test hits cap/cap+1. Also sweep cc.py/compile.py/cli.py for behaviors with no row (e.g. compile failure surfacing, temp-dir cleanup, .dylib vs .so suffix selection, shdlc CLI flags, missing-meta handling).` },

  { key: 'cnf', prompt: PRE + `

YOUR DOMAIN: R (CNF-1..CNF-5).
Files: conformance/MANIFEST.json, conformance/conformance.md, conformance/runner/ (all files), conformance/cases/ (list all; read 3-4 representative case dirs incl. one Tier A, one trace-bearing, one ABI case), tests/test_conformance.py, scripts/build_conformance_corpus.py.
Specific checks: (a) CNF-1: verify 32 cases / 34 traces and that the listed categories (primitives, derived gates, arithmetic, state/feedback, language features, degenerate, ABI tiers) all actually appear. (b) CNF-2: verify Tier A byte-equality and Tier B/C trace replay with lockstep divergence check actually exist in the runner/test. (c) CNF-3: verify the integrity tests (manifest<->disk bijection, minimum counts >=32/>=34, never-from-C provenance policing — is provenance actually CHECKED by a test or just documented?). (d) CNF-4: confirm none of the listed additions exist yet. (e) Check the feature-coverage check mentioned in §1.3 exists. Also report anything the corpus covers that golden_tests.md doesn't credit, and any integrity hole (e.g. traces not hashed, expected.base.shdl regenerable silently).` },

  { key: 'cpu', prompt: PRE + `

YOUR DOMAIN: W (CPU-1..CPU-6).
Files: tests/cpu/ (all test files + conftest.py), examples/CPU/ (skim structure only), tasks/cpu_todo.md if helpful.
Specific checks: (a) CPU-1: verify EVERY ISA instruction is covered in test_instructions.py and that PC, R0-R7, flags, halt, cycle cost are all asserted after every instruction (read the harness/asserts). (b) CPU-2: 13 ALU ops x corner + random x carry-in — count the actual ops tested. (c) CPU-3: 15 settle offsets / period-8 oscillation claim — verify the parametrization. (d) CPU-4 doubled budgets. (e) CPU-5: verify each named program (fib, gcd, memcpy, recursive sum, array wraparound) exists. (f) CPU-6 reserved encodings via .word. Report any CPU-tier coverage that exists but has no row (e.g. RAM tests, regfile tests, seq element tests have their own files — are they adequately credited?).` },

  { key: 'rob', prompt: PRE + `

YOUR DOMAIN: T (ROB-1..ROB-4) plus the crash-candidate inventory the doc's Domain T preamble asserts: "7 raw exceptions (KeyError in loader.py:51; ValueErrors in high_eval/base_eval/codegen) and 21 asserts".
Files: ALL of flattener/ and shdlc/ (every .py file, including sim/).
Tasks: (a) Produce the authoritative inventory: every 'raise <BuiltinError>' (non-SHDLError) with file:line, and every bare 'assert' statement AND every 'raise AssertionError' site with file:line (orchestrator's grep found 22 bare asserts and ~25 raise AssertionError sites — the doc says 21 asserts; reconcile: perhaps the doc's count predates changes, or counts only reachable ones; report the true current numbers). (b) For each raw exception, judge reachability from user input (e.g. is codegen.py's unknown-gate-type ValueError reachable given model validation upstream? is loader.py:51 KeyError reachable?). (c) ROB-2: find whether any test pins the BaseEval-stricter-than-ABI asymmetry (poke overflow raises in oracle, masks in C) — check tests/compiler/ and shdlc/sim/base_eval.py docstrings. (d) Verify ROB-1/3/4 statuses. Also check tests/compiler/test_frontend_errors.py: do any tests already cover malformed input reaching these raw raises?` },

  { key: 'spec-shdl', prompt: PRE + `

YOUR TASK: clause-by-clause normative sweep of /Users/Rafa/Code/Python/shdlc/shdl.md (the SHDL language spec, 995 lines) against golden_tests.md.
Read shdl.md IN FULL, section by section (§2 lexical through §14 constraints). For every normative statement (MUST-level behavior, defined semantics, error condition, reserved thing, defined default), find the golden_tests.md obligation row that covers it. Report every normative statement with NO corresponding obligation as a new_obligation (assign it to the best-fitting existing domain, write the row in the doc's style, and set suggested_status by searching tests/ for coverage — cite tests if found).
Statements to scrutinize especially (non-exhaustive): §2.1 trailing-comment placement; §2.2 the exact reserved bus pattern (digits-only between underscores) and its boundary cases; §3 module = imports then components, at-most-one-top E0310, top-with-params-requires-defaults; §4.2 declarations may interleave with init/connect; §5 multiple instances per line; §5.1 instance-port slicing (adder.Sum[1]); §6.1 valid source/destination table (every cell); §6.4 all six connection rules; §6.5 MSB-first ordering + bare {expr} one-element concat equivalence; §7.1 range table incl. compound; §7.4 context legality for generators AND conditionals in BOTH contexts; §7.7 BoolExpr grammar (parenthesized, precedence of && over ||); §8.1 unbounded-width truth table; §9.1 all four resolution rules; §10.2 derived gates inlined; §11.1 poked inputs hold across cycles; §11.4 init rules (all three); §13 grammar productions vs parser reality; §14 the full constraints table. Also report spec-internal contradictions or ambiguities not already in Domain U (AMB-1..12) as new_ambiguities. Check the doc's claim that test_spec_examples pins the spec §3.7/§4.4 examples literally (read tests/test_spec_examples.py: WHICH spec examples are pinned, and which spec code blocks are NOT tested?).` },

  { key: 'spec-base-goals', prompt: PRE + `

YOUR TASK: clause-by-clause normative sweep of /Users/Rafa/Code/Python/shdlc/base_shdl.md (519 lines) and /Users/Rafa/Code/Python/shdlc/shdlc_goals.md (241 lines) against golden_tests.md.
Read both IN FULL. For every normative statement, find the covering obligation row; report uncovered ones as new_obligations (best-fitting domain, doc's row style, suggested_status grounded by searching tests/).
Scrutinize especially: base_shdl.md §2 minimal-consumer guarantee (structural core parseable alone); §3.2 grammar (one component per file enforced? base parser in shdlc/baseshdl.py); §3.4 trailing-underscore convention; §3.6 connection rules AT THE BASE LEVEL (does shdlc re-validate single-driver/floating, or trust the flattener? check shdlc/model.py — that asymmetry needs a row); §4.2 "unknown keys ignored" + "keys in any order" + version string; §4.3 LSB-first port lists; §4.5 source_map bidirectional redundancy; §4.7 timing semantics under feedback; §4.11 init keys expanded to single-bit wires; §6 constraints tables; §7 .shdb = embedded meta + state_region byte-equal. shdlc_goals.md: §2.3 compute-commit contract consequences; §2.4 reset semantics incl. constants-not-preloaded; §3.1 ABI exact signatures; §3.2 ALL six ABI design constraints (string-lookup cold path only, global state, no caller memory, no callbacks, no thread-safety, primitive types only — is symbol visibility tested? which constraints are testable and untested?); §5.3 hot-path hard rules (no alloc/strings/branches-on-values in step — is the generated C checked for this? a test could grep the generated tick() for forbidden constructs); §7.1 reference-interpreter definition; §8 interop (dlopen/ctypes, C11 validity, self-containedness, only-public-symbols-visible). Report new ambiguities not already in AMB-1..12.` },

  { key: 'adversarial', prompt: PRE + `

YOUR TASK: hunt for missing test CATEGORIES — failure modes of a flattener/compiler/simulator that NO current domain in golden_tests.md would catch. Think like an attacker on each pipeline stage, then GROUND every idea in the actual code before proposing it (read the relevant source; if the code plainly cannot fail that way, drop the idea; if a category is already covered by an existing row, drop it).
Code to consult: flattener/pipeline.py, flattener/cli.py, flattener/source.py, flattener/emit.py, shdlc/codegen.py, shdlc/cli.py, shdlc/compile.py, shdlc/cc.py, tests/compiler/harness.py.
Candidate directions to evaluate (extend with your own): C-identifier safety in codegen (SHDL names reaching C as identifiers vs strings — can a port/gate name collide with a C keyword, the chunk function names, or internal symbols like state arrays? READ codegen.py to see how names are emitted); JSON metadata encoding edges (non-ASCII in doc strings, huge metadata, control chars in file names); source positions in SUCCESS paths (source_map line/col accuracy is MET-4, but is any position asserted exact against hand-line-numbered source?); filesystem/CLI robustness (output path unwritable, input is a directory, .shdl file imported from a path with spaces, case-insensitive macOS filesystem vs module-name case, symlink cycles in -I dirs); resource exhaustion distinct from SCL rows (generator range like [1:10**9] — is there any guard? metadata JSON of pathological size); flattener output INVARIANT properties no row states (every emitted Base SHDL passes shdlc model validation — is that property-tested across all fixtures? every gate name in source_map exists; emitted port order deterministic vs input order); harness blind spots (DualSim compares ports every cycle — are INTERNAL divergences that cancel at ports detectable? is that acceptable-by-design and worth a row saying so?); cross-version skew (flattener emits version 2.0 — what does shdlc do with version 3.0? MET-8 covers consumers 'ignoring unknown keys' but version MISMATCH specifically); init seeds interacting with reset in the C ABI vs oracle; peek of a port whose name shadows a gate name. For each surviving category, emit a new_obligation with domain assignment (may propose rows for existing domains; only invent the need for a new domain if truly nothing fits). Quality over quantity: each must name a concrete, plausible defect the current suite would miss.` },

  { key: 'consistency', prompt: PRE + `

YOUR TASK: internal-consistency audit of golden_tests.md itself (cross-references, counts, register completeness). Do NOT audit test coverage — other agents do that. Verify the DOCUMENT's self-consistency:
(a) ID uniqueness and contiguity per domain (LEX-1..8, PAR-1..9, VAL-1..7, MON-1..7, GEN-1..11, EXP-1..10, CON-1..6, FLT-1..8, IMP-1..6, MET-1..9, DET-1..5, TIM-1..5, DIA-1..7, SIM-1..10, ABI-1..10, CCT-1..8, FUZ-1..7, CNF-1..5, SCL-1..6, ROB-1..4, AMB-1..12, CPU-1..6).
(b) Every cross-reference: each "see AMB-n" from a domain row must point at the semantically MATCHING ambiguity (scrutinize ABI-7 which says "see AMB-6/spec gap" — AMB-6 is replication count 0; is that the right target or should it be a new AMB?); CNF-4's list vs the rows it references; FUZ-4's "21 asserts and 7 raw exceptions" vs Domain T's preamble (which says 7 raw + 21 asserts — internally consistent but verify the orchestrator's mechanical recount: 22 bare asserts + ~25 raise AssertionError sites + 7 raw raises; flag the doc numbers as stale if so); DIA-2's "~70 raise sites" vs the mechanical count of 99 'raise err(' sites.
(c) Gap register completeness BOTH directions: every 🟡/❌ domain row should appear in P0/P1/P2/staged (or have a defensible reason not to — list every 🟡/❌ row NOT in the register: check at least DIA-7, MET-4, MET-9, SIM-10, ABI-4, ABI-6, ABI-7, CCT-8, FLT-4, FLT-8, FUZ-5, ROB-2, SCL-6, VAL-6, GEN-6, PAR-6, LEX-6, CON-2, DET-3, CNF-4, DIA-2...), and every register entry must reference a real row with matching status.
(d) Counts in §3 and elsewhere: "600 collected tests" (mechanically verified true), "~6.5k lines" (mechanical count: 7583 lines across tests/*.py + tests/compiler/*.py + tests/cpu/*.py + conformance/runner/*.py — judge what the doc likely meant and whether to update), "32 cases / 34 traces" (true), "41/41" (true), "~280 tests" legacy claim (unverifiable — flag as unverifiable, not wrong).
(e) §1.1 oracle-chain diagram claims vs reality spot-checks other agents handle; just check internal consistency of the diagram's arrows/labels with §1.2-1.3 and Domain descriptions.
(f) Spec-section citations: golden_tests.md cites spec sections (e.g. "spec §2.3" in LEX-3, "§6.5.2" in EXP-1, "§8.1" in CON-2, "§11.4" in FLT-7, "shdlc_goals §7.1" in the §1.1 diagram, "(spec §8)" in CCT-6) — open the cited spec files and verify each citation points at the right section.
(g) Exit criteria (§6) names "Domains A-T and W" — check that's the complete set of non-future domains (U is ambiguities, V is future; is that handled correctly?).` },
]

phase('Audit')
log('Fanning out 15 auditors across domains, specs, robustness, adversarial categories, and internal consistency')

const results = await pipeline(
  AUDITS,
  (a) => agent(a.prompt, { label: 'audit:' + a.key, phase: 'Audit', schema: AUDIT_SCHEMA }),
  async (audit, a) => {
    if (!audit) return { key: a.key, audit: null, verified: [] }
    const changes = (audit.status_checks || []).filter(c => c.verdict === 'change')
    if (changes.length === 0) return { key: a.key, audit, verified: [] }
    log('audit:' + a.key + ' proposes ' + changes.length + ' status change(s); spawning skeptics')
    const verified = await parallel(changes.map(c => () =>
      agent(
`You are an adversarial verifier in an audit of /Users/Rafa/Code/Python/shdlc/golden_tests.md. An auditor proposes changing the status of obligation ${c.id} from "${c.doc_status}" to "${c.proposed}".

Auditor's reason: ${c.reason}
Auditor's evidence: ${(c.evidence || []).join(' ; ')}

Your job is to try to REFUTE this change.
1. Read the ${c.id} row in /Users/Rafa/Code/Python/shdlc/golden_tests.md to see the exact obligation text.
2. Verify each cited evidence location actually contains what is claimed (read the files at those lines).
3. Hunt for contradicting evidence: for a downgrade (✅→🟡/❌), search tests/ and conformance/ hard (multiple grep keyword variants, read candidate tests' assertions) for a test that DOES cover the behavior. For an upgrade (❌/🟡→✅ or hole-shrinking), verify the cited test really asserts the FULL obligation as written, not a fragment, and that it is a real assertion (not skipped/xfail/commented).
4. The bar: a ✅ requires a cited test function that actually asserts the described behavior. A 🟡 must name a real hole. An ❌ means no coverage exists anywhere.
Set upheld=false if the evidence does not check out OR you find contradicting coverage. final_status = what the row should actually say (may differ from both the doc and the proposal — e.g. 🟡 with a more precise hole). Be specific in evidence (path:line).`,
        { label: 'verify:' + c.id, phase: 'Verify', schema: VERDICT_SCHEMA }
      ).then(v => ({ change: c, check: v }))
    ))
    return { key: a.key, audit, verified: verified.filter(Boolean) }
  }
)

const ok = results.filter(Boolean)
log('Audit complete: ' + ok.length + '/' + AUDITS.length + ' auditors returned')
return ok