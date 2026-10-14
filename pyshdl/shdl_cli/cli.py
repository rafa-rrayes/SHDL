"""``shdl``: the SHDL project manager and unified build/test/run driver.

    shdl new NAME [--top NAME]         scaffold a project directory
    shdl init [NAME] [--top NAME]      scaffold into the current directory
    shdl add PKG[@RANGE]... | --path DIR    add dependencies (and vendor them)
    shdl remove PKG...                 remove direct dependencies
    shdl install [--frozen] [--force]  sync shdl_modules/ to shdl.lock
    shdl build [--top N] [-o LIB] [--dev] [--cc CC] [--emit-base]
    shdl test [COMPONENT...]           run tests/*.tests.json
    shdl run [--top N]                 poke/peek REPL over the compiled circuit
    shdl search TERM                   search the package index
    shdl info PKG [--versions]         one package's metadata and exports
    shdl verify-package DIR [--packages-root ROOT]
    shdl publish DIR                   verify + print the PR playbook

Exit status: 0 on success, 1 on any diagnosed failure, 2 on usage errors.
Build/test/run never touch the network; add/install/search/info/publish
resolve against ``--index`` > ``$SHDL_INDEX_URL`` > ``[registry] url`` in
shdl.toml > the default Circuit Circus index.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from . import builder, vendor
from .errors import CliError
from .index_client import DEFAULT_INDEX, IndexClient, resolve_index_url
from .lockfile import (
    Lock,
    check_fresh,
    manifest_fingerprint,
    read_lock,
    write_lock,
)
from .project import (
    PathDep,
    Project,
    edit_dependencies,
    find_project,
    load_project,
    validate_package_name,
)
from .resolver import resolve
from .runner import run_cases
from .scaffold import create_project
from .semver import Range, Version, caret


# --- shared helpers ----------------------------------------------------------
def _project() -> Project:
    return load_project(find_project())


def _optional_project() -> Project | None:
    try:
        return load_project(find_project())
    except CliError:
        return None


def _client(index_flag: str | None, project: Project | None) -> IndexClient:
    return IndexClient(
        resolve_index_url(index_flag, project.registry_url if project else None)
    )


def _preflight_lock(project: Project) -> Lock:
    """A fresh lock for build/test/run — no network, ever.

    A project with no dependencies never needs a lock to build, so a missing
    or stale one degrades to the empty resolution instead of demanding
    'shdl install' for nothing.
    """
    url = resolve_index_url(None, project.registry_url)
    try:
        return check_fresh(project, url)
    except CliError:
        if not project.dependencies:
            return Lock(
                manifest_fingerprint=manifest_fingerprint({}, url),
                registry=url,
                packages={},
            )
        raise


def _prepared_include_dirs(project: Project) -> list[str]:
    lock = _preflight_lock(project)
    vendor.verify_vendored(project, lock)
    return vendor.include_dirs(project, lock)


# --- commands ------------------------------------------------------------------
def cmd_new(args) -> int:
    dest = Path(args.name)
    files = create_project(dest, dest.name, top=args.top)
    print(f"created project {dest.name} in {dest}/")
    for rel in files:
        print(f"  {rel}")
    print(f"next: cd {dest} && shdl build && shdl test")
    return 0


def cmd_init(args) -> int:
    cwd = Path.cwd()
    name = args.name or cwd.name
    files = create_project(cwd, name, top=args.top, into_existing=True)
    print(f"initialized project {name} in {cwd}")
    for rel in files:
        print(f"  {rel}")
    return 0


def _parse_add_specs(args, client: IndexClient) -> dict[str, str | PathDep]:
    additions: dict[str, str | PathDep] = {}
    for spec in args.packages:
        name, _, rng = spec.partition("@")
        validate_package_name(name, f"'{spec}'")
        if rng:
            Range.parse(rng)  # validate the grammar up front
            additions[name] = rng
        else:
            latest = client.registry_entry(name)["version"]
            additions[name] = caret(Version.parse(latest))
    return additions


def cmd_add(args) -> int:
    project = _project()
    client = _client(args.index, project)

    additions = _parse_add_specs(args, client)
    if args.path:
        pdir = Path(args.path)
        manifest_file = pdir / "package.json"
        if not manifest_file.is_file():
            raise CliError(f"--path {pdir}: no package.json there")
        try:
            name = json.loads(manifest_file.read_text(encoding="utf-8"))["name"]
        except (json.JSONDecodeError, KeyError) as e:
            raise CliError(f"{manifest_file}: not a valid package manifest: {e}") from e
        # a name shdl.toml cannot hold must be rejected here, not on next load
        validate_package_name(name, str(manifest_file))
        rel = Path(os.path.relpath(pdir.resolve(), project.root)).as_posix()
        additions[name] = PathDep(rel)
    if not additions:
        raise CliError("nothing to add — name packages or pass --path DIR")

    candidate = replace(
        project, dependencies={**project.dependencies, **additions}
    )
    lock = resolve(candidate, client)
    for line in vendor.sync(candidate, lock, client):
        print(line)
    # both files mutate only after resolution + vendoring succeeded
    edit_dependencies(project.file, add=additions)
    write_lock(project.lock_path, lock)
    for name, spec in additions.items():
        shown = f"path {spec.path}" if isinstance(spec, PathDep) else spec
        print(f"added {name} {shown}")
    return 0


def cmd_remove(args) -> int:
    project = _project()
    lock = read_lock(project.lock_path)
    for name in args.packages:
        if name in project.dependencies:
            continue
        requirers = (
            sorted(n for n, p in lock.packages.items() if name in p.dependencies)
            if lock
            else []
        )
        if requirers:
            raise CliError(
                f"{name} is not a direct dependency — it is required by "
                f"{', '.join(requirers)}"
            )
        raise CliError(f"{name} is not a dependency")

    removed = set(args.packages)
    candidate = replace(
        project,
        dependencies={
            k: v for k, v in project.dependencies.items() if k not in removed
        },
    )
    client = _client(args.index, project)
    new_lock = resolve(candidate, client)
    # record first, prune second: pruning is the destructive step, and a
    # failing shdl.toml edit must not leave the vendored tree missing
    edit_dependencies(project.file, remove=removed)
    write_lock(project.lock_path, new_lock)
    for line in vendor.sync(candidate, new_lock, client):
        print(line)
    for name in args.packages:
        print(f"removed {name}")
    return 0


def cmd_install(args) -> int:
    project = _project()
    url = resolve_index_url(args.index, project.registry_url)
    expected = manifest_fingerprint(project.dependencies, url)
    lock = read_lock(project.lock_path)
    client = IndexClient(url)
    if lock is None or lock.manifest_fingerprint != expected:
        if args.frozen:
            raise CliError(
                "shdl.lock is missing or stale and --frozen was given — "
                "run 'shdl install' without --frozen first"
            )
        lock = resolve(project, client)
        write_lock(project.lock_path, lock)
    lines = vendor.sync(project, lock, client, force=args.force)
    for line in lines:
        print(line)
    if not lines:
        n = sum(1 for p in lock.packages.values() if p.is_registry)
        print(f"up to date ({n} package{'s' if n != 1 else ''})")
    return 0


def cmd_build(args) -> int:
    project = _project()
    dirs = _prepared_include_dirs(project)
    out = builder.build(
        project,
        dirs,
        top=args.top,
        output=args.output,
        dev=args.dev,
        cc=args.cc,
        emit_base=args.emit_base,
    )
    print(f"built {out}")
    return 0


def cmd_test(args) -> int:
    project = _project()
    dirs = _prepared_include_dirs(project)
    tests_dir = project.root / "tests"
    test_files = sorted(tests_dir.glob("*.tests.json")) if tests_dir.is_dir() else []
    if not test_files:
        raise CliError(f"no test files (tests/*.tests.json) under {project.root}")

    wanted = set(args.components)
    seen: set[str] = set()
    passed = total = 0
    for tf in test_files:
        try:
            spec = json.loads(tf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise CliError(f"{tf}: invalid JSON: {e}") from e
        cases = spec.get("cases", [])
        if wanted:
            cases = [c for c in cases if c.get("component") in wanted]
        if not cases:
            continue
        seen.update(c.get("component") for c in cases if c.get("component"))
        print(f"[{tf.name}]")
        lines, p, t = run_cases(
            lambda comp: builder.open_circuit(
                project, dirs, comp, dev=args.dev, cc=args.cc
            ),
            cases,
        )
        for line in lines:
            print(line)
        passed += p
        total += t
    if wanted - seen:
        raise CliError(
            f"no test cases for component(s): {', '.join(sorted(wanted - seen))}"
        )
    if total == 0:
        raise CliError("test files exist but contain no cases")
    print(f"\n{passed}/{total} cases green")
    return 0 if passed == total else 1


_REPL_HELP = """\
commands:
  poke SIGNAL VALUE     drive an input (VALUE may be 0x…/0b… too)
  peek SIGNAL           read a signal
  step [N]              advance N unit-delay cycles (default 1)
  settle                step until stable, print how many cycles it took
  reset                 back to the power-on state
  info                  ports of the compiled circuit
  quit                  exit (Ctrl-D works too)"""


def cmd_run(args) -> int:
    project = _project()
    dirs = _prepared_include_dirs(project)
    c = builder.open_circuit(project, dirs, args.top, dev=args.dev, cc=args.cc)
    interactive = sys.stdin.isatty()
    if interactive:
        print(f"{project.name}: top={args.top or project.top or '(module top)'} — 'help' for commands")
    try:
        while True:
            if interactive:
                print("shdl> ", end="", flush=True)
            line = sys.stdin.readline()
            if not line:
                break
            tokens = line.split()
            if not tokens:
                continue
            cmd, rest = tokens[0], tokens[1:]
            try:
                if cmd == "quit" or cmd == "exit":
                    break
                elif cmd == "help":
                    print(_REPL_HELP)
                elif cmd == "poke" and len(rest) == 2:
                    c.poke(rest[0], int(rest[1], 0))
                elif cmd == "peek" and len(rest) == 1:
                    print(c.peek(rest[0]))
                elif cmd == "step" and len(rest) <= 1:
                    c.step(int(rest[0], 0) if rest else 1)
                elif cmd == "settle" and not rest:
                    print(f"settled after {c.settle()} cycle(s)")
                elif cmd == "reset" and not rest:
                    c.reset()
                elif cmd == "info" and not rest:
                    print(f"inputs:  {', '.join(c.inputs)}")
                    print(f"outputs: {', '.join(c.outputs)}")
                else:
                    print(f"error: unknown command {line.strip()!r} — 'help' lists them")
            except Exception as e:  # noqa: BLE001 - REPL stays alive on bad input
                print(f"error: {e}")
    finally:
        c.close()
    return 0


def cmd_search(args) -> int:
    client = _client(args.index, _optional_project())
    term = args.term.lower()
    hits = [
        p
        for p in client.registry().get("packages", [])
        if term in p["name"].lower()
        or term in p.get("summary", "").lower()
        or any(term in k.lower() for k in p.get("keywords", []))
    ]
    if not hits:
        print(f"no packages match {args.term!r} (index: {client.index_url})")
        return 0
    width = max(len(f"{p['name']} {p['version']}") for p in hits)
    for p in hits:
        head = f"{p['name']} {p['version']}"
        print(f"{head:<{width}}  {p.get('summary', '')}")
    return 0


def cmd_info(args) -> int:
    client = _client(args.index, _optional_project())
    idx = client.package_index(args.package)
    latest = idx["latest"]
    v = idx["versions"][latest]
    print(f"{args.package} {latest} — {v['summary']}")
    if v.get("description"):
        print(f"\n{v['description']}")
    print()
    print(f"license:      {v['license']}")
    print(f"authors:      {', '.join(v['authors'])}")
    if v.get("homepage"):
        print(f"homepage:     {v['homepage']}")
    if v.get("keywords"):
        print(f"keywords:     {', '.join(v['keywords'])}")
    print(f"shdl:         {v['shdl']}")
    deps = v.get("dependencies", {})
    print(
        "dependencies: "
        + (", ".join(f"{d} {r}" for d, r in deps.items()) if deps else "(none)")
    )
    exports = v.get("exports", [])
    print(f"\nexports ({len(exports)}):")
    width = max((len(e["name"]) for e in exports), default=0)
    for e in exports:
        print(f"  {e['name']:<{width}}  {e.get('summary', '')}")
    if args.versions:
        print("\nversions:")
        for ver in sorted(idx["versions"], key=Version.parse, reverse=True):
            marker = " (latest)" if ver == latest else ""
            print(f"  {ver}{marker}")
    return 0


def cmd_verify_package(args) -> int:
    from .publish import verify_package

    root = Path(args.packages_root) if args.packages_root else None
    lines, ok = verify_package(Path(args.directory), root)
    for line in lines:
        print(line)
    print(f"\n{'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def cmd_publish(args) -> int:
    from .publish import (
        check_not_published,
        load_package_manifest,
        publish_playbook,
        verify_package,
    )

    pkg_dir = Path(args.directory)
    manifest = load_package_manifest(pkg_dir)
    client = _client(args.index, _optional_project())
    check_not_published(manifest, client)
    root = Path(args.packages_root) if args.packages_root else None
    lines, ok = verify_package(pkg_dir, root)
    for line in lines:
        print(line)
    if not ok:
        print("\nFAIL — fix the package before publishing")
        return 1
    print()
    for line in publish_playbook(pkg_dir.resolve(), manifest, client.index_url):
        print(line)
    return 0


# --- argument parsing ------------------------------------------------------------
def _add_index_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--index",
        metavar="URL",
        help=f"package index URL (default: $SHDL_INDEX_URL, then [registry] url, then {DEFAULT_INDEX})",
    )


def _add_build_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dev", action="store_true", help="compile the C with -O0 (fast builds, slower sim)")
    p.add_argument("--cc", metavar="CC", help="C compiler (default: $CC, then cc/clang/gcc)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="shdl",
        description="SHDL project manager and build/test/run driver.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="scaffold a new project directory")
    p.add_argument("name", help="project directory (its basename is the project name)")
    p.add_argument("--top", default="Main", help="top component name (default: Main)")

    p = sub.add_parser("init", help="scaffold a project into the current directory")
    p.add_argument("name", nargs="?", help="project name (default: the directory name)")
    p.add_argument("--top", default="Main", help="top component name (default: Main)")

    p = sub.add_parser("add", help="add dependencies, vendor them, update shdl.toml + shdl.lock")
    p.add_argument("packages", nargs="*", metavar="PKG[@RANGE]",
                   help="registry packages (default range: caret of the latest version)")
    p.add_argument("--path", metavar="DIR", help="add a local directory as a path dependency")
    _add_index_flag(p)

    p = sub.add_parser("remove", help="remove direct dependencies")
    p.add_argument("packages", nargs="+", metavar="PKG")
    _add_index_flag(p)

    p = sub.add_parser("install", help="sync shdl_modules/ to shdl.lock")
    p.add_argument("--frozen", action="store_true",
                   help="fail if shdl.lock is missing or stale (CI semantics)")
    p.add_argument("--force", action="store_true",
                   help="re-fetch every package even if it looks current")
    _add_index_flag(p)

    p = sub.add_parser("build", help="flatten + compile to a shared library in build/")
    p.add_argument("--top", metavar="NAME", help="top component (default: [project] top)")
    p.add_argument("-o", "--output", metavar="LIB", help="shared-library path")
    p.add_argument("--emit-base", action="store_true",
                   help="also write the flattened Base SHDL to build/<name>.base.shdl")
    _add_build_flags(p)

    p = sub.add_parser("test", help="run tests/*.tests.json")
    p.add_argument("components", nargs="*", metavar="COMPONENT",
                   help="only run cases for these components")
    _add_build_flags(p)

    p = sub.add_parser("run", help="a poke/peek/step REPL over the compiled circuit")
    p.add_argument("--top", metavar="NAME", help="top component (default: [project] top)")
    _add_build_flags(p)

    p = sub.add_parser("search", help="search the package index")
    p.add_argument("term")
    _add_index_flag(p)

    p = sub.add_parser("info", help="show one package's metadata and exports")
    p.add_argument("package")
    p.add_argument("--versions", action="store_true", help="also list every published version")
    _add_index_flag(p)

    p = sub.add_parser("verify-package",
                       help="verify a package directory (manifest, builds, vectors)")
    p.add_argument("directory")
    p.add_argument("--packages-root", metavar="ROOT",
                   help="directory holding dependency packages (default: DIR/..)")

    p = sub.add_parser("publish", help="verify a package and print the CCircus PR playbook")
    p.add_argument("directory")
    p.add_argument("--packages-root", metavar="ROOT",
                   help="directory holding dependency packages (default: DIR/..)")
    _add_index_flag(p)

    return ap


_COMMANDS = {
    "new": cmd_new,
    "init": cmd_init,
    "add": cmd_add,
    "remove": cmd_remove,
    "install": cmd_install,
    "build": cmd_build,
    "test": cmd_test,
    "run": cmd_run,
    "search": cmd_search,
    "info": cmd_info,
    "verify-package": cmd_verify_package,
    "publish": cmd_publish,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.platform == "win32":
        print(
            "shdl: warning: Windows is untested for this release; "
            "paths and C toolchain discovery may misbehave",
            file=sys.stderr,
        )
    try:
        return _COMMANDS[args.command](args)
    except CliError as e:
        print(f"shdl: error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("shdl: interrupted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
