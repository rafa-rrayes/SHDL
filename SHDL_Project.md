# The SHDL Project

*The official definition of the SHDL project: vision, architecture, components, and roadmap.*
*github.com/rafa-rrayes/SHDL*

---

## 1. What SHDL Is

SHDL (Simple Hardware Description Language) is a minimalist language and toolchain for describing, simulating, debugging, and deploying digital circuits built entirely from logic gates. Its guiding principle is fidelity to the hardware: **every circuit is ultimately a netlist of single-bit primitive gates**, and every convenience in the language exists only to write that netlist more concisely. There are no behavioral abstractions, no implicit state elements, and no synthesizable arithmetic operators — only gates, wires, and mechanical ways to repeat them. What you write is what is built.

This makes SHDL fundamentally an **educational and exploratory** system. A learner builds a NAND from primitives, a latch from cross-coupled gates, a register from latches, an ALU from adders, and ultimately a working processor — never leaving the gate level, always able to see exactly what their design becomes and how signals propagate through it one gate at a time.

### 1.1 The Defining Principle: Gate-Level Fidelity

SHDL simulates each gate the way a real gate behaves. On each simulation cycle, every gate simultaneously computes its output from the values present on its inputs at the end of the previous cycle — **unit propagation delay, one gate-level per cycle**. A combinational result is not visible instantly; it ripples forward one level per cycle. A 16-bit ripple-carry adder takes many cycles, and the carry can be *watched* advancing through the chain. A carry-lookahead adder settles in fewer cycles than a ripple-carry adder — propagation depth is an observable, comparable design property, exactly as in real hardware.

This is a deliberate, non-negotiable decision. The toolchain must never collapse combinational propagation into a single step (for example, by evaluating gates in topological order to settle instantly). Doing so would be faster but would erase the gate-level behavior SHDL exists to expose. Convenience operations like `settle()` live *above* the simulation as driver helpers; they never change the model itself.

### 1.2 Determinism and State

Every wire has a defined value at cycle 0 — 0 by default, or a chosen value via an optional `init` block. This makes the model fully deterministic for *all* circuits, including those with feedback: the same inputs always yield the same trace. Latches, registers, and oscillators arise naturally from feedback loops of ordinary gates; state and timing need no special syntax.

---

## 2. The Pipeline

SHDL is organized around a clean separation between the language people write and the intermediate representation tools consume. Nothing downstream ever reads SHDL directly — everything consumes **Base SHDL**.

```
  SHDL  (Expanded SHDL — what you write)
  ┌────────────────────────────────────────┐
  │  components, hierarchy, parameters,     │
  │  multi-bit ports, generators,           │
  │  conditionals, slices, concatenation,   │
  │  constants, init, imports               │
  └────────────────────────────────────────┘
       │
       ▼
  ┌──────────────┐
  │  Flattener   │   6 sequential phases
  └──────────────┘
       │
       ▼
  Base SHDL  (intermediate representation)
  ┌──────────────────────────────────┐
  │  Structural Core                 │  pure single-bit primitive-gate netlist
  │  + Metadata Section (JSON)       │  port groups, hierarchy, source maps,
  │                                  │  timing, constants, init, stats, docs
  └──────────────────────────────────┘
       │
       ├──▶  SHDLC Compiler  ──▶  C  ──▶  Shared Library
       ├──▶  Debugger (SHDB)
       ├──▶  Python Driver (PySHDL)
       └──▶  Alternative backends (Verilog, BLIF, Yosys, hardware, ...)
```

### 2.1 The Two Languages

**SHDL (Expanded SHDL)** is the authoring language. It offers reusable, parameterized hierarchical components, multi-bit ports, generators with compile-time conditionals for repetitive structure, bit slices and concatenation, named constants, optional initial state, and imports — everything needed to keep real designs compact and readable. It is fully specified in `shdl.md`.

**Base SHDL** is the intermediate representation. Its structural core describes the circuit using only single-bit wires and the six primitive gates — no widths, no indexing, no hierarchy, no parameters. Alongside it travels a JSON **metadata section** carrying everything the tooling needs to recover the high-level view (multi-bit port groupings, the pre-flattening hierarchy, source-location maps, timing/depth information, constant origins, initial-state seeds, statistics, and documentation). It is fully specified in `base_shdl.md`.

The relationship between the two is exact and total: every SHDL feature has a defined Base SHDL expansion, and a circuit using none of the high-level features is already valid Base SHDL.

### 2.2 The Six Primitives

Base SHDL has exactly six primitive types, and they are the only types that survive flattening: the logic gates `AND`, `OR`, `NOT`, `XOR` (each mapping to a single C bitwise operator), and the power pins `__VCC__` (constant 1) and `__GND__` (constant 0). Every other gate — NAND, NOR, XNOR, and all user components — is an ordinary composition that is inlined during flattening.

### 2.3 The Flattener (Complete)

The flattener lowers SHDL to Base SHDL in six sequential phases, each fully completing before the next: lexical stripping (comments and imports), monomorphization (binding parameters and specializing parameterized components), generator and conditional expansion, expander expansion (slices and concatenation into single-bit connections), constant materialization (referenced constant bits into power pins), and hierarchy flattening (inlining components, prefixing names, extracting metadata). The flattening guarantees functional equivalence, name uniqueness, full resolution to the six primitives, and determinism.

---

## 3. The Compiler (SHDLC)

SHDLC takes Base SHDL and generates C code that, compiled by clang/gcc into a shared library, simulates the circuit. The compiled artifact must be **correct** (cycle-accurate, functionally equivalent to the source), **faithful** (level-by-level propagation, never collapsed), **fast** (per-cycle overhead in nanoseconds), and **interoperable** (a stable C ABI any language can call, plus state observable by external tools).

### 3.1 The Simulation Model in C

The generated code implements the unit-delay, one-level-per-cycle model via a **two-buffer compute-commit cycle**: every gate's output is held in a *current* and a *next* buffer; to advance one cycle, each gate is computed by reading its inputs from the current buffer and writing its result to the next buffer; after all gates are computed, the buffers swap. Because every gate reads only the immutable current buffer, evaluation order within a cycle is irrelevant — which makes feedback work for free and makes the model trivially parallelizable in later phases.

### 3.2 The ABI

The release build exposes `reset()`, `poke(signal, value)`, `peek(signal)`, and `step(cycles)`, using user-facing multi-bit signal names from the `ports` metadata. The debug build adds gate-level introspection: `peek_gate`, `peek_gate_prev`, `get_cycle`, and gate enumeration, alongside a `.shdb` metadata file. Both builds produce functionally identical simulation results.

### 3.3 The State Region

All simulation state lives in a single, contiguous, self-describing memory region with a compile-time-fixed, versioned layout. This is the substrate that makes same-process direct access, shared-memory observation, cross-process driving, and future parallel evaluation all additive rather than rewrites. The function-call ABI is always the primary interface; the State Region is what lets everything else attach without disturbing the simulation.

### 3.4 Build Strategy: Correct First, Fast Last

SHDLC is built in versions. **V1 is deliberately simple and unoptimized**: parse Base SHDL, evaluate each gate one at a time using the two-buffer cycle, generate readable C, expose the release ABI. It exists to be provably correct. Subsequent versions add the debug build, then performance tiers — type-based bit-packing, then PDEP/PEXT-accelerated gather on capable hardware, then SIMD, then multi-threading — each validated bit-exactly against V1 and the conformance suite. **Compiler optimization is intentionally the last major work in the project**, because it is the part most able to introduce subtle correctness regressions and the part that benefits most from a mature test corpus.

---

## 4. The Ecosystem

Around the core pipeline sits a full ecosystem of tools. They are described here by role; the build sequence is in §5.

### 4.1 PySHDL — the Python Driver

The keystone of the ecosystem. PySHDL loads a compiled shared library and wraps the ABI in an ergonomic Python interface (`poke`, `peek`, `step`, context managers, dict-style access). It reads the `ports`, `timing`, and `init` metadata to provide multi-bit access, power-on reset, and a `settle()` convenience that advances exactly `max_depth` cycles for combinational circuits (and is disabled, by design, for circuits with feedback). Almost every higher tool talks to circuits *through* PySHDL.

### 4.2 SHDB — the Debugger

A gate-level debugger built on PySHDL and the compiler's debug build. It offers breakpoints, watchpoints, waveform capture, hierarchy navigation, scope-aware signal inspection, source-level mapping, and constant/initial-state display — all powered by the metadata (`hierarchy`, `source_map`, `constants`, `monitors`, `init`) and the debug ABI (`peek_gate`, `peek_gate_prev`, `get_cycle`).

### 4.3 The Standard Library (stdlib)

A growing collection of reusable SHDL components — derived gates (`NAND`, `NOR`, `XNOR`), multiplexers, adders, registers, shifters, ALUs, and more — shipped as `.shdl` source. It is mostly independent of the binary toolchain but is the source of fixtures that every other tool tests against.

### 4.4 The Testbench Runner

A format (`.shtb`) for declaring input vectors and expected outputs, executed in batch against a compiled circuit. It makes circuits self-verifying and is the backbone of automated testing and CI.

### 4.5 The Performance Profiler

A tool that measures simulation throughput and identifies bottlenecks, using PySHDL and meaningful circuits from the stdlib. It guides — and validates — the compiler's optimization work.

### 4.6 Alternative Backends

Backends that read Base SHDL and emit other formats: **structural Verilog** (unlocking the entire Verilog ecosystem and independent cross-validation against Verilator), **BLIF** (unlocking formal equivalence checking and logic minimization via ABC), and **Yosys JSON** (unlocking the open-source FPGA flow). These depend only on the flattener, not on SHDLC, and can be built in parallel with the simulation tools. They are also gateways: BLIF to the equivalence checker, Yosys JSON to FPGA bitstreams.

### 4.7 Verification Tools

A family built on the backends and testbench runner: a **formal equivalence checker** (prove two SHDL circuits compute the same function — e.g., that a carry-lookahead adder matches a ripple-carry adder), **combinational-loop detection** as a standalone lint, **coverage** analysis (which gates and paths a test actually exercises), and a **fuzzer** for surfacing undriven nets and unexpected oscillation.

### 4.8 Visualization

A **VCD waveform export** (the cheapest high-value item — emit from SHDB/PySHDL and gain GTKWave/Surfer support for free), an interactive **schematic viewer** that renders a circuit as a gate diagram from the hierarchy and source-map metadata, a **hierarchy explorer** for drilling into nested instances, and an animated **propagation view** that showcases the one-level-per-cycle model.

### 4.9 The Web Playground

SHDL compiled to WebAssembly with an in-browser editor and live simulation, shareable by URL. It removes all installation friction and is the single biggest reach multiplier for an educational language.

### 4.10 Hardware Bridge

The most distinctive frontier: targets that deploy a circuit to a physical board (Arduino, ESP, Raspberry Pi) so the user interacts with their gate-built circuit via the actual pins. Extensions include a **logic-analyzer mode** (capture real pin states back into a SHDL waveform), **hardware-in-the-loop testing** (run a testbench against the deployed circuit), and the natural endgame, an **FPGA bitstream target** via the Yosys → nextpnr flow, so SHDL designs run as real reconfigurable hardware.

### 4.11 Authoring Tools

A **language server (LSP)** for editor support everywhere (autocomplete on component ports, go-to-definition across imports, inline width-mismatch diagnostics, hover showing flattened gate counts), a **formatter** (`shdlfmt`), a **documentation generator**, an **importer** (Verilog/BLIF → SHDL, to bring existing netlists into the ecosystem), and an interactive **tutorial**.

### 4.12 Distribution and Glue

A **unified CLI** (`shdl build`, `shdl sim`, `shdl test`, `shdl deploy`), a **package manager / registry** for sharing components (`shdl add alu`), and a **CI action** that compiles, runs testbenches, and checks equivalence on every push.

### 4.13 The Conformance Suite

A versioned corpus of `.shdl` files paired with known-correct Base SHDL and known cycle-by-cycle traces. Everything validates against it. It is the safeguard against regressions and the ground truth that lets the flattener and compiler be refactored or reimplemented with confidence. It is built immediately after SHDLC V1 and maintained forever.

### 4.14 SHDL Station

The culminating vision: an integrated application that brings the editor (LSP), simulation (PySHDL), debugging (SHDB), visualization (schematic and waveform), and testing (testbench runner) into a single environment — everything needed to work with SHDL in one place. It is, by definition, a shell over mature parts, and so it comes last.

---

## 5. Build Sequence

The ecosystem has a clear dependency structure. The layers below indicate what must exist before what; items within a layer marked "parallel" can be built concurrently.

### Layer 0 — Core (done / in progress)

1. **Flattener** — *complete.*
2. **SHDLC V1** — *in progress.* Simple, scalar, unoptimized; release ABI.
3. **Conformance Suite** — build immediately after V1. Depends only on the flattener and V1. The validation foundation for everything that follows.

### Layer 1 — Consumers of a compiled circuit

4. **PySHDL** — the driver; the keystone. Depends on SHDLC V1's library and ABI.
5. **stdlib** *(parallel)* — `.shdl` source; depends on the flattener and conformance suite. Build early; it supplies fixtures to everyone.
6. **SHDLC debug build** — adds the debug ABI and `.shdb`. Prerequisite for SHDB.
7. **SHDB** — the debugger. Depends on PySHDL + the debug build.

### Layer 2 — Verification & analysis (depend on PySHDL + stdlib)

8. **Testbench runner** *(build early)* — backbone of automated testing and CI.
9. **Performance profiler** — needs PySHDL and real circuits.
10. **Alternative backends** *(parallel track off the flattener)* — Verilog, BLIF, Yosys JSON. Independent of SHDLC.
11. **Equivalence checker** — depends on the BLIF backend (ABC). Plus combinational-loop lint, coverage, fuzzer.

### Layer 3 — Visualization (depend on metadata + PySHDL)

12. **VCD waveform export** *(cheapest high-value item)*.
13. **Schematic viewer** — reads hierarchy + source-map metadata.
14. **WASM build + web playground** — depends on SHDLC compiling through Emscripten; high effort, high reach.

### Layer 4 — Hardware bridge

15. **MCU pin-interaction targets** (Arduino, ESP, Pi) — depend on PySHDL's interaction model and the C codegen.
16. **FPGA bitstream target** — depends on the Yosys backend (Layer 2).

### Layer 5 — Glue & distribution

17. **Unified CLI, LSP, formatter, documentation generator, importer, package registry, CI action** — wrap the tools they orchestrate; come once those exist.

### Layer 6 — Integration

18. **SHDL Station** — integrates editor, simulation, debugging, visualization, and testing into one app. Last by definition.

### Layer 7 — Optimization (intentionally last)

19. **SHDLC performance tiers** — bit-packing, PDEP/PEXT gather, SIMD, multi-threading — each validated bit-exactly against V1 and the conformance suite.

### Critical Path

The spine of the project runs: **SHDLC V1 → Conformance Suite → PySHDL → SHDLC debug build → SHDB**, with **stdlib** and the **testbench runner** built in parallel as early as possible because they are the fixtures-and-testing infrastructure everyone leans on. **Backends** form a parallel track directly off the flattener that branches into verification (BLIF → equivalence) and hardware (Yosys → FPGA). **Compiler optimization** stays last, validated the whole way by the conformance suite.

---

## 6. Project Principles

These principles govern every part of the project.

**Fidelity over speed.** The gate-level, one-level-per-cycle model is sacred. No tool may collapse propagation or hide the structure that SHDL exists to expose. Speed is pursued only in ways that preserve the model exactly.

**One IR, many consumers.** Base SHDL is the single contract between the front-end and everything else. The flattener does the hard work once; backends, compilers, debuggers, and viewers are thin consumers of a flat single-bit netlist plus metadata. New targets are added without touching the front-end.

**Correctness before performance.** A reference interpreter defines ground truth. Every generated simulation is validated bit-exactly against it, cycle by cycle. Optimizations make correct code faster; they never alter observable semantics. The conformance suite makes this enforceable forever.

**Build it once.** Foundational decisions — the metadata contract, the State Region layout, the two-buffer model — are designed so that future capabilities attach additively rather than forcing rewrites. The early simplicity is a deliberate investment in never having to start over.

**Determinism everywhere.** The same input yields the same output: byte-identical Base SHDL, byte-identical generated C, identical simulation traces, on every platform and at every optimization level.

**Education is the mission.** Every choice favors a learner building hardware from first principles: readable syntax, visible structure, observable propagation, deployment to real pins, and a path from a single NAND gate all the way to a working processor.

---

## 7. Status Summary

| Component                     | Layer | Status        |
|-------------------------------|-------|---------------|
| Flattener (SHDL → Base SHDL)  | 0     | Complete      |
| SHDLC V1 (Base SHDL → C)      | 0     | In progress   |
| Conformance suite             | 0     | Planned (next)|
| PySHDL driver                 | 1     | Planned       |
| stdlib                        | 1     | Planned       |
| SHDLC debug build             | 1     | Planned       |
| SHDB debugger                 | 1     | Planned       |
| Testbench runner              | 2     | Planned       |
| Performance profiler          | 2     | Planned       |
| Backends (Verilog/BLIF/Yosys) | 2     | Planned       |
| Verification tools            | 2     | Planned       |
| Visualization (VCD/schematic) | 3     | Planned       |
| Web playground (WASM)         | 3     | Planned       |
| Hardware bridge (MCU/FPGA)    | 4     | Planned       |
| Glue & distribution (CLI/LSP) | 5     | Planned       |
| SHDL Station                  | 6     | Planned       |
| SHDLC optimization tiers      | 7     | Planned (last)|

---

## 8. Reference Documents

| Document                      | Defines                                              |
|-------------------------------|------------------------------------------------------|
| `shdl.md`                     | The SHDL (Expanded SHDL) language — full specification |
| `base_shdl.md`                | The Base SHDL IR — structural core + metadata        |
| `SHDL_Compiler_Goals.md`      | SHDLC goals, ABI, State Region, correctness          |
| `SHDL_Project.md`             | This document — the official project definition      |

This document is the authoritative overview of the SHDL project. Where it summarizes a component, the component's own specification (where one exists) governs the details.