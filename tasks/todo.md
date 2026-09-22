# SHDL docs overhaul — plan

Branch `docs-overhaul` (worktree `shdlc-docs`, from master 2452654 = PySHDL 1.1.0).
Scope (user-confirmed): rebuild the public site in `website/` + fix every
in-repo spec. Describe master / v1.1.0 only. No commit / push / deploy without asking.

## Audit findings (evidence-backed)

Accurate today, keep (light verification only):
- `conformance/conformance.md` — matches runner + MANIFEST (suite 1.1.0, 38 cases).
- `docs/shdl_cli.md` — accurate; missing per-command flags, REPL details, test output.
- `docs/pyshdl.md` — accurate prose; two broken anchors (§9→§11 lifecycle, §7→§8 bare libs).

Wrong / stale:
- `README.md` — "~1640 tests" (actual: 1905 collected); "next up: debug build + SHDB"; docs list lacks pyshdl.md / shdl_cli.md; no site link.
- `docs/SHDL_Project.md` — SHDB in §2 diagram; §3.2 debug ABI + §3.3 State Region described as if real (not implemented); §7 status stale; §8 cites nonexistent `SHDL_Compiler_Goals.md` (→ `shdlc_goals.md`).
- `docs/shdl.md` — SHDB in §1.2; §9.1 "first bound wins" is wrong (E0701 "module 'x' resolves to two different files"); §11.4 State Region/debugger; §2.4 omits parens in `when`; limits missing (nesting 200, range 1,000,000); no error-code catalog. (+ whatever the language-research agent finds.)
- `docs/base_shdl.md` — SHDB/.shdb/State Region/"SHDLC (debug)" presented as real; "6 sequential phases"; §4.7 timing, §4.9 stats (22 vs real 23), §4.10 doc (`author` never emitted) examples don't match real flattener output (use conformance `add2` golden instead).
  - CONSTRAINT: `tests/compiler/test_model.py` regex-extracts the §3.7 Add2 block (bare ``` fence, gate order x1,x2,a1,a2,o1) — keep it verbatim.
- `docs/shdlc_goals.md` — debug ABI (§3.3/3.4), State Region (§4), debug mode (§6.2), `.shdb`, `-O3` presented as requirements with no status; real default is `-O2` (`--dev` = `-O0`). Add status banners, keep as goals doc.
- `docs/golden_tests.md` — internal plan; light pass for factual staleness only.

Code discrepancies (flag to user, do NOT fix unasked):
- `__version__ = "1.0.0"` in `SHDL/`, `shdlc/`, `flattener/__init__.py` vs package 1.1.0.
- `shdl run` REPL help: "settle — step until stable, print how many cycles" — actually runs exactly `max_depth` and errors on feedback.

## Plan

### 1. Site scaffold (`website/`)
- [x] Docusaurus 3.10.x (classic preset, TS), `baseUrl: /SHDL/`, `onBrokenLinks: 'throw'`, `markdown.format: 'detect'`.
- [x] Two docs instances: guide at `/docs` (`website/docs`), specs at `/specs` (path `../docs`, the in-repo specs rendered as-is — single source).
- [x] Custom `shdl` Prism grammar (keywords, primitives, `>i[N]{}`, `{expr}`, comments, `"""doc"""`).
- [x] Reuse old logo + favicon; simple custom landing page (no template boilerplate).
- [x] `@docusaurus/plugin-client-redirects`: old `/docs/debugger/*` → `/docs/roadmap`.
- [x] `.github/workflows/docs.yml`: build on PR, deploy Pages on master (paths: website/**, docs/**).

### 2. Guide pages (old slugs preserved where they still make sense)
- [x] `intro`
- [x] getting-started/: `installation`, `first-circuit`, `using-pyshdl`, `projects` (new)
- [x] concepts/: `simulation-model` (unit delay, cycle 0, VCC@0, lazy peek, settle vs step_settle, feedback, init)
- [x] language-reference/: `overview`, `lexical-elements`, `components`, `signals`, `connections`, `generators`, `parameters` (new), `constants`, `sequential-logic` (new: feedback + `init`), `imports`, `standard-gates`, `errors` (full code catalog + limits)
- [x] tools/: `shdl-cli`, `project-manifest` (shdl.toml / lock / semver / resolution), `testing` (tests.json), `packages` (CCircus + publish), `shdl-flatten`, `shdlc`, `python-api` (full reference), `c-abi`, `conformance`
- [x] examples/: `half-adder`, `full-adder`, `8-bit-adder`, `multiplexer`, `comparator`, `register`, `decoder`, + `latches`, `alu`, `ring-oscillator`, `sr16-cpu`, `game-of-life`
- [x] architecture/: `overview`, `flattening-pipeline`, `base-shdl`, `compiler-internals`, `pyshdl-internals`
- [x] `roadmap` (SHDB debugger + debug build + State Region = planned, not in 1.1.0)

### 3. Spec fixes (in place, minimal diffs)
- [x] README.md · SHDL_Project.md · shdl.md · base_shdl.md · shdlc_goals.md · pyshdl.md
- [x] base_shdl.md second pass: §3.3 NOT `^ 1`; §4.4/§4.5 rebuilt from add2 golden (instance site, lines ⊇ inverse); §4.6 prefixed keys; §4.7 power pins depth 1 + feedback-start paths; §4.11 real srLatch keys; §5 driver row; §6 comments; §8 State Region planned
- [x] shdl.md §11.4 E0A02 caveat (verified probe) · examples/CPU/ISA.md SR16 has no `A` param (RAM256) · GameOfLife README Python 3.14 note
- [x] shdl_cli.md package-manager pass: add/remove re-resolve · no backtracking · verify-package = per-package half of admission · `--index` lock stale for build · 0.y.z bumps; SHDL_Project.md §4.12 scaffold has no `shdl_modules/`
- [x] shdl_cli.md (all flags, REPL table + transcript, test format/output, --top lookup, Windows warning) · golden_tests.md (test count 1905) · examples/README.md (full ABI, Python snippet, CPU/GameOfLife)

### 4. Verification
- [x] Every ```shdl module block flattened (`uv run shdl-flatten`, examples/ on -I); fragments explicitly marked.
- [x] Every ```python block executed via `uv run`; printed values diffed against documented values.
- [x] CLI transcripts (shdl new/add/build/test/run, shdl-flatten, shdlc, shdl-conformance) captured from real runs (file:// CCircus index for add/install).
- [x] `npm run build` clean (broken links = error); spot-check rendered pages for swallowed `<...>`.
- [x] `uv run pytest -q` + `uvx ruff check` still green (test_model reads base_shdl.md).
- [x] Review section below.

## Review

Verified 2026-09-22 on the worktree (nothing committed):
- `uv run website/scripts/check_snippets.py` → 555 snippets checked, 0 failed
  (174 shdl modules flattened, 187 python blocks run with 188 exact-output
  comparisons, 194 console transcripts re-run). 22 blocks are marked
  `fragment` (excerpts), plus the live registry listing in tools/packages.mdx,
  dated rather than re-run because every publish changes it.
- `npm run build` → success with onBrokenLinks / onBrokenAnchors /
  onBrokenMarkdownLinks all `throw`; built HTML has only standard tags (no
  swallowed `<placeholder>`s); old /docs/debugger/* URLs redirect.
- `uv run pytest -q` → 1897 passed, 8 skipped (test_model still parses the
  base_shdl.md §3.7 block).
- `uvx ruff check` → 7 errors, all in examples/GameOfLife/{gen_life,gol_render,validate}.py,
  untouched vs HEAD (pre-existing).

Notes:
- Docusaurus `future.v4` disables MDX1 compat: custom heading IDs must be
  `{/* #id */}`, not `{#id}` (classic form fails the MDX compile).
- The shdl-cli.mdx `add`/`search`/`info` transcripts run against the live
  CCircus index on purpose (they catch drift); they will fail the docs job
  when the index changes, including the v2 cutover.
