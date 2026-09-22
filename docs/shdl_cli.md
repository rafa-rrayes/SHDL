# The `shdl` CLI — projects, packages, build/test/run

`shdl` is the SHDL project manager and unified toolchain driver. It owns the
workflow the lower layers deliberately don't: a project manifest
(`shdl.toml`), a pinned dependency resolution (`shdl.lock`), a vendored
package tree (`shdl_modules/`), and one-command build/test/run over
`SHDL.Circuit`. Packages come from **Circuit Circus**
(<https://rafa-rrayes.github.io/CCircus/>), the hosted SHDL package index;
its wire format is specified in the CCircus repo's `INDEX_FORMAT.md`.

Installed with the toolchain: `pip install pyshdl` (Python 3.14 or newer; a C
compiler on `PATH` for `build`/`test`/`run`).

## Two minutes in

```bash
shdl new counter && cd counter    # a compiling skeleton: shdl.toml, shdl.lock, src/, tests/
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
version = "0.1.0"         # required — X.Y.Z by convention (only non-empty is checked)
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
| `shdl new NAME [--top N]` | scaffold `NAME/` (refuses non-empty dirs): `shdl.toml`, `shdl.lock`, `src/NAME.shdl` (a `top component` N, default `Main`), `tests/NAME.tests.json`, `.gitignore`, `README.md` |
| `shdl init [NAME] [--top N]` | the same, into the current directory (NAME defaults to the directory name) |
| `shdl add PKG[@RANGE]… [--index URL]` | resolve, vendor, then record in shdl.toml + shdl.lock (default range: caret of the latest version); re-resolves the whole graph, so other locked versions may move |
| `shdl add --path DIR` | add a local package by path |
| `shdl remove PKG… [--index URL]` | remove **direct** deps (naming the requirer if transitive) |
| `shdl install [--frozen] [--force] [--index URL]` | make `shdl_modules/` mirror the lock: fetch missing, prune extra, verify versions; `--force` re-fetches everything |
| `shdl build [--top N] [-o LIB] [--emit-base] [--dev] [--cc CC]` | flatten + compile to `build/<project name>.<dylib\|so\|dll>`; `--emit-base` also writes `build/<project name>.base.shdl`; prints `built <path>` |
| `shdl test [COMPONENT…] [--dev] [--cc CC]` | run every `tests/*.tests.json` (optionally filtered to the named components); exit 1 on any failure |
| `shdl run [--top N] [--dev] [--cc CC]` | the REPL below; scriptable via stdin |
| `shdl search TERM [--index URL]` | search the index (name/summary/keywords) |
| `shdl info PKG [--versions] [--index URL]` | one package's metadata + exports |
| `shdl verify-package DIR [--packages-root ROOT]` | the per-package half of CCircus admission: manifest schema, every export builds at defaults, vectors green; ROOT (holding dependency packages) defaults to `DIR/..`. The registry-wide rules (dependency ranges met by published versions, no cycles, unique names, immutability) are checked only by CCircus CI |
| `shdl publish DIR [--packages-root ROOT] [--index URL]` | verify + check not-already-published + print the PR playbook |

Shared flags: `--top NAME` defaults to `[project] top` (then the main
module's own `top` marker). If the named component is not defined in the main
module, `shdl` looks for it in the other project modules (under the main
module's directory and `src/`, skipping `shdl_modules/` and `build/`) and
flattens that module instead — which is also how `shdl test` cases can target
any project component; a name defined in two project modules is an error; `--dev` compiles the generated C with `-O0` (much faster C
compilation, slower simulation); `--cc CC` picks the C compiler (default:
`$CC`, then the first of `cc`/`clang`/`gcc` on `PATH`).

Exit codes: 0 success, 1 diagnosed failure, 2 usage error (argparse).
Errors go to stderr as `shdl: error: …`; Ctrl-C prints `shdl: interrupted`
and exits 1. On Windows every command first prints
`shdl: warning: Windows is untested for this release; paths and C toolchain discovery may misbehave`.

### The `shdl run` REPL

`shdl run` builds the top component and reads one command per line from
stdin (with a `shdl> ` prompt and a banner only when stdin is a terminal, so
it can be scripted with a pipe). A bad command or a failing call prints
`error: …` and the REPL keeps going; the exit status is 0.

| Command | Effect |
|---|---|
| `poke SIGNAL VALUE` | drive an input; VALUE is parsed with Python `int(v, 0)`, so `0x…`/`0b…`/`0o…` work |
| `peek SIGNAL` | print a port's value (an output peek after a poke runs one lazy cycle — `pyshdl.md`) |
| `step [N]` | advance N unit-delay cycles (default 1) |
| `settle` | `Circuit.settle()`: advance exactly `timing.max_depth` cycles and print `settled after N cycle(s)`; on a circuit with feedback it prints `error: settle() is refused: …` instead |
| `reset` | back to the power-on state |
| `info` | print `inputs:` and `outputs:` port lists |
| `help` | list the commands |
| `quit` / `exit` / Ctrl-D | leave |

```text
$ printf 'info\npoke A 1\npeek Y\nsettle\n' | shdl run
inputs:  A
outputs: Y
0
settled after 1 cycle(s)
```

(The built-in `help` text describes `settle` as "step until stable"; it
actually runs exactly `max_depth` cycles, as above.)

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
`build`, `test` and `run` take no `--index`: they check the lock against
`SHDL_INDEX_URL` / `[registry] url` / the default, so a lock written with
`--index URL` counts as stale for them. To use another index for a whole
project, set `[registry] url` (or `SHDL_INDEX_URL`) instead.

## How resolution works

Flat, cargo-style-lite: for every constrained package, the highest version
satisfying **all** collected ranges wins; constraints come from shdl.toml,
path-dep manifests, and every chosen package's own dependencies (iterated to
a fixpoint). There is no backtracking: resolution stops at the first package
whose collected ranges no version satisfies, with an error listing those
ranges, their requirers, and the available versions.

Because the SHDL module namespace is flat and program-global, resolution also
refuses, at lock time: two packages shipping the same module basename, a
project module shadowing a package's, and two packages exporting the same
component name. The installed pyshdl is checked against every package's
`shdl` range.

## Testing

`tests/*.tests.json` uses the CCircus vector format — either a **vector
table** (for each vector: reset → poke every input → `step` the case's
`steps` budget, default 64 → check every output) or an **op sequence**
(`reset`/`poke`/`step`/`expect`, `step` defaulting to 1 cycle) for
sequential circuits. A skeleton from `shdl new`:

```json
{
  "test_format": 1,
  "package": "demo",
  "cases": [
    {
      "component": "Main",
      "steps": 8,
      "vectors": [
        {"in": {"A": 0}, "out": {"Y": 1}},
        {"in": {"A": 1}, "out": {"Y": 0}}
      ]
    }
  ]
}
```

Output is one block per file, one line per case, then a total; any failing
case makes the exit status 1 (a case's build error is reported as a failure,
and at most six mismatches are listed per case):

```text
[demo.tests.json]
  ok    Main

1/1 cases green
```

```text
[demo.tests.json]
  FAIL  Main: in={'A': 1} Y=0 (want 1)

0/1 cases green
```

Naming a component with no cases is an error (`no test cases for
component(s): …`), as is a project with no `tests/*.tests.json`.
Every case's `component` must be reachable from `main` (defined there or in
an imported module). Vendored packages' own tests are *not* re-run — they
were verified at admission.

## Publishing to Circuit Circus

```bash
shdl verify-package path/to/mypkg     # the per-package checks CI runs
shdl publish path/to/mypkg            # + not-already-published + PR playbook
```

Publishing is a PR against `rafa-rrayes/CCircus`; the playbook is printed by
`shdl publish`. Published versions are immutable — every change needs a
version bump (patch = docs/tests, minor = new exports, major = changed or
removed ports; for `0.y.z` packages the minor position carries breaking
changes, matching the caret rule).
