# SR16 — a 16-bit RISC CPU in SHDL

A load-store RISC processor built entirely from SHDL primitive gates:
8×16-bit registers (R7 = SP), 256 words of unified in-circuit RAM, Z/N/C/V
flags with conditional branches, stack + CALL/RET, a multi-cycle FSM
(FETCH/EXEC/MEMRD/HALTED) and a two-phase non-overlapping clock.

**`ISA.md` is the specification of record** — instruction set, formats,
microarchitecture, clocking protocol and top-level pins.

## Layout

| File | Contents |
|------|----------|
| `seq.shdl` | MSFFE master-slave flip-flop, RegE register (two-phase) |
| `parts.shdl` | wide muxes, decoders, +1 incrementer, OR-reduce |
| `alu.shdl` | 16-bit ALU (ADD/SUB/ADC/AND/OR/XOR/MOV/NOT/shifts) + flags |
| `regfile.shdl` | 8×16 register file, 2 read / 1 write port |
| `ram.shdl` | 256×16 RAM, phi1-strobed write, combinational read tree |
| `control.shdl` | FSM + instruction decode → control word |
| `sr16.shdl` | top level: datapath + control + DMA loader + debug pins |
| `sr16tools/` | `asm.py` assembler · `golden.py` architectural model · `driver.py` ctypes driver |

Power-on state flows entirely from the shared `examples/srLatch.shdl` seeds
(all visible state reads 0; see the latch's docstring for why a seeded
feedback loop must own every gate in it).

## Running a program

```sh
# flatten + compile the circuit (once)
uv run shdl-flatten examples/CPU/sr16.shdl -I examples -o /tmp/sr16.bshdl
uv run shdlc /tmp/sr16.bshdl -o /tmp/sr16.dylib

# assemble + run
cd examples/CPU
uv run python -m sr16tools.driver /tmp/sr16.dylib program.s
```

## Verification

`tests/cpu/` proves the CPU against `sr16tools/golden.py` (itself checked
line-by-line against ISA.md — on any disagreement the document wins):

- **component tests** — seq/parts/ALU/regfile/RAM driven at the pins;
- **power-on tests** — every stateful layer holds its reset state at many
  tick offsets (regression net for the SRLatch seed bug);
- **per-instruction lockstep** — every opcode, funct, condition and reserved
  encoding, with full architectural state + cycle cost compared after every
  instruction;
- **program tests** — Fibonacci, array sum, GCD, recursive CALL/stack,
  memcpy, compared in lockstep plus hand-derived results;
- **margin guard** — doubling the driver's clock budgets leaves the
  architectural trace bit-identical.

```sh
uv run pytest tests/cpu        # full CPU suite (builds the circuit once)
```
