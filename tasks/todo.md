# Repo cleanup — SHDL toolchain (Phase 1 tidy)

Goal: make the repo perfectly clean (structure, packaging, style, docs, git
hygiene) with **zero behavior change**. Baseline: 1644 tests collected
(1636 passed, 8 skipped); conformance 78 checks / 0 failures.

## Step 0 — Baseline (DONE)
- [x] Full suite green; recorded count = **1644**.
- [x] Conformance runner green (78 checks, 0 failures).
- [x] Committed all outstanding work in 6 logical baseline commits
      (specs/docs, source, conformance, CI, CPU, tests). Scratch excluded.

## Key findings (decisions baked in)
- **CLI unification not needed**: `shdlc/cli.py` already uses argparse in the
  working tree (the task's "hand-rolled" premise is stale). No CLI change.
- **`tests/flattener/` stays a non-package** (no `__init__.py`): the loose
  tests are non-package (`from helpers import ...`) and a package literally
  named `flattener` would shadow the `flattener` source package under pytest
  prepend import mode. `compiler`/`cpu` can be packages — those names don't
  collide. Only edit needed: `helpers.py` FIXTURES path (`.parent.parent`).
- **`tests/fixtures/` does not move** — shared by `helpers.py` and
  `tests/compiler/harness.py` (`REPO/"tests"/"fixtures"`).
- **Only one real path reference** to a moved spec: `tests/compiler/test_model.py:20`
  (`/ "base_shdl.md"` → `/ "docs" / "base_shdl.md"`). Prose `(shdl.md §N)`
  citations are not paths and stay.
- **Markdown links** `[base_shdl.md](base_shdl.md)` in `shdl.md` stay valid —
  both files move into `docs/` together (same dir).
- **ruff**: line-length 100 (matches code; flattener max 99, shdlc 97);
  select E,F,W,I,UP,B; ignore E501 (formatter owns wrapping; long Base-SHDL
  string literals are intentional).

## Task 1 — Scratch removal + .gitignore
- [ ] `rm fa.c fullAdder.dylib .coverage` (grep-verified: only ref is
      examples/README.md describing `fullAdder.dylib` as command output).
- [ ] Expand `.gitignore`: `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`,
      `.coverage`, `*.so/*.dylib/*.dll`, `.venv/`, `.DS_Store`, build dirs,
      `.claude/*` except `.claude/workflows/`.

## Task 2 — Restructure
- [ ] `git mv` the 5 specs into `docs/`.
- [ ] Fix `tests/compiler/test_model.py` SPEC path → `docs/base_shdl.md`.
- [ ] `git mv` all loose `tests/test_*.py` + `helpers.py` + `fuzz_source_gen.py`
      into `tests/flattener/` (NO `__init__.py`).
- [ ] Fix `helpers.py` FIXTURES → `Path(__file__).parent.parent / "fixtures"`.
- [ ] Run full suite → green.

## Task 3 — Packaging
- [ ] Rename distribution `shdlc` → `pyshdl`; fix description (whole toolchain);
      keep py>=3.14, 3 entry points, hatchling, 3 wheel packages, version 0.1.0.
- [ ] Add `[tool.ruff]` (line-length 100; E,F,W,I,UP,B; ignore E501).
- [ ] Add `ruff` to dev group; `uv lock`.

## Task 4 — Code cleanliness
- [ ] `uvx ruff format`; `uvx ruff check --fix`; resolve remainder by hand.
- [ ] Dedup within-package only (respect flattener/shdlc decoupling).
- [ ] Remove provably-dead code / unused imports / stray prints.
- [ ] Full suite → green.

## Task 5 — README.md
- [ ] Front page: what SHDL is, two-language architecture, uv install/dev,
      quickstart, layout map, tests, docs pointers, PySHDL note.

## Task 6 — Housekeeping
- [ ] Verify `.github/workflows/*.yml` paths post-move.
- [ ] Check `examples/README.md` matches examples present.
- [ ] Review section below.

## Verification gate
- [ ] pytest green, count == 1644.
- [ ] conformance green.
- [ ] `ruff check` + `ruff format --check` clean.
- [ ] `git status` clean.
- [ ] grep proof: no stale paths to moved files.

## Review
_(to be filled at the end)_
