"""shdl.toml: discovery, loading, validation, and safe textual edits.

The stdlib reads TOML (``tomllib``) but does not write it, so ``shdl add`` /
``shdl remove`` patch the ``[dependencies]`` table textually (cargo-style):
replace or insert one ``name = …`` line, leave every other byte untouched,
then re-parse the result and assert it means exactly what was intended —
aborting without writing if not.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import CliError

PROJECT_FILE = "shdl.toml"
LOCK_FILE = "shdl.lock"
MODULES_DIR = "shdl_modules"
BUILD_DIR = "build"

_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")


def validate_package_name(name: str, context: str) -> None:
    if not _NAME.match(name):
        raise CliError(f"{context}: package name {name!r} must match [a-z][a-z0-9_]*")


@dataclass(frozen=True)
class PathDep:
    """A local, never-vendored dependency: ``pkg = { path = "…" }``."""

    path: str  # as written in shdl.toml (resolved relative to the project root)


@dataclass
class Project:
    root: Path
    name: str
    version: str
    main: str
    top: str | None
    shdl: str | None
    dependencies: dict[str, str | PathDep]
    registry_url: str | None

    @property
    def file(self) -> Path:
        return self.root / PROJECT_FILE

    @property
    def main_path(self) -> Path:
        return self.root / self.main

    @property
    def lock_path(self) -> Path:
        return self.root / LOCK_FILE

    @property
    def modules_dir(self) -> Path:
        return self.root / MODULES_DIR

    @property
    def build_dir(self) -> Path:
        return self.root / BUILD_DIR

    def path_dep_dir(self, name: str) -> Path:
        dep = self.dependencies[name]
        assert isinstance(dep, PathDep)
        return (self.root / dep.path).resolve()


def find_project(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default cwd) to the directory holding shdl.toml."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / PROJECT_FILE).is_file():
            return candidate
    raise CliError(
        f"no {PROJECT_FILE} found in {here} or any parent — "
        "run inside a project, or create one with 'shdl new'"
    )


def load_project(root: Path) -> Project:
    file = root / PROJECT_FILE
    try:
        doc = tomllib.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CliError(f"no {PROJECT_FILE} at {file}") from None
    except tomllib.TOMLDecodeError as e:
        raise CliError(f"{file}: invalid TOML: {e}") from e

    proj = doc.get("project")
    if not isinstance(proj, dict):
        raise CliError(f"{file}: missing [project] table")
    for field in ("name", "version", "main"):
        if not isinstance(proj.get(field), str) or not proj[field]:
            raise CliError(f"{file}: [project] {field} is required (a non-empty string)")
    if not _NAME.match(proj["name"]):
        raise CliError(
            f"{file}: project name {proj['name']!r} must match [a-z][a-z0-9_]*"
        )
    for field in ("top", "shdl"):
        if field in proj and not isinstance(proj[field], str):
            raise CliError(f"{file}: [project] {field} must be a string")

    deps = _parse_dependencies(file, doc.get("dependencies", {}))

    registry = doc.get("registry", {})
    if not isinstance(registry, dict):
        raise CliError(f"{file}: [registry] must be a table")
    url = registry.get("url")
    if url is not None and not isinstance(url, str):
        raise CliError(f"{file}: [registry] url must be a string")

    return Project(
        root=root,
        name=proj["name"],
        version=proj["version"],
        main=proj["main"],
        top=proj.get("top"),
        shdl=proj.get("shdl"),
        dependencies=deps,
        registry_url=url,
    )


def _parse_dependencies(file: Path, table: object) -> dict[str, str | PathDep]:
    if not isinstance(table, dict):
        raise CliError(f"{file}: [dependencies] must be a table")
    deps: dict[str, str | PathDep] = {}
    for name, spec in table.items():
        if not _NAME.match(name):
            raise CliError(f"{file}: dependency name {name!r} must match [a-z][a-z0-9_]*")
        if isinstance(spec, str):
            deps[name] = spec
        elif isinstance(spec, dict) and set(spec) == {"path"} and isinstance(spec["path"], str):
            deps[name] = PathDep(spec["path"])
        else:
            raise CliError(
                f"{file}: dependency {name} must be a version-range string "
                f'or {{ path = "…" }}, got {spec!r}'
            )
    return deps


# --- textual edits ----------------------------------------------------------
_TABLE_HEADER = re.compile(r"\s*\[")
_DEPS_HEADER = re.compile(r"\s*\[dependencies\]\s*(#.*)?\n?\Z")


def _render_dep(name: str, spec: str | PathDep) -> str:
    if isinstance(spec, PathDep):
        return f'{name} = {{ path = "{spec.path}" }}'
    return f'{name} = "{spec}"'


def edit_dependencies(
    file: Path,
    add: dict[str, str | PathDep] | None = None,
    remove: set[str] | None = None,
) -> None:
    """Patch the ``[dependencies]`` table in place, byte-preserving the rest.

    After patching, the result is re-parsed and its dependency table compared
    against the intended mapping; any mismatch aborts without touching the
    file ("edit shdl.toml by hand").
    """
    add = add or {}
    remove = remove or set()
    # newline="" disables universal-newline translation: untouched CRLF lines
    # must survive byte-for-byte. New lines match the file's dominant style.
    original = file.read_text(encoding="utf-8", newline="")
    lines = original.splitlines(keepends=True)
    nl = "\r\n" if "\r\n" in original else "\n"

    # locate the [dependencies] table: (header index, end-exclusive index)
    header = end = None
    for i, line in enumerate(lines):
        if header is None:
            if _DEPS_HEADER.match(line):
                header = i
        elif _TABLE_HEADER.match(line):
            end = i
            break
    if header is not None and end is None:
        end = len(lines)

    if header is None:
        if remove:
            raise CliError(f"{file}: no [dependencies] table to remove from")
        body = "".join(_render_dep(n, s) + nl for n, s in add.items())
        text = original
        if text and not text.endswith(("\n", "\r")):
            text += nl
        text += f"{nl}[dependencies]{nl}" + body
    else:
        table = lines[header + 1 : end]
        pending = dict(add)

        def key_of(line: str) -> str | None:
            m = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", line)
            return m.group(1) if m else None

        new_table: list[str] = []
        for line in table:
            k = key_of(line)
            if k in remove:
                continue
            if k in pending:
                new_table.append(_render_dep(k, pending.pop(k)) + nl)
            else:
                new_table.append(line)
        if pending:
            # insert after the last non-blank line of the table (so trailing
            # blank lines before the next table stay where they were)
            insert_at = len(new_table)
            while insert_at > 0 and new_table[insert_at - 1].strip() == "":
                insert_at -= 1
            # a POSIX-incomplete final line would otherwise concatenate
            if insert_at > 0 and not new_table[insert_at - 1].endswith("\n"):
                new_table[insert_at - 1] += nl
            additions = [_render_dep(n, s) + nl for n, s in pending.items()]
            new_table[insert_at:insert_at] = additions
        text = "".join(lines[: header + 1] + new_table + lines[end:])

    # intent check: re-parse and compare the dependency table exactly
    intended: dict[str, object] = {}
    parsed_before = tomllib.loads(original).get("dependencies", {})
    for name, spec in parsed_before.items():
        intended[name] = spec
    for name in remove:
        if name not in intended:
            raise CliError(f"{file}: {name} is not a dependency")
        del intended[name]
    for name, spec in add.items():
        intended[name] = {"path": spec.path} if isinstance(spec, PathDep) else spec

    try:
        reparsed = tomllib.loads(text).get("dependencies", {})
    except tomllib.TOMLDecodeError:
        reparsed = None
    if reparsed != intended:
        raise CliError(
            f"cannot safely edit {file} — its [dependencies] table has a shape "
            "the editor does not understand; edit shdl.toml by hand"
        )

    fd, tmp = tempfile.mkstemp(dir=file.parent, prefix=".shdl.toml.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, os.stat(file).st_mode & 0o7777)  # mkstemp gives 0600
        os.replace(tmp, file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
