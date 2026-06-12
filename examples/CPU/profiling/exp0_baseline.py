"""Exp 0: baseline — phase timing + exact ABI call counts for the stock mul.s run."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sr16tools.asm import assemble
from sr16tools.driver import SR16

LIB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sr16.dylib"
SRC = Path(__file__).resolve().parents[1] / "programs" / "mul.s"


class CountingSR16(SR16):
    """Counts ABI calls and ticks without changing semantics."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.n_step = self.n_poke = self.n_peek = self.ticks = 0

    def step(self, n):
        self.n_step += 1
        self.ticks += n
        super().step(n)

    def poke(self, name, value):
        self.n_poke += 1
        super().poke(name, value)

    def peek(self, name):
        self.n_peek += 1
        return super().peek(name)


def main():
    words = assemble(SRC.read_text())
    print(f"program: {len(words)} words")

    cpu = CountingSR16(LIB)

    t0 = time.perf_counter()
    cpu.reset()
    t1 = time.perf_counter()
    cpu.load_program(words)
    t2 = time.perf_counter()
    snap = (cpu.n_step, cpu.n_poke, cpu.n_peek, cpu.ticks)
    cycles = cpu.run()
    t3 = time.perf_counter()
    st = cpu.state()
    t4 = time.perf_counter()

    assert st["regs"][3] == 132, st
    print(f"cycles: {cycles}")
    print(f"reset : {(t1 - t0) * 1e3:8.2f} ms")
    print(f"load  : {(t2 - t1) * 1e3:8.2f} ms  ({snap[3]} ticks)")
    print(f"run   : {(t3 - t2) * 1e3:8.2f} ms  ({cpu.ticks - snap[3]} ticks)")
    print(f"state : {(t4 - t3) * 1e3:8.2f} ms")
    print(f"total : {(t4 - t0) * 1e3:8.2f} ms")
    print(f"calls : step={cpu.n_step} poke={cpu.n_poke} peek={cpu.n_peek} ticks={cpu.ticks}")
    run_s = t3 - t2
    print(f"run-phase ticks/sec: {(cpu.ticks - snap[3]) / run_s / 1e3:.0f}k")
    print(f"gate-evals/sec (run): {(cpu.ticks - snap[3]) * 42530 / run_s / 1e9:.2f} G")


if __name__ == "__main__":
    main()
