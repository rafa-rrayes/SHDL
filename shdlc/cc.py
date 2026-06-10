"""C compiler discovery and invocation.

Finds a host C compiler and builds the generated C into a shared library.
All failures surface as :class:`CCError` carrying the full command line and
the compiler's stderr verbatim — never a silent fallback.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

#: Flags used for release builds of generated C.
DEFAULT_CFLAGS: tuple[str, ...] = (
    "-std=c11",
    "-O2",
    "-shared",
    "-fPIC",
    "-fvisibility=hidden",
)


class CCError(Exception):
    """C compiler discovery or invocation failure.

    ``argv`` is the full command line attempted (empty if discovery failed);
    ``stderr`` is the compiler's stderr verbatim (empty if not run).
    """

    def __init__(self, message: str, *, argv: Sequence[str] = (), stderr: str = ""):
        super().__init__(message)
        self.argv = list(argv)
        self.stderr = stderr


def find_cc(cc: str | None = None) -> list[str]:
    """Resolve the C compiler to an argv prefix (e.g. ``["ccache", "clang"]``).

    Order: explicit ``cc`` argument, then ``$CC``, then the first of
    ``cc``/``clang``/``gcc`` on PATH. Values are shlex-split so wrappers like
    ``"ccache clang"`` work. Raises CCError if nothing is found.
    """

    def _resolve(value: str, source: str) -> list[str]:
        argv = shlex.split(value)
        if not argv:
            raise CCError(
                f"C compiler not found: {source} ({value!r}) is empty after splitting"
            )
        head = argv[0]
        if shutil.which(head) is None and not (
            os.path.isabs(head) and os.path.exists(head)
        ):
            raise CCError(
                f"C compiler not found: {head!r} (from {source}: {value!r}) "
                f"is not on PATH and is not an existing absolute path"
            )
        return argv

    if cc is not None:
        return _resolve(cc, "explicit cc argument")

    env_cc = os.environ.get("CC", "")
    if env_cc.strip():
        return _resolve(env_cc, "$CC")

    fallbacks = ("cc", "clang", "gcc")
    for name in fallbacks:
        if shutil.which(name) is not None:
            return [name]

    raise CCError(
        "C compiler not found: no explicit compiler given, $CC is unset, and "
        "none of " + ", ".join(repr(n) for n in fallbacks) + " is on PATH"
    )


def lib_suffix() -> str:
    """Shared-library suffix for this platform: .dylib / .so / .dll."""
    platform = sys.platform
    if platform == "darwin":
        return ".dylib"
    if platform in ("win32", "cygwin"):
        return ".dll"
    return ".so"


def build_shared(
    c_path: str | Path,
    out_path: str | Path,
    *,
    cc: str | None = None,
    cflags: Sequence[str] | None = None,
) -> Path:
    """Compile ``c_path`` into a shared library at ``out_path``.

    ``cflags`` defaults to :data:`DEFAULT_CFLAGS` (replaced, not appended,
    when given). Returns ``out_path`` as a Path. Raises CCError on a nonzero
    exit, with the compiler's stderr in the exception.
    """
    argv = (
        find_cc(cc)
        + list(cflags if cflags is not None else DEFAULT_CFLAGS)
        + ["-o", str(out_path), str(c_path)]
    )
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CCError(
            f"C compiler failed with exit code {proc.returncode}: "
            f"{shlex.join(argv)}\n--- stderr ---\n{proc.stderr}",
            argv=argv,
            stderr=proc.stderr,
        )
    return Path(out_path)
