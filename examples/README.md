# SHDL Examples

A graded tour of the language, from a single gate to a parameterized ALU.
Each file is a self-contained module; read them in order — every example
introduces one new language feature and builds on the ones before it.

Compile any example to Base SHDL from the repo root:

```sh
uv run shdl-flatten examples/alu.shdl                    # uses the `top`-marked component
uv run shdl-flatten examples/stdgates.shdl --top NAND    # pick a component explicitly
uv run shdl-flatten examples/adderN.shdl -o adderN.bshdl # write to a file
```

Imports resolve relative to the importing file, so the directory works as-is
with no `-I` flags.

## Learning path

| #  | File               | Top component | Introduces |
|----|--------------------|---------------|------------|
| 01 | `inverter.shdl`    | `Inverter`    | Components, ports, instances, `connect` |
| 02 | `stdgates.shdl`    | *(library)*   | Derived gates (NAND/NOR/XNOR); a multi-component library module |
| 03 | `mux2.shdl`        | `Mux2`        | Intermediate gates, fan-out |
| 04 | `fullAdder.shdl`   | `FullAdder`   | Hierarchy: components instantiating components; the `top` marker |
| 05 | `busOps.shdl`      | `SignExtend`  | Multi-bit ports, slices `S[a:b]`, concatenation `{hi, lo}`, replication `N{...}` |
| 06 | `adder8.shdl`      | `Adder8`      | Generators `>i[N]{...}`, `{expr}` substitution, imports (`use`) |
| 07 | `adderN.shdl`      | `AdderN<N=8>` | Parameters with defaults; `when`/`else` boundary folding |
| 08 | `add100.shdl`      | `Add100`      | Named constants as sources; per-bit constant references |
| 09 | `muxN.shdl`        | `Mux4N<N=8>`  | Passing parameters down the hierarchy |
| 10 | `comparator.shdl`  | `EqualN<N=8>` | Reduction chains (XNOR + AND-reduce) |
| 11 | `srLatch.shdl`     | `SRLatch`     | Feedback/state under the unit-delay model; `init` power-on seeds |
| 12 | `dLatch.shdl`      | `DLatch`      | Composing sequential components |
| 13 | `registerN.shdl`   | `RegisterN<N=8>` | Generators over user-defined sequential components |
| 14 | `ringClock.shdl`   | `RingClock<N=8>` | Oscillators: feedback rings as clocks |
| 15 | `alu.shdl`         | `ALU<N=8>`    | Capstone: everything combined |

## Conventions the examples follow

- **`PascalCase`** component names; short free-form port names (`A`, `Cin`, `clk`).
- **Bit 1 is the LSB** everywhere — ports, slices, constants, generators (§6.2).
- One **`top`-marked** component per runnable module makes single-file
  compilation self-describing; pure library modules (`stdgates`) have none.
- **Parameters carry defaults** (`<N = 8>`) so parameterized components can be
  marked `top` and compiled directly.
- **`when`/`else` folds boundary stages into the loop** (first carry-in, chain
  heads) instead of hoisting copies of the body outside the generator (§7.7.1).
- **`init` seeds state, never structure** — used only where the power-on value
  matters (the SR latch), left out of purely combinational circuits.
- Docstring-style `"""..."""` comments head each module; `#` comments annotate
  individual connections.
