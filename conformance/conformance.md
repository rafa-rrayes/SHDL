# SHDL Conformance Suite

Version: see `MANIFEST.json` → `suite_version`.

This directory is the ground-truth corpus for the SHDL toolchain. The
flattener, the `shdlc` C backend, every future backend, and every
reimplementation (in any language) validate against it. The corpus is
designed to outlive all of those implementations: every artifact is plain
text or JSON, every expected value's origin is recorded, and nothing in here
requires Python to read.

---

## 1. Principles

1. **Provenance of truth.** Every golden value comes from `BaseEval` (the
   pure-Python unit-delay reference evaluator) or is hand-derived from the
   specs (`shdl.md`, `base_shdl.md`, `shdlc_goals.md`) — never from an
   implementation under test. Each case records the provenance of each of
   its goldens (§5, `provenance`).
2. **Fidelity.** Traces are cycle-by-cycle under the unit-delay model. No
   helper settles combinational logic instantly; if a circuit needs N cycles
   for a value to propagate, the trace steps N cycles and the intermediate
   states are real observable states.
3. **Determinism.** Same inputs produce byte-identical Base SHDL and
   identical traces on every platform. All timestamps are pinned
   (`MANIFEST.json` → `flatten_timestamp`). Running the suite twice produces
   byte-identical reports.
4. **The suite outlives implementations.** Case formats are readable without
   Python: plain text (`.shdl`) and JSON only.
5. **Goldens are frozen, not regenerated casually.** Regeneration is an
   explicit, single-case, reviewed operation (§9). Nothing regenerates
   automatically.
6. **A golden that cannot be checked is a failure.** Missing, de-listed, or
   corrupt artifacts fail the suite loudly, by repo-relative path.

---

## 2. Layout

```
conformance/
  MANIFEST.json            suite version, case list, feature map, changelog
  conformance.md           this document
  cases/
    <case-name>/
      case.json            case metadata (schema in §5)
      circuit.shdl         the SHDL entry point (always listed in sources)
      *.shdl               any further SHDL sources the circuit imports
      expected.base.shdl   frozen golden: the flattened Base SHDL
      traces/
        *.json             frozen golden simulation traces (schema in §6)
```

Every case directory is self-contained: `circuit.shdl` plus the other
`.shdl` files in the same directory are everything the flattener needs
(SHDL `use` imports resolve relative to the importing file's directory
first).

---

## 3. The three tiers

A case declares which tiers it participates in (`case.json` → `tiers`).

- **Tier A — flattening.** Flatten `circuit.shdl` (with `top` = the case's
  `top` field, `timestamp` = the manifest's `flatten_timestamp`) and compare
  the output **byte-for-byte** against `expected.base.shdl`.
- **Tier B — simulation.** Replay golden traces against a simulator built
  from the case's Base SHDL, checking circuit behavior (truth tables,
  propagation latency, state machines, carry ripple, oscillation).
- **Tier C — ABI semantics.** Same trace mechanics as Tier B, but each trace
  isolates one rule of the simulator control ABI (§7): poke masking, lazy
  peek, peek-of-input, `step(0)`, reset/init, `__VCC__` at cycle 0.

B and C are executed identically; the tier tag is classification. The
reference runner compiles the **frozen** `expected.base.shdl` for tiers B/C
— never a fresh flatten — so a flattener regression shows up only as a
Tier A failure and a backend regression only as B/C failures. (A consumer
testing only a flattener needs Tier A alone; a consumer testing only a
simulator backend needs `expected.base.shdl` + the traces and may ignore
`circuit.shdl` entirely.)

---

## 4. `MANIFEST.json`

```json
{
  "manifest_format": 1,
  "suite_version": "1.1.0",
  "flatten_timestamp": "2026-01-01T00:00:00Z",
  "cases": ["abi_lazy_peek", "..."],
  "required_features": { "primitive:and": "AND gate compiled and simulated correctly", "...": "..." },
  "changelog": [ { "version": "1.0.0", "date": "2026-06-10", "notes": "..." } ],
  "golden_hashes": { "conformance/cases/abi_lazy_peek/expected.base.shdl": "<sha256 hex>", "...": "..." }
}
```

| field | type | meaning |
|---|---|---|
| `manifest_format` | int | schema version of this file; currently `1`. Reject unknown values. |
| `suite_version` | string | semver of the corpus (§10). |
| `flatten_timestamp` | string | the pinned timestamp baked into every `expected.base.shdl` (`meta.doc.flattened_at`). Tier A must flatten with exactly this value. |
| `cases` | string[] | **sorted, unique** names; must match the directories under `cases/` exactly, in both directions. |
| `required_features` | object | feature key → human description. Every key must be claimed by ≥ 1 case (`case.json` → `features`); every claimed feature must exist here. This is the coverage map. |
| `changelog` | object[] | one entry per released suite version: `{version, date, notes}`. Never rewritten, only appended. |
| `golden_hashes` | object | repo-relative path → SHA-256 hex of every golden byte (each case's `expected.base.shdl` and every `traces/*.json`). The **mechanical drift fence** (§9.1): the integrity check fails if any golden's actual content hash differs from its entry, or if the map and the on-disk golden set disagree in either direction. Refreshed **only** by `regen --write`. |

---

## 5. `case.json`

```json
{
  "case_format": 1,
  "name": "mux2",
  "title": "2-to-1 single-bit multiplexer",
  "description": "Classic AND-OR select logic with fan-out on S.",
  "tiers": ["A", "B"],
  "top": null,
  "circuit": "circuit.shdl",
  "sources": ["circuit.shdl"],
  "expected_base": "expected.base.shdl",
  "traces": ["traces/select.json"],
  "features": ["primitive:and", "primitive:or", "primitive:not"],
  "provenance": {
    "expected_base": "flattener flatten_program(circuit.shdl, timestamp='2026-01-01T00:00:00Z') at suite v1.0.0 creation (2026-06-10); reviewed and frozen — modified only via 'shdl-conformance regen'",
    "traces": "expect values computed by conformance.runner.oracle.OracleSim (the BaseEval reference oracle with release-ABI peek/poke discipline) replaying the ops over the frozen expected.base.shdl; never taken from the C implementation under test"
  }
}
```

| field | type | rules |
|---|---|---|
| `case_format` | int | currently `1`. |
| `name` | string | must equal the directory name. |
| `title`, `description` | string | non-empty; human context. |
| `tiers` | string[] | non-empty unique subset of `["A","B","C"]`. |
| `top` | string \| null | component to select as top during flattening; `null` means default selection (`top` marker / single component rules). |
| `circuit` | string | the flattening entry point; must appear in `sources`. |
| `sources` | string[] | **sorted**; must match the `*.shdl` files in the case directory exactly (excluding `expected_base`), in both directions. A listed-but-missing file or an on-disk-but-unlisted file is an integrity failure naming the file. |
| `expected_base` | string | filename of the frozen flattened golden (by convention `expected.base.shdl`). Must exist. |
| `traces` | string[] | **sorted** case-relative paths; must match `traces/*.json` on disk exactly, in both directions. Required non-empty iff the case declares tier B or C; must be empty otherwise. |
| `features` | string[] | non-empty; every entry must be a key of the manifest's `required_features`. |
| `provenance` | object | `expected_base` and `traces`: non-empty strings recording where each golden's values came from (principle 1). |

---

## 6. Trace files (`traces/*.json`)

A trace is a frozen, ordered list of operations replayed against a
simulator instance. **Order is meaning**: `expect` uses real `peek`
semantics, and `peek` of an output can advance the circuit one cycle (§7),
so observation is part of the stimulus — reordering ops, even adjacent
expects of different signals, can change subsequent values.

```json
{
  "trace_format": 1,
  "name": "cycle_semantics",
  "tier": "B",
  "description": "O is 0 at cycle 0 (no tick yet), 1 after one cycle with A=0, then follows NOT A.",
  "provenance": "expect values computed by ...",
  "ops": [
    { "op": "reset" },
    { "op": "expect", "signal": "O", "value": 0 },
    { "op": "step",   "cycles": 1 },
    { "op": "expect", "signal": "O", "value": 1 }
  ]
}
```

| field | rules |
|---|---|
| `trace_format` | currently `1`. |
| `name` | non-empty; by convention the filename stem. |
| `tier` | `"B"` or `"C"`; must be declared in the case's `tiers`. |
| `description`, `provenance` | non-empty strings. |
| `ops` | non-empty list; `ops[0]` must be exactly `{"op": "reset"}` so replay never depends on prior state. |

The four operations (each op object carries **exactly** the keys shown):

| op | keys | meaning (full semantics in §7) |
|---|---|---|
| `reset` | `op` | return the simulator to its post-construction state. |
| `poke` | `op`, `signal`, `value` | drive input port `signal` with `value`. `value` is an integer in `[0, 2^64)` and **may exceed the port width**: the implementation must mask. |
| `step` | `op`, `cycles` | advance `cycles` cycles; integer in `[0, 1000000]`. `0` is meaningful (§7). |
| `expect` | `op`, `signal`, `value` | `peek(signal)` — with full peek semantics, including the possible hidden tick — and compare the result to `value`. A mismatch is a conformance failure identifying the trace, the op index, the signal, expected and actual values. |

`signal` names are **port names** from the Base SHDL `meta.ports` of the
case's `expected_base` (inputs for `poke`; inputs or outputs for `expect`).
A multi-bit port's value is the integer Σ bitᵢ·2ⁱ over its wire list, which
is listed **LSB-first** in `meta.ports`. Implementations are expected to
reject or zero-read unknown signal names; the suite's own validator rejects
any trace naming a signal not present in the frozen base's ports, so
conforming traces never exercise that path.

JSON note for non-Python consumers: values are integers up to 2⁶⁴−1, above
IEEE-754 double precision (2⁵³). Use a 64-bit-aware JSON parser (in
JavaScript, a BigInt-capable one). Every value in the current corpus is
≤ 65535, but the format allows the full range.

### 6.1 Worked example, derived by hand

Case `single_gate`: one NOT gate, input `A`, output `O`
(`A -> n1.A; n1.O -> O`). The trace above plus its continuation:

| # | op | simulator state afterwards | why |
|---|---|---|---|
| 0 | `reset` | every wire 0, inputs 0, dirty clear | §7 reset rule. |
| 1 | `expect O == 0` | unchanged | dirty is clear, so this peek does **not** tick; cycle 0 is the all-zero state — the NOT gate's output has not been computed yet. |
| 2 | `step 1` | gate evaluates: `O := NOT A = NOT 0 = 1` | one unit-delay cycle. |
| 3 | `expect O == 1` | unchanged | dirty clear after step; plain read. |
| 4 | `poke A = 1` | `A = 1`, dirty set | poke never evaluates anything. |
| 5 | `step 1` | `O := NOT 1 = 0`, dirty clear | the step consumes the dirty flag before any peek can. |
| 6 | `expect O == 0` | unchanged | |
| 7 | `poke A = 0`, `step 1` | `O := NOT 0 = 1` | |
| 8 | `expect O == 1` | unchanged | |

Every Tier B trace in the corpus follows this discipline — observe only at
clean points (right after `reset`/`step`) — so its values are exactly the
unit-delay circuit behavior. Tier C traces deliberately break the
discipline (e.g. peek while dirty) to pin the ABI's hidden-tick rules; see
`abi_lazy_peek`, whose NOT-chain output counts every tick, making hidden
ticks visible in the values.

---

## 7. The simulator contract the traces assume

These rules define a conforming simulator. They are the release control ABI
of `shdlc`-generated libraries (`shdlc_goals.md` §2–3, `shdl.md` §11); the
reference oracle (`conformance/runner/oracle.py`) implements exactly these
rules over `BaseEval`. A reimplementation must reproduce them to pass
tiers B/C.

**Evaluation model (unit delay, two buffers).** The circuit holds a current
and a next value for every gate output. One cycle ("tick"): for every gate,
compute the next output from the *current* values of its sources — gate
inputs wired to component input ports read the live input values — then
swap buffers. One gate level of propagation per cycle, never settled
instantly. Output ports read current values; combinational depth D means a
poked input reaches an output after D cycles.

**Primitives.** `AND`, `OR`, `XOR` (inputs `A`,`B`, output `O`), `NOT`
(input `A`, output `O`), `__VCC__` (output `O`, computes constant 1),
`__GND__` (output `O`, constant 0). Because `__VCC__`'s 1 is *computed* on
the first tick like any other gate output, `__VCC__` reads **0 at cycle 0**
and 1 from cycle 1 (unless seeded by `meta.init`).

**State + dirty flag.**

- `reset()` — zero all input ports and both value buffers, apply
  `meta.init` seeds to the *current* buffer only, clear the dirty flag.
  Idempotent. Construction/load behaves as if `reset` was called.
- `poke(signal, value)` — set input port `signal` to
  `value & (2^width − 1)` (oversized values are masked, never an error),
  set the dirty flag. Never evaluates the circuit.
- `peek(signal)` of an **output** port — if dirty: advance exactly one
  cycle, clear dirty; then return the port's value. (Lazy evaluation: the
  first observation after a poke reflects one cycle of propagation.)
- `peek(signal)` of an **input** port — return its current value. Never
  ticks, never touches dirty (even while dirty).
- `step(n)` — if `n > 0`: advance `n` cycles and clear dirty. If `n ≤ 0`:
  complete no-op — in particular it does **not** clear dirty.

Each Tier C case pins one of these clauses; together with Tier B they pin
all of them.

---

## 8. Provenance: where golden values come from

- `expected.base.shdl` — output of the flattener at the suite version
  recorded in the case's `provenance.expected_base`, with the manifest's
  pinned timestamp. Reviewed when frozen; changed only via §9.
- Trace `expect` values — computed by replaying the trace's own
  poke/step/expect skeleton on the reference oracle (`OracleSim`:
  `BaseEval` + the §7 ABI discipline) over the frozen `expected.base.shdl`.
  The C implementation under test never produces a golden value.
- The ABI traces (`abi_*`) were additionally hand-derived from §7 and
  cross-checked against the oracle before freezing — both derivations are
  recorded in those cases' descriptions.

`shdl-conformance verify-oracle` re-closes the loop at any time: it asserts
every stored expect value is re-derivable from a fresh oracle, and that the
oracle and the compiled C library agree at every observation in lockstep.

---

## 9. Regeneration policy

Goldens change only when the *specification* of flattening or simulation
changes — never to make a failing implementation pass.

- `uv run shdl-conformance regen --case NAME` — **dry run**: re-flattens,
  re-derives expect values over the new base, prints a full unified diff of
  `expected.base.shdl` and every changed expect value. Writes nothing.
- `uv run shdl-conformance regen --case NAME --write` — applies exactly the
  diff shown. One case at a time; there is deliberately no bulk mode.
- Regeneration only rewrites derived artifacts (the flattened base, expect
  values). Stimulus shape (pokes/steps), metadata, and descriptions are
  frozen and never touched by tooling.
- A regenerated golden requires: a reviewed diff, a **major** version bump,
  and a changelog entry naming the affected cases and the reason (§10).

### 9.1 Mechanical drift enforcement

The "bump the major version and add a changelog entry" rule above is a
*policy*; on its own it is only a printed reminder, so a coordinated edit
that changes a golden byte and forgets the version bump would pass every
live check (Tier A would still match a re-flatten, the oracle would still
re-derive the new value). To close that loophole, `MANIFEST.json` carries a
`golden_hashes` map of every golden's SHA-256 (§4), and the integrity check
(§11, and `tests/test_conformance.py::test_corpus_integrity`) verifies it:

- a golden byte that changed without its hash being refreshed fails loudly,
  naming the artifact and its expected/actual hash;
- a golden present on disk with no `golden_hashes` entry, or an entry with no
  matching golden, also fails (the map is bijective with the golden set).

The hashes are refreshed in exactly **one** place: `regen --write`, the only
sanctioned golden writer (it rewrites the changed goldens, then rewrites
their `golden_hashes` entries, then prints the major-version-bump reminder).
Hand-editing a golden therefore *must* be followed by a `regen --write` (or
the equivalent manifest refresh) and a version bump, or the suite stays red.
A purely additive change (new case or trace, §10 minor) adds new entries to
`golden_hashes`; it never rewrites an existing one.

---

## 10. Versioning policy

`suite_version` is semver over the *corpus*:

- **Major** — any change to an existing golden byte (an
  `expected.base.shdl`, or any op of an existing trace). Requires a
  changelog entry naming the cases and why.
- **Minor** — additive: new cases, new traces on existing cases, new
  required features (with covering cases).
- **Patch** — non-golden edits: descriptions, documentation, runner
  behavior.

`manifest_format` / `case_format` / `trace_format` version the *schemas* in
this document and bump only when a schema changes shape; consumers should
reject formats they don't recognize.

---

## 11. Running the suite (reference runner)

```
uv run shdl-conformance run                 # everything; exit 0 iff all pass
uv run shdl-conformance run --tier A        # one tier (A, B or C)
uv run shdl-conformance run --filter mux    # substring filter on case names
uv run shdl-conformance verify-oracle       # provenance closure (§8)
uv run shdl-conformance regen --case NAME   # §9 (dry run without --write)
uv run shdl-conformance list                # one line per case
```

Reports are deterministic (manifest order, no wall-clock, no temp paths):
two consecutive runs emit byte-identical text. Any integrity problem —
missing/corrupt/de-listed artifact, coverage gap — aborts before checking,
listing every problem by repo-relative path, with nonzero exit.

Pytest integration: `tests/test_conformance.py` exposes the same checks as
one integrity test plus one test per Tier A golden and per trace, so
`uv run pytest` covers the suite.

---

## 12. Consuming the suite from another implementation

To validate a reimplementation without any of this repo's Python:

1. Read `MANIFEST.json`; iterate `cases`.
2. **Flattener under test:** for each case with tier A, flatten
   `cases/<name>/<circuit>` (top = `top`, timestamp =
   `flatten_timestamp`) and byte-compare with `expected_base`. Encoding is
   UTF-8 with `\n` line endings.
3. **Simulator under test:** for each case with tier B/C, build your
   simulator from `expected_base` (Base SHDL grammar: `base_shdl.md`;
   ports/widths from `meta.ports`, initial state from `meta.init`), then
   replay each file in `traces` with §6/§7 semantics, comparing every
   `expect`.
4. Report failures naming case, trace, op index, signal, expected vs
   actual; exit nonzero on any failure or on any missing/unparseable
   artifact.

A conforming runner must treat the absence of a listed artifact as a
failure naming it — never skip silently.

---

## 13. Authoring a new case by hand

1. Create `cases/<name>/` with `circuit.shdl` (plus any imported `.shdl`
   files) and write `case.json` per §5 (`sources` sorted; choose `features`
   from the manifest's `required_features`; write honest `provenance`
   strings).
2. Produce `expected.base.shdl`: flatten with the manifest's pinned
   timestamp (`uv run shdl-flatten` or `flatten_program(...,
   timestamp=...)`), **review the output** against `base_shdl.md`, then
   freeze it.
3. Write each trace's stimulus skeleton (§6: `reset` first; for Tier B,
   observe only after `step`; step at least `meta.timing.max_depth` cycles
   — or 1 for purely sequential circuits — to let values propagate).
   Fill the `expect` values either by hand from §7 (preferred for ABI
   cases; show your derivation in `description`) or with
   `conformance.runner.gen.fill_trace_ops`, which replays the skeleton on
   the reference oracle. Review the values for plausibility either way.
4. Add the case name to `MANIFEST.json` → `cases` (sorted). If it covers a
   new feature, add the feature key + description to `required_features`.
5. Bump `suite_version` (minor) and append a changelog entry.
6. `uv run shdl-conformance run --filter <name>` and
   `uv run shdl-conformance verify-oracle --filter <name>` must pass; the
   full `uv run shdl-conformance run` must still pass (coverage map
   included).

Formatting note: the tools emit canonical JSON (2-space indent, keys in the
orders shown in §4–§6, trailing newline, UTF-8). Validation checks content,
not formatting — but keeping hand-written files canonical keeps future
`regen` diffs minimal.
