"""Check every code block on the documentation site against the real toolchain.

    uv run website/scripts/check_snippets.py [PAGE.md ...] [-v]

With no arguments, every page under website/docs/ is checked. Fences opt in
or out through words in their info string (after the language):

```shdl                      a module: written to a scratch dir and flattened
```shdl title="alu.shdl"     ... saved under that name (later blocks may `use` it)
```shdl lib                  a module with no single top: parsed and validated only
```shdl error=E0401          must fail to flatten with exactly this code
```shdl fragment             not checked (an excerpt, not a whole module)

```python                    run; if the next fence is ```text title="Output",
                             stdout must match it exactly
```python continue           runs in the same interpreter as the previous block
```python fragment           not run

```console check             each `$ command` runs in bash (in the page's
                             scratch dir, toolchain on PATH); the lines up to
                             the next `$` must match stdout+stderr. A line that
                             is exactly `...` matches any run of lines.
```console check continue    same scratch dir and shell state as the last one

Every page gets its own scratch directory holding the page's .shdl blocks and
an `examples` symlink to the repository's examples/, so snippets can say
`Circuit("examples/adder8.shdl")`. Imports resolve against the scratch
directory first, then examples/.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "website" / "docs"
EXAMPLES = REPO / "examples"

sys.path.insert(0, str(REPO))
from flattener.diagnostics import SHDLError  # noqa: E402
from flattener.loader import load_program  # noqa: E402
from flattener.pipeline import flatten_program  # noqa: E402
from flattener.validate import validate_program  # noqa: E402

FENCE = re.compile(r"^(?P<indent>\s*)(?P<fence>`{3,}|~{3,})(?P<lang>[\w+-]*)\s*(?P<meta>.*)$")
TITLE = re.compile(r'title="([^"]*)"')
ERROR = re.compile(r"\berror=(E0[0-9A]\d\d)\b")


@dataclass
class Block:
    lang: str
    meta: str
    body: str
    line: int
    output: str | None = None  # the following ```text title="Output" fence

    def has(self, word: str) -> bool:
        return word in self.meta.split()

    @property
    def title(self) -> str | None:
        m = TITLE.search(self.meta)
        return m.group(1) if m else None


@dataclass
class Report:
    checked: int = 0
    failures: list[str] = field(default_factory=list)

    def fail(self, page: Path, block: Block, why: str) -> None:
        self.failures.append(f"{display(page)}:{block.line}: {block.lang}: {why}")


def display(page: Path) -> str:
    return str(page.relative_to(REPO)) if page.is_relative_to(REPO) else str(page)


def parse_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        fence, start = m.group("fence"), i
        body: list[str] = []
        i += 1
        while i < len(lines) and not (
            lines[i].strip().startswith(fence[0] * len(fence))
            and set(lines[i].strip()) == {fence[0]}
        ):
            body.append(lines[i])
            i += 1
        indent = len(m.group("indent"))
        body = [ln[indent:] if ln[:indent].isspace() else ln for ln in body]
        blocks.append(Block(m.group("lang"), m.group("meta"), "\n".join(body) + "\n", start + 1))
        i += 1
    # Attach expected-output fences to the block they follow.
    for prev, nxt in zip(blocks, blocks[1:]):
        if nxt.lang == "text" and nxt.title == "Output":
            prev.output = nxt.body
    return blocks


def normalize(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.strip("\n").split("\n")]


def matches(expected: list[str], actual: list[str]) -> bool:
    """Line match where an `...` line in *expected* swallows any run of lines."""
    if not expected:
        return not actual
    if expected[0] == "...":
        return any(matches(expected[1:], actual[k:]) for k in range(len(actual) + 1))
    return bool(actual) and expected[0] == actual[0] and matches(expected[1:], actual[1:])


def diff(expected: str, actual: str) -> str:
    return "\n      expected:\n" + _indent(expected) + "\n      actual:\n" + _indent(actual)


def _indent(text: str) -> str:
    return "\n".join("        | " + ln for ln in text.strip("\n").split("\n"))


def check_shdl(page: Path, block: Block, scratch: Path, index: int, report: Report) -> None:
    name = block.title or f"snippet{index}.shdl"
    path = scratch / Path(name).name
    path.write_text(block.body, encoding="utf-8")
    expect = ERROR.search(block.meta)
    includes = [str(scratch), str(EXAMPLES)]
    try:
        if block.has("lib"):
            validate_program(load_program(str(path), includes))
        else:
            flatten_program(str(path), include_dirs=includes, timestamp="2026-01-01T00:00:00Z")
    except SHDLError as e:
        got = e.diagnostic.code.value
        if not expect:
            report.fail(page, block, f"does not flatten: {e.diagnostic}")
        elif got != expect.group(1):
            report.fail(page, block, f"expected {expect.group(1)}, got {e.diagnostic}")
        return
    except Exception as e:  # a crash is always a failure
        report.fail(page, block, f"flattener crashed: {e!r}")
        return
    if expect:
        report.fail(page, block, f"expected {expect.group(1)}, but it flattened cleanly")


RUNNER = """\
import sys
ns = {"__name__": "__main__"}
for i, path in enumerate(sys.argv[1:]):
    print(f"\\n@@SNIPPET {i}@@", flush=True)
    exec(compile(open(path, encoding="utf-8").read(), path, "exec"), ns)
    sys.stdout.flush()
"""


def run_python_chain(page: Path, chain: list[Block], scratch: Path, report: Report) -> None:
    paths = []
    for block in chain:
        path = scratch / f"snippet_line{block.line}.py"
        path.write_text(block.body, encoding="utf-8")
        paths.append(str(path))
    runner = scratch / "_runner.py"
    runner.write_text(RUNNER, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(runner), *paths],
        cwd=scratch,
        capture_output=True,
        text=True,
        timeout=600,
    )
    parts = re.split(r"\n?@@SNIPPET \d+@@\n", proc.stdout)[1:]
    for k, block in enumerate(chain):
        if k >= len(parts):
            report.fail(page, block, "never ran: an earlier block in the chain failed")
            continue
        if k == len(parts) - 1 and proc.returncode != 0:
            report.fail(page, block, f"raised:\n{_indent(proc.stderr)}")
            continue
        if block.output is not None and normalize(parts[k]) != normalize(block.output):
            report.fail(page, block, "output differs" + diff(block.output, parts[k]))


def check_console(page: Path, block: Block, shell_state: Path, scratch: Path, report: Report) -> None:
    steps: list[tuple[str, list[str]]] = []
    for ln in block.body.rstrip("\n").split("\n"):
        if ln.startswith("$ "):
            steps.append((ln[2:], []))
        elif steps:
            steps[-1][1].append(ln)
    env = dict(os.environ)
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env['PATH']}"
    env["NO_COLOR"] = "1"
    env["COLUMNS"] = "80"
    for cmd, expected in steps:
        # Each command runs in a fresh bash that restores the working
        # directory saved by the previous one, so `cd` carries across steps.
        script = (
            f"cd {shlex.quote(shell_state.read_text().strip())}\n"
            f"{cmd}\nstatus=$?\npwd > {shlex.quote(str(shell_state))}\nexit $status\n"
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        actual = (proc.stdout + proc.stderr).replace(str(scratch), "<scratch>")
        if not matches(normalize("\n".join(expected)), normalize(actual)):
            report.fail(page, block, f"`{cmd}` output differs" + diff("\n".join(expected), actual))
            return


def check_page(page: Path, report: Report, verbose: bool) -> None:
    blocks = parse_blocks(page.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="shdl-docs-") as tmp:
        scratch = Path(tmp).resolve()
        (scratch / "examples").symlink_to(EXAMPLES)
        shell_state = scratch / ".shell-cwd"
        chain: list[Block] = []
        for n, block in enumerate(blocks):
            if block.has("fragment"):
                continue
            if block.lang == "shdl":
                report.checked += 1
                check_shdl(page, block, scratch, n, report)
            elif block.lang == "python":
                report.checked += 1
                if block.has("continue"):
                    chain.append(block)
                    continue
                if chain:
                    run_python_chain(page, chain, scratch, report)
                chain = [block]
            elif block.lang == "console" and block.has("check"):
                report.checked += 1
                if not block.has("continue"):
                    shell_state.write_text(str(scratch))
                check_console(page, block, shell_state, scratch, report)
        if chain:
            run_python_chain(page, chain, scratch, report)
    if verbose:
        print(f"checked {display(page)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pages", nargs="*", type=Path)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    pages = [p.resolve() for p in args.pages] or sorted(
        p for p in DOCS.rglob("*") if p.suffix in (".md", ".mdx")
    )
    report = Report()
    for page in pages:
        check_page(page, report, args.verbose)
    for failure in report.failures:
        print(failure)
    print(f"{report.checked} snippets checked, {len(report.failures)} failed")
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
