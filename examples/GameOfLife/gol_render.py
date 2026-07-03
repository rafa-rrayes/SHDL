"""Run the gate-level Game of Life and render it to an animated GIF.

Builds the compiled circuit once, seeds a torus with several gliders (all
four orientations, so they fly in different directions and eventually
collide) plus a pulsar, clocks it generation by generation, checks every
generation against an independent Python model, and paints the result.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from validate import LifeDriver, ref_step

HERE = Path(__file__).resolve().parent

W = H = 32
GENS = 120

# ---- patterns -------------------------------------------------------------

GLIDER = [(0, 1), (1, 2), (2, 0), (2, 1), (2, 2)]   # base: travels down-right

def oriented(cells, flip_r=False, flip_c=False):
    out = []
    for (r, c) in cells:
        rr = (2 - r) if flip_r else r
        cc = (2 - c) if flip_c else c
        out.append((rr, cc))
    return out

PULSAR = []
_p = [(2, 4), (2, 5), (2, 6), (2, 10), (2, 11), (2, 12)]
# build the classic 13x13 pulsar from its symmetric quadrant strokes
_base = [
    (0, 2), (0, 3), (0, 4), (0, 8), (0, 9), (0, 10),
    (2, 0), (3, 0), (4, 0), (2, 5), (3, 5), (4, 5),
    (2, 7), (3, 7), (4, 7), (2, 12), (3, 12), (4, 12),
    (5, 2), (5, 3), (5, 4), (5, 8), (5, 9), (5, 10),
    (7, 2), (7, 3), (7, 4), (7, 8), (7, 9), (7, 10),
    (8, 0), (9, 0), (10, 0), (8, 5), (9, 5), (10, 5),
    (8, 7), (9, 7), (10, 7), (8, 12), (9, 12), (10, 12),
    (12, 2), (12, 3), (12, 4), (12, 8), (12, 9), (12, 10),
]
PULSAR = _base


def stamp(grid, cells, r0, c0):
    for (r, c) in cells:
        grid[(r0 + r) % H][(c0 + c) % W] = 1


def build_seed():
    g = [[0] * W for _ in range(H)]
    stamp(g, oriented(GLIDER), 1, 1)                       # down-right
    stamp(g, oriented(GLIDER, flip_c=True), 1, 26)         # down-left
    stamp(g, oriented(GLIDER, flip_r=True), 26, 2)         # up-right
    stamp(g, oriented(GLIDER, flip_r=True, flip_c=True), 26, 27)  # up-left
    stamp(g, GLIDER, 14, 6)                                # a fifth, into the fray
    stamp(g, PULSAR, 9, 9)                                 # pulsing centerpiece
    return g


# ---- color: age-based palette (cosmetic, derived from hardware output) -----

BG = (12, 14, 18)
def palette(age):
    # newborn = bright cyan-white; older = settling teal/blue
    if age == 1:
        return (224, 255, 252)
    if age == 2:
        return (120, 230, 220)
    if age <= 4:
        return (52, 196, 190)
    if age <= 8:
        return (36, 150, 170)
    return (30, 110, 150)


def render(frames, path, scale=14, pad=1, hold_last=8):
    imgs = []
    age = [[0] * W for _ in range(H)]
    for grid in frames:
        for r in range(H):
            for c in range(W):
                age[r][c] = age[r][c] + 1 if grid[r][c] else 0
        img = Image.new("RGB", (W * scale, H * scale), BG)
        px = img.load()
        for r in range(H):
            for c in range(W):
                if grid[r][c]:
                    col = palette(age[r][c])
                    for y in range(r * scale + pad, (r + 1) * scale - pad):
                        for x in range(c * scale + pad, (c + 1) * scale - pad):
                            px[x, y] = col
        imgs.append(img)
    imgs += [imgs[-1]] * hold_last
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=110, loop=0, optimize=True)
    return path


if __name__ == "__main__":
    print(f"building {W}x{H} circuit (C compile of ~{W*H*90} gates)...")
    drv = LifeDriver(str(HERE / "life32.shdl"), W, H)
    seed = build_seed()
    drv.load(seed)
    assert drv.read() == seed, "seed load mismatch"

    frames = [drv.read()]
    ref = seed
    mismatches = 0
    for g in range(1, GENS + 1):
        ref = ref_step(ref)
        drv.gen()
        hw = drv.read()
        if hw != ref:
            mismatches += 1
        frames.append(hw)
    drv.close()
    print(f"ran {GENS} generations; mismatches vs reference: {mismatches}")
    out = render(frames, str(HERE / "life.gif"))
    print("wrote", out)
