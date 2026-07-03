"""``shdl new`` / ``shdl init``: a compiling, testing project skeleton."""

from __future__ import annotations

import re
from pathlib import Path

from .errors import CliError
from .index_client import DEFAULT_INDEX
from .lockfile import Lock, manifest_fingerprint, write_lock
from .project import PROJECT_FILE

_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")

_TOML = """\
[project]
name = "{name}"
version = "0.1.0"
main = "src/{name}.shdl"
top = "{top}"
shdl = ">=1.0.0"

[dependencies]
"""

_MODULE = '''\
"""{name} — an SHDL project."""

top component {top}(A) -> (Y) {{
    inv: NOT;
    connect {{
        A -> inv.A;
        inv.O -> Y;
    }}
}}
'''

_TESTS = """\
{{
  "test_format": 1,
  "package": "{name}",
  "cases": [
    {{
      "component": "{top}",
      "steps": 8,
      "vectors": [
        {{"in": {{"A": 0}}, "out": {{"Y": 1}}}},
        {{"in": {{"A": 1}}, "out": {{"Y": 0}}}}
      ]
    }}
  ]
}}
"""

_GITIGNORE = """\
shdl_modules/
build/
"""

_README = """\
# {name}

An [SHDL](https://github.com/rafa-rrayes/SHDL) project.

```bash
shdl add arith        # add a Circuit Circus package
shdl build            # flatten + compile to build/
shdl test             # run tests/*.tests.json
shdl run              # poke/peek REPL over the compiled circuit
```

Or drive it from Python:

```python
from SHDL import Circuit

with Circuit("src/{name}.shdl", top="{top}",
             include_dirs=["shdl_modules/<pkg>"]) as c:
    c.poke("A", 1); c.step(8)
    print(c.peek("Y"))
```
"""


def create_project(
    directory: Path, name: str, top: str = "Main", *, into_existing: bool = False
) -> list[str]:
    """Scaffold a project in ``directory`` (created if missing). Returns the
    files written, project-relative. ``into_existing`` (``shdl init``) allows
    a non-empty directory but still refuses to overwrite anything."""
    if not _NAME.match(name):
        raise CliError(f"project name {name!r} must match [a-z][a-z0-9_]*")
    if not re.match(r"[A-Za-z_][A-Za-z0-9_]*\Z", top):
        raise CliError(f"top component name {top!r} must be an identifier")
    if (directory / PROJECT_FILE).exists():
        raise CliError(f"{directory / PROJECT_FILE} already exists")
    if not into_existing and directory.exists() and any(directory.iterdir()):
        raise CliError(f"{directory} exists and is not empty (use 'shdl init' inside it)")

    files = {
        PROJECT_FILE: _TOML.format(name=name, top=top),
        f"src/{name}.shdl": _MODULE.format(name=name, top=top),
        f"tests/{name}.tests.json": _TESTS.format(name=name, top=top),
        ".gitignore": _GITIGNORE,
        "README.md": _README.format(name=name, top=top),
    }
    clobbered = [rel for rel in (*files, "shdl.lock") if (directory / rel).exists()]
    if clobbered:
        raise CliError(f"refusing to overwrite: {', '.join(clobbered)}")
    for rel, text in files.items():
        dest = directory / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")

    write_lock(
        directory / "shdl.lock",
        Lock(
            manifest_fingerprint=manifest_fingerprint({}, DEFAULT_INDEX),
            registry=DEFAULT_INDEX,
            packages={},
        ),
    )
    return [*files, "shdl.lock"]
