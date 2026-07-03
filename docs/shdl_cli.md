# The `shdl` CLI — projects, packages, build/test/run

`shdl` is the SHDL project manager and unified toolchain driver. It owns the
workflow the lower layers deliberately don't: a project manifest
(`shdl.toml`), a pinned dependency resolution (`shdl.lock`), a vendored
package tree (`shdl_modules/`), and one-command build/test/run over
`SHDL.Circuit`. Packages come from **Circuit Circus**
(<https://rafa-rrayes.github.io/CCircus/>), the hosted SHDL package index;
its wire format is specified in the CCircus repo's `INDEX_FORMAT.md`.

Installed with the toolchain: `pip install pyshdl`.

## Two minutes in

```bash
shdl new counter && cd counter    # a compiling skeleton: shdl.toml, src/, tests/
shdl add arith                    # vendors arith + its deps into shdl_modules/
shdl build                        # flatten + compile -> build/counter.<dylib|so>
shdl test                         # run tests/*.tests.json
shdl run                          # poke/peek/step REPL over the live circuit
```

```shdl
use arith::{RippleAdder};         # anything you vendored is importable
```

## The project layout

```
counter/
├── shdl.toml            # the manifest (below)
├── shdl.lock            # pinned resolution — commit it
├── src/counter.shdl     # your modules ([project] main is the entry point)
├── tests/*.tests.json   # test vectors (CCircus MANIFEST_FORMAT.md §3 format)
├── shdl_modules/        # vendored packages — gitignored, rebuilt by install
└── build/               # artifacts — gitignored
```

### `shdl.toml`

```toml
[project]
name = "counter"          # required — [a-z][a-z0-9_]*
version = "0.1.0"         # required — X.Y.Z
main = "src/counter.shdl" # required — the entry module
top = "Main"              # optional — default top component for build/run
shdl = ">=1.0.0"          # optional — toolchain compatibility range

[dependencies]
arith = "^0.1.0"                      # registry package
mylib = { path = "../mylib" }         # local dir: on the include path, never vendored

[registry]
url = "https://rafa-rrayes.github.io/CCircus"   # optional override
```

Version ranges use cargo semantics: exact (`0.1.0`), caret (`^0.1.0` =
`>=0.1.0, <0.2.0`; for `0.x` the minor is the breaking position), the four
comparators, and comma as AND. No tilde/wildcards/prereleases.

### `shdl.lock`

JSON, written by `add`/`remove`/`install`, meant to be committed. It pins
every package's version and archive sha256 and fingerprints the inputs that
produced it (the direct dependencies + the effective registry URL).
**`build`/`test`/`run` never touch the network**: they check the lock is
fresh and the vendored tree matches it, and error with "run 'shdl install'"
otherwise. `shdl install --frozen` is the CI form — it fails instead of
re-resolving.

## Commands

| Command | What it does |
|---|---|
| `shdl new NAME [--top N]` | scaffold `NAME/` (refuses non-empty dirs) |
| `shdl init [NAME] [--top N]` | scaffold into the current directory |
| `shdl add PKG[@RANGE]…` | resolve, vendor, then record in shdl.toml + shdl.lock (default range: caret of the latest version) |
| `shdl add --path DIR` | add a local package by path |
| `shdl remove PKG…` | remove **direct** deps (naming the requirer if transitive) |
| `shdl install [--frozen] [--force]` | make `shdl_modules/` mirror the lock: fetch missing, prune extra, verify versions |
| `shdl build [--top N] [-o LIB] [--dev] [--cc CC] [--emit-base]` | flatten + compile to `build/`; `--dev` = `-O0` fast compile |
| `shdl test [COMPONENT…]` | run every `tests/*.tests.json` (optionally filtered); exit 1 on any failure |
| `shdl run [--top N]` | REPL: `poke/peek/step/settle/reset/info/quit`; scriptable via stdin |
| `shdl search TERM` | search the index (name/summary/keywords) |
| `shdl info PKG [--versions]` | one package's metadata + exports |
| `shdl verify-package DIR [--packages-root ROOT]` | CCircus admission semantics: manifest schema, every export builds at defaults, vectors green |
| `shdl publish DIR` | verify + check not-already-published + print the PR playbook |

Exit codes: 0 success, 1 diagnosed failure, 2 usage error. Errors go to
stderr as `shdl: error: …`.

## Choosing the index

Precedence: `--index URL` (one command) → `SHDL_INDEX_URL` (session) →
`[registry] url` in shdl.toml (project) → the default
(`https://rafa-rrayes.github.io/CCircus`). `file://` URLs work natively —
a local CCircus checkout is a fully functional index:

```bash
export SHDL_INDEX_URL=file:///path/to/CCircus
```

The lock fingerprint includes the effective registry URL, so switching
indexes makes the lock stale (deliberately) — re-run `shdl install`.

## How resolution works

Flat, cargo-style-lite: for every constrained package, the highest version
satisfying **all** collected ranges wins; constraints come from shdl.toml,
path-dep manifests, and every chosen package's own dependencies (iterated to
a fixpoint). Conflicts are hard errors listing every range and its requirer.

Because the SHDL module namespace is flat and program-global, resolution also
refuses, at lock time: two packages shipping the same module basename, a
project module shadowing a package's, and two packages exporting the same
component name. The installed pyshdl is checked against every package's
`shdl` range.

## Testing

`tests/*.tests.json` uses the CCircus vector format — either a **vector
table** (reset → poke inputs → `step` a settle budget → check outputs) or an
**op sequence** (`reset`/`poke`/`step`/`expect`) for sequential circuits.
Every case's `component` must be reachable from `main` (defined there or in
an imported module). Vendored packages' own tests are *not* re-run — they
were verified at admission.

## Publishing to Circuit Circus

```bash
shdl verify-package path/to/mypkg     # what CI will check
shdl publish path/to/mypkg            # + not-already-published + PR playbook
```

Publishing is a PR against `rafa-rrayes/CCircus`; the playbook is printed by
`shdl publish`. Published versions are immutable — every change needs a
version bump (patch = docs/tests, minor = new exports, major = changed or
removed ports).
