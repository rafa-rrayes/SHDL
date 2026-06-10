"""Session-scoped build cache for compiler tests.

Builds happen lazily inside tests (never at collection time) so the suite
collects cleanly while the compiler internals are still stubs. Every build
uses STRICT_CFLAGS, proving the generated C is warning-free.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from shdlc.cc import lib_suffix

from .harness import (
    STRICT_CFLAGS,
    DualSim,
    Sim,
    flatten_fixture_text,
    load_fresh_copy,
)


class BuildCache:
    """Caches flattened fixture text and built libraries for one session."""

    def __init__(self, root: Path):
        self.root = root
        self.libs = root / "libs"
        self.libs.mkdir()
        self.instances = root / "instances"
        self.instances.mkdir()
        self._texts: dict[str, str] = {}
        self._built: dict[str, Path] = {}

    # -- sources -----------------------------------------------------------

    def fixture_text(self, name: str) -> str:
        """Flattened Base SHDL text of ``tests/fixtures/<name>.shdl``."""
        if name not in self._texts:
            self._texts[name] = flatten_fixture_text(name)
        return self._texts[name]

    # -- builds ------------------------------------------------------------

    def lib_from_text(
        self,
        key: str,
        base_text: str,
        *,
        cflags: Sequence[str] = STRICT_CFLAGS,
    ) -> Path:
        """Build ``base_text`` into a shared library, cached by ``key``."""
        if key not in self._built:
            from shdlc.compile import build_library

            out = self.libs / f"{key}{lib_suffix()}"
            self._built[key] = Path(build_library(base_text, out, cflags=cflags))
        return self._built[key]

    def fixture_lib(self, name: str) -> Path:
        return self.lib_from_text(f"fix-{name}", self.fixture_text(name))

    # -- fresh instances ----------------------------------------------------

    def sim_from_text(self, key: str, base_text: str) -> Sim:
        """A fresh, independent Sim (per-instance dylib copy)."""
        return load_fresh_copy(self.lib_from_text(key, base_text), self.instances)

    def sim_fixture(self, name: str) -> Sim:
        return load_fresh_copy(self.fixture_lib(name), self.instances)

    def dual_from_text(self, key: str, base_text: str, *, seed=None, label="") -> DualSim:
        return DualSim(
            self.sim_from_text(key, base_text),
            base_text,
            seed=seed,
            label=label or key,
        )

    def dual_fixture(self, name: str, *, seed=None) -> DualSim:
        return DualSim(
            self.sim_fixture(name),
            self.fixture_text(name),
            seed=seed,
            label=name,
        )


@pytest.fixture(scope="session")
def builds(tmp_path_factory) -> BuildCache:
    return BuildCache(tmp_path_factory.mktemp("shdlc-builds"))
