"""Validate the compiled Life circuit against an independent Python model."""
from __future__ import annotations

from pathlib import Path

from SHDL import Circuit

# cell.shdl imports fullAdder (examples/) and seq (examples/CPU/)
EXAMPLES = Path(__file__).resolve().parents[1]

# ---- independent reference: toroidal Conway's Game of Life ----------------

def ref_step(grid: list[list[int]]) -> list[list[int]]:
    H, W = len(grid), len(grid[0])
    out = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            n = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    n += grid[(r + dr) % H][(c + dc) % W]
            out[r][c] = 1 if (n == 3 or (grid[r][c] and n == 2)) else 0
    return out


# ---- two-phase clock over the Circuit driver ------------------------------

class LifeDriver:
    def __init__(self, path, W, H, settle=80, cap=16, gap=4, cc=None):
        self.W, self.H = W, H
        self.s, self.cap, self.gap = settle, cap, gap
        self.c = Circuit(path, include_dirs=[EXAMPLES, EXAMPLES / "CPU"], cc=cc)
        self.c.reset()

    def _clock(self):
        c = self.c
        c.step_settle(self.s)
        c.poke("Phi1", 1); c.step_settle(self.cap)
        c.poke("Phi1", 0); c.step_settle(self.gap)
        c.poke("Phi2", 1); c.step_settle(self.cap)
        c.poke("Phi2", 0); c.step_settle(self.gap)

    def load(self, grid):
        c = self.c
        c.poke("Load", 1)
        for r in range(self.H):
            bits = 0
            for col in range(self.W):
                if grid[r][col]:
                    bits |= (1 << col)          # bit 0 (LSB) = column 1
            c.poke(f"S{r + 1}", bits)
        self._clock()
        c.poke("Load", 0)

    def gen(self):
        self._clock()

    def read(self):
        out = []
        for r in range(self.H):
            bits = self.c.peek(f"Q{r + 1}")
            out.append([(bits >> col) & 1 for col in range(self.W)])
        return out

    def close(self):
        self.c.close()


def show(grid):
    return "\n".join("".join("#" if x else "." for x in row) for row in grid)


if __name__ == "__main__":
    W = H = 8
    drv = LifeDriver("life8.shdl", W, H)

    # blinker (period-2 oscillator) + a glider, on the torus
    grid = [[0] * W for _ in range(H)]
    for c in (2, 3, 4):
        grid[1][c] = 1                          # horizontal blinker
    glider = [(4, 4), (5, 5), (6, 3), (6, 4), (6, 5)]
    for (r, c) in glider:
        grid[r][c] = 1

    drv.load(grid)
    hw = drv.read()
    print("loaded pattern, hardware vs reference match:", hw == grid)

    ref = grid
    ok = True
    for g in range(1, 13):
        ref = ref_step(ref)
        drv.gen()
        hw = drv.read()
        same = hw == ref
        ok = ok and same
        print(f"gen {g:2d}: match={same}")
        if not same:
            print("  HARDWARE:\n" + show(hw))
            print("  REFERENCE:\n" + show(ref))
            break
    drv.close()
    print("ALL MATCH" if ok else "MISMATCH")
