"""Session-scoped build cache for the SR16 CPU suite.

Flattens modules from examples/CPU (with examples/ on the include path so the
shared library parts — stdgates, dLatch, … — resolve) and compiles them with
STRICT_CFLAGS via the same machinery as the compiler suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from compiler.harness import STRICT_CFLAGS, Sim, load_fresh_copy

from flattener.pipeline import flatten_program
from shdlc.cc import lib_suffix

REPO = Path(__file__).resolve().parents[2]
CPU_DIR = REPO / "examples" / "CPU"
EXAMPLES = REPO / "examples"
TS = "2026-01-01T00:00:00Z"

# sr16tools (assembler / golden model / driver) lives next to the SHDL sources
if str(CPU_DIR) not in sys.path:
    sys.path.insert(0, str(CPU_DIR))


class CpuBuildCache:
    def __init__(self, root: Path):
        self.root = root
        self.libs = root / "libs"
        self.libs.mkdir()
        self.instances = root / "instances"
        self.instances.mkdir()
        self._texts: dict[tuple, str] = {}
        self._built: dict[tuple, Path] = {}

    def text(self, module: str, top: str | None = None) -> str:
        key = (module, top)
        if key not in self._texts:
            src = CPU_DIR / f"{module}.shdl"
            if not src.exists():  # shared library parts (dLatch, srLatch, ...)
                src = EXAMPLES / f"{module}.shdl"
            self._texts[key] = flatten_program(
                str(src),
                include_dirs=[str(EXAMPLES)],
                top=top,
                timestamp=TS,
            ).text
        return self._texts[key]

    def lib(self, module: str, top: str | None = None) -> Path:
        key = (module, top)
        if key not in self._built:
            from shdlc.compile import build_library

            out = self.libs / f"{module}-{top or 'top'}{lib_suffix()}"
            self._built[key] = Path(
                build_library(self.text(module, top), out, cflags=STRICT_CFLAGS)
            )
        return self._built[key]

    def sim(self, module: str, top: str | None = None) -> Sim:
        """A fresh, independent instance (per-instance dylib copy)."""
        return load_fresh_copy(self.lib(module, top), self.instances)

    def fresh_path(self, module: str, top: str | None = None) -> Path:
        """A private dylib copy for non-Sim loaders (e.g. sr16tools.driver).

        dlopen caches by path, so a caller that does its own CDLL must get a
        unique file to own that instance's global state.
        """
        import itertools
        import shutil

        if not hasattr(self, "_path_counter"):
            self._path_counter = itertools.count()
        src = self.lib(module, top)
        dst = self.instances / f"{src.stem}.drv{next(self._path_counter):04d}{src.suffix}"
        shutil.copy2(src, dst)
        return dst


@pytest.fixture(scope="session")
def cpu_builds(tmp_path_factory) -> CpuBuildCache:
    return CpuBuildCache(tmp_path_factory.mktemp("sr16-builds"))


@pytest.fixture(scope="session")
def sr16(cpu_builds):
    """One full-CPU instance for the whole session (tests reset() it)."""
    from sr16tools.driver import SR16

    return SR16(cpu_builds.fresh_path("sr16"))


# --- lockstep runner: circuit vs golden model -------------------------------


def lockstep(cpu, source, *, max_instructions: int = 1000, check_mem: bool = True):
    """Run a program on the gate-level CPU and the golden model in lockstep.

    After EVERY instruction the full architectural state (PC, R0–R7, Z/N/C/V,
    halted) and the cycle cost are compared; afterwards every memory word the
    golden model wrote (plus untouched sentinels) is compared through the DMA
    port. Expected values come exclusively from sr16tools.golden.Golden.

    Returns the golden model (for extra hand-derived assertions).
    """
    from sr16tools.asm import assemble
    from sr16tools.golden import MEM_WORDS, Golden

    words = assemble(source) if isinstance(source, str) else list(source)

    golden = Golden()
    golden.load(words)
    written: set[int] = set()
    real_wr = golden._wr_mem
    golden._wr_mem = lambda addr, value: (written.add(addr % MEM_WORDS), real_wr(addr, value))[1]

    cpu.reset()
    cpu.load_program(words)

    executed = 0
    while not golden.halted:
        assert executed < max_instructions, f"golden model not halted after {executed} instructions"
        at_pc, ir = golden.pc, golden.mem[golden.pc % MEM_WORDS]
        want_cycles = golden.step()
        got_cycles = cpu.step_instruction()
        executed += 1
        st = cpu.state()
        ctx = f"instr #{executed} @ pc={at_pc:#06x} ir={ir:#06x}"
        assert got_cycles == want_cycles, f"{ctx}: cycles {got_cycles} != {want_cycles}"
        assert st["pc"] == golden.pc, f"{ctx}: pc {st['pc']:#06x} != {golden.pc:#06x}"
        assert st["regs"] == golden.regs, f"{ctx}: regs {st['regs']} != {golden.regs}"
        got_flags = (st["z"], st["n"], st["c"], st["v"])
        want_flags = (golden.z, golden.n, golden.c, golden.v)
        assert got_flags == want_flags, f"{ctx}: flags ZNCV {got_flags} != {want_flags}"
        assert st["halted"] == int(golden.halted), f"{ctx}: halted {st['halted']}"

    if check_mem:
        sentinels = {0, 1, 63, 64, 65, 191, 255, len(words) - 1}
        for addr in sorted(written | sentinels):
            got = cpu.read_mem(addr)
            assert got == golden.mem[addr], (
                f"mem[{addr:#04x}]: {got:#06x} != {golden.mem[addr]:#06x}"
            )
    return golden


# --- two-phase clock helpers (ISA.md §5) -----------------------------------
# Small-part settle budgets; the full CPU uses the pinned values in
# sr16tools/driver.py. Generous on purpose: unit tests value clarity over speed.

T_CAP = 16
T_GAP = 4
T_SETTLE = 40


def clock(sim: Sim, n: int = 1) -> None:
    """n full two-phase clock cycles.

    Settles combinational logic BEFORE the Phi1 strobe (pokes happen right
    before clock(), so decode paths need their settle time first), then
    captures on Phi1 and publishes on Phi2.
    """
    for _ in range(n):
        sim.step(T_SETTLE)
        sim.poke("Phi1", 1)
        sim.step(T_CAP)
        sim.poke("Phi1", 0)
        sim.step(T_GAP)
        sim.poke("Phi2", 1)
        sim.step(T_CAP)
        sim.poke("Phi2", 0)
        sim.step(T_GAP)
