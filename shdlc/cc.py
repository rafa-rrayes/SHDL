"""C compiler discovery and invocation.

Finds a host C compiler and builds the generated C into a shared library.
All failures surface as :class:`CCError` carrying the full command line and
the compiler's stderr verbatim — never a silent fallback.
"""

from __future__ import annotations

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
    raise NotImplementedError


def lib_suffix() -> str:
    """Shared-library suffix for this platform: .dylib / .so / .dll."""
    raise NotImplementedError


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
    raise NotImplementedError
