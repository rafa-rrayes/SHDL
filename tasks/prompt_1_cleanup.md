# Task: Organize and clean up the SHDL toolchain repository

## Context

This repo (`/Users/Rafa/Code/Python/shdlc`) is a from-scratch rewrite of the SHDL hardware-description-language toolchain. It is in excellent functional shape — ~1640 tests green, a frozen conformance corpus (v1.1.0), dual simulation oracles, fuzzing, and a verified 16-bit CPU example — but it grew organically and has never been tidied. Your job is to make the repository **perfectly clean**: structure, packaging, naming, code style, docs placement, git hygiene. Behavior must not change.

Read these first (currently at repo root):
- `SHDL_Project.md` — project charter: architecture, ecosystem, build sequence, principles.
- `golden_tests.md` — the verification map tying every spec obligation to tests. This file is the project's conscience; treat its obligations as contracts.
- `shdl.md`, `base_shdl.md`, `shdlc_goals.md` — normative specs (language, IR, compiler).

Current state: three packages at root (`flattener/` = SHDL→Base SHDL, `shdlc/` = Base SHDL→C→shared lib, `conformance/` = corpus + runner), tests split across `tests/` (flattener tests, loose), `tests/compiler/`, `tests/cpu/`, plus `examples/`, `scripts/`, `tasks/`, `.github/workflows/`. There is a large amount of uncommitted and untracked work in the working tree.

## Hard constraints

1. **Zero behavior change.** Every existing test must pass, unmodified in substance, after every commit. Tests are pinned contracts (see `golden_tests.md`) — never weaken, skip, or rewrite a test to make a cleanup fit. Mechanical updates (import paths, file paths) are fine.
2. **Test count must not drop.** Capture `uv run pytest --collect-only -q | tail -1` before starting; the collected count at the end must be identical.
3. **The flattener and shdlc packages must remain decoupled.** Base SHDL (text + meta JSON) is the *only* contract between them — a core project principle ("One IR, many consumers"). Do not introduce imports between `flattener` and `shdlc`, even to deduplicate constants. Dedupe within a package is fine.
4. **Do not change spec content** — only fix file paths/links inside the .md files when files move. The specs and `golden_tests.md` are normative documents maintained by hand.
5. Use `uv` for everything (`uv run pytest`, `uv lock`, `uvx ruff …`).
6. Work on the current branch. No force-pushes, no rebases, no history rewriting.

## Step 0 — Baseline (do this before touching anything)

1. Run the full suite: `uv run pytest`. Confirm green. Record the collected test count.
2. Run the conformance runner (entry point `shdl-conformance`; check `conformance/runner/cli.py` for usage) and confirm it passes.
3. Commit ALL outstanding modified and untracked work as one or more logical baseline commits (e.g. "Baseline: commit outstanding test suite, conformance corpus, CI, CPU work"). Exclude things that should be gitignored (`.coverage`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `*.dylib`, `.claude/` — decide deliberately and document in the commit message). Nothing in the working tree should be silently lost; if a file looks like scratch, confirm it is regenerable before excluding it.

## Tasks

### 1. Remove scratch and fix .gitignore
- Delete from root: `fa.c`, `fullAdder.dylib`, `.coverage` (verify first that nothing references them — grep).
- Expand `.gitignore` (currently 54 bytes) to cover: `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `*.so`, `*.dylib`, `*.dll`, build/temp artifacts, `.venv/`, `.DS_Store`. Decide whether `.claude/` is committed or ignored (look at what's in it; settings worth sharing stay, local state is ignored).

### 2. Restructure to the target layout

```
repo/
├── README.md              ← NEW (see task 5)
├── docs/                  ← specs move here
│   ├── SHDL_Project.md
│   ├── shdl.md
│   ├── base_shdl.md
│   ├── shdlc_goals.md
│   └── golden_tests.md
├── flattener/             ← unchanged location
├── shdlc/                 ← unchanged location
├── conformance/           ← unchanged location
├── tests/
│   ├── flattener/         ← ALL loose tests/test_*.py move here
│   ├── compiler/          ← unchanged
│   └── cpu/               ← unchanged
├── examples/              ← unchanged (incl. CPU/)
├── scripts/
├── tasks/
└── pyproject.toml
```

- Use `git mv` for all moves.
- **Update every reference to moved files.** Known/likely reference sites — grep exhaustively for each moved filename (`shdl.md`, `base_shdl.md`, `shdlc_goals.md`, `golden_tests.md`, `SHDL_Project.md`) across `*.py`, `*.md`, `*.yml`, `*.toml`:
  - `tests/.../test_spec_examples.py` almost certainly reads `shdl.md` from the repo root by path.
  - `.github/workflows/ci.yml` and `nightly.yml` may reference paths.
  - `scripts/build_conformance_corpus.py`, `conformance/conformance.md`, cross-references inside the specs themselves, `tasks/*.md`.
- Moving the loose flattener tests: check how they import helpers (e.g. `tests/fuzz_source_gen.py` is a generator helper imported by `tests/test_fuzz_source.py` — it moves too and imports must be fixed). Check for `conftest.py` files and pytest's rootdir/import mode; add `tests/flattener/__init__.py` only if the existing convention uses package-style tests (match what `tests/compiler/` does today).
- `tests/compiler/harness.py` re-exports `shdlc/harness.py` — leave that relationship intact.

### 3. Fix packaging (`pyproject.toml`)
- Rename the project/distribution from `shdlc` to **`pyshdl`** — this distribution will ship the entire toolchain; the user-facing `pyshdl` package itself lands in the next work item (do NOT create it now).
- Fix the description: it currently says the project is just the flattener. Make it describe the whole toolchain (flattener + shdlc compiler + conformance suite; PySHDL driver coming).
- Keep `requires-python = ">=3.14"`, the three CLI entry points (`shdl-flatten`, `shdlc`, `shdl-conformance`), hatchling, and the three wheel packages.
- Add a `version` source of truth note or leave 0.1.0 — but make sure nothing else claims a different version.
- Add `[tool.ruff]` configuration: a sensible modern ruleset (at minimum `E, F, W, I, UP, B`; line length matching the existing code's convention — inspect before choosing). Add ruff to the dev dependency group.
- Update `[tool.pytest.ini_options]` if needed after the test moves.
- Run `uv lock` so `uv.lock` reflects the rename.

### 4. Code cleanliness (behavior-preserving)
- Run `uvx ruff check --fix` and `uvx ruff format` across the repo with the new config; resolve remaining lint findings by hand. The full suite must stay green after.
- **CLI consistency:** `flattener/cli.py` uses argparse; `shdlc/cli.py` hand-rolls argument parsing. Unify on argparse **only if** every pinned CLI test (`tests/.../test_cli.py` on both sides, diagnostics-format tests) passes unmodified — exact CLI output/exit codes are contractual (DIA-3/DIA-9 in golden_tests.md). If unification would change pinned output, leave the code as is and record why in your final report.
- Deduplicate obvious repetition **within** each package (e.g. gate-type tables appearing in more than one module of the same package). Respect constraint #3: never across the flattener/shdlc boundary.
- `shdlc/harness.py` (the `Sim` class): leave its semantics exactly as is — the next work item (PySHDL) builds on it. Docstring/style polish only.
- Audit for dead code, unused imports, stray TODO/debug prints. Remove only what is provably dead.

### 5. Write `README.md` at the repo root
A proper front page: what SHDL is (educational gate-level HDL, one-level-per-cycle simulation), the two-language architecture (SHDL → flattener → Base SHDL → shdlc → C → shared library), install/dev setup with `uv`, quickstart (flatten an example, compile it, run the conformance suite), repo layout map, how to run tests, pointers into `docs/`. Mention PySHDL as the upcoming user-facing API. Keep it accurate and concise — no marketing fluff.

### 6. Housekeeping
- `tasks/todo.md`: per the project workflow, write your plan there first with checkable items, keep it updated, and add a review section at the end.
- Make sure `.github/workflows/*.yml` still reference correct paths post-move. Note: the Linux CI matrix is authored but has never been proven on a real runner (known residual CCT-6) — updating paths is in scope; making Linux CI pass is NOT.
- Check `examples/README.md` still matches the examples present.

## Verification gate (all must hold before you call it done)

1. `uv run pytest` — fully green, collected count identical to the Step-0 baseline.
2. Conformance runner — green.
3. `uvx ruff check` and `uvx ruff format --check` — clean.
4. `git status` — completely clean working tree.
5. Grep proof: no stale references to old paths of moved files (`grep -rn "golden_tests.md" --include="*.py" --include="*.yml" --include="*.md" .` etc. shows only correct new paths).
6. History: a sequence of small, logical commits (baseline → scratch removal → moves → packaging → style → README), each with a clear message, each individually green if practical.

## Out of scope
- Building PySHDL (separate, follow-up task — but leave the structure ready for a `pyshdl/` package at root).
- Any behavior, performance, or spec-content changes.
- Proving Linux CI / publishing to PyPI.
- The SHDB debugger, stdlib, backends, or anything else from the charter's later layers.

## Final report
Summarize: what moved where, what was deleted and why, packaging changes, refactors performed vs. skipped (with reasons — especially the CLI unification decision), and the before/after verification evidence (test counts, conformance result).
