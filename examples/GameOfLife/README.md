# Conway's Game of Life — in SHDL gates

A fully gate-level Game of Life: every cell's next state is computed by
real AND/OR/NOT/XOR gates and stored in a master-slave flip-flop on a
two-phase clock. No software shortcuts — the rule lives in silicon.

This is a `shdl` project: the adders come from the CCircus package index
(`arith`), the flip-flop is a local module, and `shdl.toml` + `shdl.lock`
pin the whole thing.

## Files
- `shdl.toml`   — the project manifest; `arith` is the one registry dependency.
- `cell.shdl`   — one Life cell: 8-neighbour popcount (arith adder tree) +
                  B3/S23 rule (equality comparators) + load mux + MSFFE flip-flop.
- `msffe.shdl`  — local module: SRLatch → DLatch → MSFFE master-slave storage.
- `gen_life.py` — emits `life32.shdl`, a W×H toroidal grid of cells (wrap-around
                  neighbours, one output/seed port per row to stay under the
                  64-bit ABI ceiling).
- `validate.py` — two-phase clock driver + an independent Python Life model;
                  the hardware is checked against it every generation.
- `gol_render.py` — seeds gliders + a pulsar, runs 120 generations, and paints
                  the animated GIF (`life.gif`).

## Run it
```sh
# with pyshdl >= 1.1.0 installed (pip install pyshdl):
shdl install           # vendor arith (+ gates) from the index
shdl build             # flatten + compile life32.shdl (top: Life)
shdl test              # gate-level Cell tests: seed load, B3/S23, overcrowding
python3 validate.py    # 8x8 hardware vs the Python reference, 12 generations
python3 gol_render.py  # 32x32, 120 generations, writes life.gif
```

## How a generation advances
Each cell holds 1 bit in a master-slave flip-flop. The harness pulses a
non-overlapping two-phase clock (settle → Phi1 → gap → Phi2 → gap); on each
clock every cell simultaneously latches `Load ? Seed : nextState`, so the whole
grid steps one generation at once — exactly as synchronous hardware would.

Result: 1024 cells, 120 generations, **0 mismatches** against the reference model.
