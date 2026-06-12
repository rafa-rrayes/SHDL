"""SR16 gate-level driver: ctypes wrapper over a compiled sr16.shdl library.

Standalone on purpose (no imports from the test tree): anything that can
dlopen the compiled circuit can run programs on it.

    from sr16tools.asm import assemble
    from sr16tools.driver import SR16

    cpu = SR16("sr16.dylib")
    cpu.load_program(assemble(src))
    cpu.run()
    print(cpu.state())

Clocking (ISA.md §5): two-phase non-overlapping, with the settle budget
spent BEFORE the Phi1 strobe — combinational decode must be stable when the
masters capture. The budgets are pinned here; a (deferred) guard test doubles
them and asserts the architectural trace is unchanged.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

# Unit-delay ticks. T_SETTLE covers the longest combinational path (control
# decode -> register read -> ALU ripple-carry -> RAM decode -> read tree ->
# writeback mux, roughly 120 gate levels) with margin to spare.
T_CAP = 16
T_GAP = 4
T_SETTLE = 200

__all__ = ["SR16", "T_CAP", "T_GAP", "T_SETTLE"]


class SR16:
    def __init__(
        self,
        lib_path: str | Path,
        *,
        t_cap: int = T_CAP,
        t_gap: int = T_GAP,
        t_settle: int = T_SETTLE,
        fast_settle: bool = False,
    ):
        """``fast_settle=True`` routes every wait through the library's
        ``step_settle`` (fixed-point early exit): the budgets above become
        ceilings instead of exact tick counts. Observably identical — the
        early exit fires only once a tick changes no gate — just faster.
        Requires a library built by a compiler that exports ``step_settle``.
        """
        self.t_cap = t_cap
        self.t_gap = t_gap
        self.t_settle = t_settle
        self.fast_settle = fast_settle
        lib = ctypes.CDLL(str(lib_path), mode=os.RTLD_LOCAL)
        lib.reset.argtypes = []
        lib.reset.restype = None
        lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
        lib.poke.restype = None
        lib.peek.argtypes = [ctypes.c_char_p]
        lib.peek.restype = ctypes.c_uint64
        lib.step.argtypes = [ctypes.c_int]
        lib.step.restype = None
        if fast_settle:
            lib.step_settle.argtypes = [ctypes.c_int]
            lib.step_settle.restype = ctypes.c_int
        self._lib = lib

    # --- raw circuit access --------------------------------------------------

    def poke(self, name: str, value: int) -> None:
        self._lib.poke(name.encode(), value)

    def peek(self, name: str) -> int:
        return int(self._lib.peek(name.encode()))

    def step(self, n: int) -> None:
        if self.fast_settle:
            self._lib.step_settle(n)
        else:
            self._lib.step(n)

    def reset(self) -> None:
        """Power-on state: all latches 0 (PC = 0, FETCH, not halted)."""
        self._lib.reset()

    # --- clocking ------------------------------------------------------------

    def clock(self, n: int = 1) -> None:
        for _ in range(n):
            self.step(self.t_settle)
            self.poke("Phi1", 1)
            self.step(self.t_cap)
            self.poke("Phi1", 0)
            self.step(self.t_gap)
            self.poke("Phi2", 1)
            self.step(self.t_cap)
            self.poke("Phi2", 0)
            self.step(self.t_gap)

    # --- DMA port (ISA.md §6) --------------------------------------------------

    def load_program(self, words: list[int]) -> None:
        """Write ``words`` to MEM[0..]; the CPU is frozen while LdEn is high."""
        self.poke("LdEn", 1)
        self.poke("LdWe", 1)
        for addr, word in enumerate(words):
            self.poke("LdAddr", addr)
            self.poke("LdData", word & 0xFFFF)
            self.step(self.t_settle)  # address decode before the strobe
            self.poke("Phi1", 1)
            self.step(self.t_cap)
            self.poke("Phi1", 0)
            self.step(self.t_gap)
        self.poke("LdWe", 0)
        self.poke("LdEn", 0)
        self.step(self.t_settle)

    def read_mem(self, addr: int) -> int:
        self.poke("LdEn", 1)
        self.poke("LdWe", 0)
        self.poke("LdAddr", addr)
        self.step(self.t_settle)
        value = self.peek("MemOut")
        self.poke("LdEn", 0)
        self.step(self.t_settle)
        return value

    # --- architectural state ---------------------------------------------------

    def state(self) -> dict:
        flags = self.peek("Flags")
        return {
            "pc": self.peek("PCout"),
            "ir": self.peek("IRout"),
            "state": self.peek("State"),
            "halted": self.peek("Halted"),
            "z": flags & 1,
            "n": (flags >> 1) & 1,
            "c": (flags >> 2) & 1,
            "v": (flags >> 3) & 1,
            "regs": [self.peek(f"R{i}out") for i in range(8)],
        }

    # --- execution ---------------------------------------------------------------

    def step_instruction(self) -> int:
        """Clock until the FSM is back in FETCH (or halted); returns cycles."""
        for cycles in range(1, 9):
            self.clock()
            if self.peek("Halted") or self.peek("State") == 0:
                return cycles
        raise RuntimeError(
            f"FSM did not return to FETCH within 8 clocks "
            f"(state={self.peek('State')}, ir={self.peek('IRout'):#06x})"
        )

    def run(self, max_instructions: int = 10_000) -> int:
        """Execute until HALT; returns total clock cycles consumed."""
        cycles = 0
        for _ in range(max_instructions):
            if self.peek("Halted"):
                return cycles
            cycles += self.step_instruction()
        if not self.peek("Halted"):
            raise RuntimeError(f"not halted after {max_instructions} instructions")
        return cycles


def _main() -> None:
    """Assemble and run a program on a compiled SR16 library.

    usage: python -m sr16tools.driver LIB ASM_FILE [MAX_INSTRUCTIONS]
    """
    import sys

    from .asm import assemble

    if len(sys.argv) not in (3, 4):
        raise SystemExit(_main.__doc__)
    lib, src = sys.argv[1], Path(sys.argv[2]).read_text()
    limit = int(sys.argv[3]) if len(sys.argv) == 4 else 10_000

    cpu = SR16(lib)
    cpu.reset()
    cpu.load_program(assemble(src))
    cycles = cpu.run(limit)
    st = cpu.state()
    print(f"halted after {cycles} cycles, pc={st['pc']:#06x}")
    print("flags:", " ".join(f"{k}={st[k]}" for k in "zncv"))
    for i, r in enumerate(st["regs"]):
        print(f"  R{i} = {r:#06x} ({r})")


if __name__ == "__main__":
    _main()
