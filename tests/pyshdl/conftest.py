"""Shared fixtures for the PySHDL suite.

Example circuits are compiled once per session through the public front door
(``Circuit`` with an explicit ``build_dir``), then handed out as independent
instances via ``Circuit.from_library`` — the C compiler runs once per
example while every test still gets a fresh, isolated simulation.

NOTE: this directory is deliberately NOT a package (no ``__init__.py``): a
test package literally named ``pyshdl`` would shadow the ``pyshdl`` source
package under pytest's prepend import mode. Test basenames are prefixed
``test_pyshdl_`` to stay unique repo-wide.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyshdl import Circuit
from shdlc.cc import lib_suffix

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"


class ExampleCache:
    """Session-scoped build cache over ``examples/*.shdl``."""

    def __init__(self, root: Path):
        self.root = root
        self.instances = root / "instances"
        self.instances.mkdir()
        self._artifacts: dict[tuple[str, str | None], tuple[Path, Path]] = {}

    def artifacts(self, name: str, top: str | None = None) -> tuple[Path, Path]:
        """``(shared_library, base_shdl)`` artifact paths, built on first use."""
        key = (name, top)
        if key not in self._artifacts:
            art_dir = self.root / f"{name}-{top or 'top'}"
            Circuit(EXAMPLES / f"{name}.shdl", top=top, build_dir=art_dir).close()
            lib = next(p for p in art_dir.glob(f"*{lib_suffix()}") if ".copy" not in p.name)
            base = next(art_dir.glob("*.base.shdl"))
            self._artifacts[key] = (lib, base)
        return self._artifacts[key]

    def base_text(self, name: str, top: str | None = None) -> str:
        return self.artifacts(name, top)[1].read_text(encoding="utf-8")

    def fresh(self, name: str, top: str | None = None, *, strict: bool = True) -> Circuit:
        """A fresh, independent Circuit over the cached build."""
        lib, base = self.artifacts(name, top)
        return Circuit.from_library(lib, base=base, strict=strict, build_dir=self.instances)


@pytest.fixture(scope="session")
def examples(tmp_path_factory) -> ExampleCache:
    return ExampleCache(tmp_path_factory.mktemp("pyshdl-examples"))
