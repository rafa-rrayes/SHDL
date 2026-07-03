# Conway's Game of Life — in SHDL gates

A fully gate-level Game of Life: every cell's next state is computed by
real AND/OR/NOT/XOR gates and stored in a master-slave flip-flop on a
two-phase clock. No software shortcuts — the rule lives in silicon.

## Files
- `cell.shdl`   — one Life cell: 8-neighbour popcount (adder tree) +
                  B3/S23 rule (equality comparators) + load mux + MSFFE flip-flop.
- `gen_life.py` — emits `life.shdl`, a W×H toroidal grid of cells (wrap-around
                  neighbours, one output/seed port per row to stay under the
                  64-bit ABI ceiling).
- `validate.py` — two-phase clock driver + an independent Python Life model;
                  the hardware is checked against it every generation.
- `gol_render.py` — seeds gliders + a pulsar, runs 120 generations, and paints
                  the animated GIF (`life.gif`).
- `*.shdl` deps — srLatch, dLatch, fullAdder, seq (MSFFE/RegE).

## Run it
```sh
# from a checkout of github.com/rafa-rrayes/SHDL with PySHDL importable:
python3 gen_life.py 32 32 life32.shdl
python3 gol_render.py            # builds with gcc, validates, writes life.gif
```

## How a generation advances
Each cell holds 1 bit in a master-slave flip-flop. The harness pulses a
non-overlapping two-phase clock (settle → Phi1 → gap → Phi2 → gap); on each
clock every cell simultaneously latches `Load ? Seed : nextState`, so the whole
grid steps one generation at once — exactly as synchronous hardware would.

Result: 1024 cells, 120 generations, **0 mismatches** against the reference model.
