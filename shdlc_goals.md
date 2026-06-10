# The SHDL Compiler: Goals and Requirements

*What the compiler must produce, why, and to what standard — without prescribing how.*
*Companion to the Base SHDL Specification.*

---

## 1. The Compiler's Mission

The SHDL compiler (SHDLC) takes a Base SHDL file as input and produces a **compiled simulation artifact** — a shared library (`.so`, `.dylib`, or `.dll`) and, in debug mode, a `.shdb` metadata file — that simulates the described circuit.

The compiled artifact must satisfy four properties simultaneously:

1. **Correctness.** The simulation must be cycle-accurate and functionally equivalent to the circuit described in Base SHDL.
2. **Fidelity.** The simulation must behave like real hardware at the gate level: signals propagate through one level of gates per cycle. This is a defining feature of SHDL, not a limitation to be optimized away.
3. **Performance.** The simulation must run as fast as the fidelity model allows. Per-cycle overhead is measured in nanoseconds, not microseconds.
4. **Interoperability.** The compiled library must expose a stable C ABI that any language, process, or tool can use without friction, and its internal state must be observable by external tools without slowing the simulation down.

These properties are equally important. A fast simulator that settles combinational logic instantly would betray SHDL's purpose: watching gates work the way real gates work.

---

## 2. The Simulation Model

### 2.1 Cycle-Accurate, 2-State

**Cycle-accurate** means the simulation advances in discrete, uniform time steps called **cycles**. Each call to `step(1)` advances the simulation by exactly one cycle. There is no continuous time, no nanosecond delays, no event-driven scheduling. One cycle = one evaluation of the gate network.

**2-state** means every signal is either 0 or 1 at all times. There is no X (unknown) or Z (high-impedance). After `reset()`, all state is 0. The simulation is deterministic at every point.

### 2.2 Level-by-Level Propagation — A Defining Principle

SHDL simulates each gate **like a real physical gate**. In a single cycle, signals propagate through exactly **one level of gates**:

- A single AND gate produces correct output after `step(1)`.
- A circuit with combinational depth N requires `step(N)` for outputs to fully reflect the inputs.
- A 16-bit ripple-carry adder takes ~32 steps; the carry can be *watched* rippling through the chain.
- A carry-lookahead adder settles in fewer steps than a ripple-carry adder — propagation depth is an observable, comparable design property, exactly as in real hardware.

This is a deliberate, central design decision. The compiler **must not** collapse combinational propagation into a single cycle (e.g., by evaluating gates in topological order within one tick). Doing so would erase the gate-level behavior that SHDL exists to expose. The `timing.max_depth` metadata exists so that *drivers* can offer a `settle()` convenience (simply `step(max_depth)`) — the convenience lives above the simulation, never inside it.

### 2.3 The Compute-Commit Contract

In a single cycle:

1. Read the current input values (set by `poke()`).
2. Read the current internal state (every gate's output from the previous cycle).
3. For every gate, compute the new output **using only values from steps 1–2**.
4. Commit all new gate outputs **simultaneously**.

This is a synchronous, parallel evaluation model. No gate sees another gate's same-cycle update. Consequences:

- **Determinism regardless of evaluation order.** Since all reads come from the immutable previous state, gates can be evaluated in any order — or in parallel — with identical results.
- **Feedback needs no special handling.** A latch or oscillator simply works: each gate in the loop reads the previous cycle's values and the loop advances one gate level per cycle.
- **Every gate's output is persistent state.** Because every gate reads previous-cycle values, every gate's output must survive across cycles (unlike settling simulators, where combinational values can be transient).

### 2.4 Reset Semantics

After `reset()`: every gate output is 0, every input is 0, every output is 0, the cycle counter is 0. Constants (`__VCC__`/`__GND__`) take effect on the first evaluation cycle after reset; they are not pre-loaded.

---

## 3. The Compiled Library Interface

### 3.1 Release Build ABI

```c
void     reset    (void);
void     poke     (const char *signal, uint64_t value);
uint64_t peek     (const char *signal);
void     step     (int cycles);
```

**`poke(signal, value)`** — Sets an input by its **user-facing name** from the `ports` metadata (e.g., `"A"`, not `"A_1_"`). Bit 0 of `value` = bit 1 of the port (LSB). The value is masked to the port's width. After a poke, cached outputs are invalidated. Unknown signal names report an error and do nothing.

**`peek(signal)`** — Reads any input or output by user-facing name. For outputs, if the circuit has not been evaluated since the last `poke()`, `peek()` triggers exactly one evaluation cycle before returning, so alternating `poke()`/`peek()` always returns consistent results. Returns the signal's bits packed from the LSB of a `uint64_t`.

**`step(cycles)`** — Advances the simulation by exactly `cycles` evaluation cycles. `step(0)` does nothing.

**`reset()`** — Returns the simulation to its initial all-zero state.

### 3.2 ABI Design Constraints

- **String-based lookup only on the cold path.** `poke()`/`peek()` accept strings for universal FFI compatibility; `step()` performs no string operations whatsoever.
- **Global state, single instance.** One simulation context per loaded library copy. Multiple simultaneous circuits = multiple library loads.
- **No caller-managed memory.** All state is internal. No alloc/free pairs cross the ABI.
- **No callbacks.** The library never calls into the caller — safe from any language's FFI.
- **No thread-safety guarantees.** Concurrent calls from multiple threads are the caller's responsibility to avoid.
- **Primitive C types only** in signatures: `void`, `int`, `uint64_t`, `const char *`, `size_t`, `uint8_t`.

### 3.3 Debug Build ABI

Everything from release, plus:

```c
uint64_t peek_gate      (const char *gate_name);
uint64_t peek_gate_prev (const char *gate_name);
uint64_t get_cycle      (void);
size_t   get_num_gates  (void);
int      get_gate_info  (size_t index,
                         const char **name,
                         uint8_t *type,
                         uint8_t *chunk,
                         uint8_t *lane);
```

**`peek_gate(name)`** — Reads any internal gate's current output by its flattened name (e.g., `"fa1_x1"`). This is what makes SHDB possible.

**`peek_gate_prev(name)`** — Reads the gate's output from the **previous** cycle. Essential for watchpoints ("did this gate change?") without the debugger maintaining a shadow copy. Because SHDL's simulation model already double-buffers all gate state, this should be nearly free.

**`get_cycle()`** — Total evaluation cycles since the last `reset()`.

**`get_num_gates()` / `get_gate_info()`** — Enumerate the gate table: name, type code, and position in the state layout.

Gate type encoding: 0 = XOR, 1 = AND, 2 = OR, 3 = NOT, 4 = `__VCC__`, 5 = `__GND__`.

### 3.4 Debug Build Requirements

Debug builds must be **functionally identical** to release builds — same inputs, same outputs, same cycle behavior. The only differences are the availability of introspection and its (bounded) overhead:

- Gate name lookup should be O(1) (hash table) for circuits beyond ~1000 gates.
- The evaluation path itself (`step`) must remain fast; debug overhead concentrates in the introspection functions and bookkeeping, not in gate evaluation.

---

## 4. The State Region — Interoperability Foundation

All simulation state — inputs, outputs, every gate's current and previous output, the cycle counter, status flags — must live in **one contiguous, self-describing memory region** with a fixed, compile-time-determined layout:

- The layout begins with a versioned header (magic number, layout version, component identity, section offsets).
- The layout is documented in the `.shdb` file so external tools can interpret the region.
- The layout must not change at runtime, and must be identical regardless of how the region is allocated.

This single requirement is what makes the following possible **without ever changing the simulation code**:

1. **Same-process direct access** — drivers can resolve a signal's offset once and bypass string lookup in hot loops.
2. **Shared-memory observation** — the region can optionally be backed by a named shared memory segment; external processes (waveform viewers, monitors) map it read-only and observe the live simulation with zero overhead to the simulation itself.
3. **Cross-process driving** — atomic status flags in the region allow another process to request steps without sockets.
4. **Future parallel evaluation** — the compute-commit model plus a stable double-buffered layout make multi-threaded and SIMD evaluation purely internal changes to `tick()`.

The function-call ABI (Section 3) is always the primary, default interface. The State Region is the substrate that makes everything else additive.

---

## 5. Performance Expectations

### 5.1 Targets

- **Small circuits (< 100 gates):** millions of cycles per second; bottleneck should be call overhead, not evaluation.
- **Medium circuits (100–10,000 gates):** hundreds of thousands to millions of cycles per second; state fits in L1/L2 cache.
- **Large circuits (10,000–1,000,000 gates):** thousands to hundreds of thousands of cycles per second; memory layout becomes critical.

The goal is that interactive debugging feels instantaneous and exhaustive testing of educational-scale circuits completes in seconds.

### 5.2 Where Performance Comes From

- No interpretation: the gate network is hardcoded into C, not traversed via data structures.
- The C compiler's optimizer (`-O3`): register allocation, scheduling, constant folding.
- CPU-native bitwise operations: each gate maps to `&`, `|`, `^`, or `~`.
- Bit-level parallelism where profitable: many independent same-type gates evaluated per instruction.
- Zero runtime allocation: all state is fixed-size, laid out at compile time.

### 5.3 Hard Rules for the Hot Path

`step()`/`tick()` must never: allocate memory, perform string operations, branch on signal values (branchless evaluation), or copy large state unnecessarily (buffer swaps are pointer swaps).

### 5.4 An Honest Bound

Level-by-level fidelity has an inherent cost: every gate's output must pass through memory every cycle (it is persistent state by definition). No implementation can avoid this traffic; the compiler's job is to make it as cheap as the model allows — compact layout, cache-friendly grouping, and wide operations where they genuinely pay.

---

## 6. Compilation Modes

### 6.1 Release Mode

**Input:** structural core + `ports` metadata.
**Output:** shared library exporting the release ABI.
**Characteristics:** maximum optimization; no per-gate name tables; introspection beyond ports is not available.

### 6.2 Debug Mode

**Input:** structural core + full metadata.
**Output:** shared library exporting the full debug ABI + a `.shdb` file (JSON metadata, including the State Region layout).
**Characteristics:** moderate optimization with debug info; every gate addressable by name; cycle counter and previous-cycle state exposed; functionally identical results to release.

---

## 7. Correctness Requirements

### 7.1 Functional Equivalence to the Reference

For any sequence of `reset()`, `poke()`, `step()`, `peek()` calls, the compiled simulation must return bit-exact results compared to a **reference interpreter** defined as:

1. `reset()`: all gate outputs and inputs = 0.
2. `poke(signal, value)`: store the masked value for the named input.
3. `step(1)`: for each gate, compute the new output from its inputs' values **as they were at the start of the cycle**; commit all outputs simultaneously.
4. `peek(signal)`: inputs return the stored value; outputs ensure at least one evaluation since the last poke, then return the value.

### 7.2 Determinism

Same call sequence → same results, on every platform, at every optimization level, in both build modes.

### 7.3 Feedback Correctness

Gates in feedback loops must never observe their own same-cycle updates. The compute-commit model guarantees this; the implementation must preserve it under all optimizations, including any future parallel evaluation.

---

## 8. Interoperability Requirements

- Loadable via `dlopen`/`dlsym`, `LoadLibrary`/`GetProcAddress`, Python `ctypes`, and any C FFI.
- Compiles with **clang** (primary), **gcc** (required), **MSVC** (best-effort), as valid C11; compiler-specific extensions only behind `#ifdef`.
- Targets: Linux `.so`, macOS `.dylib`, Windows `.dll`.
- Depends only on the C standard library. Self-contained.
- Only public API functions are visible symbols; everything else is `static` (no collisions when loading multiple SHDL libraries in one process).

---

## 9. Relationship to Base SHDL

**From the structural core** the compiler reads: input/output port names, gate instances (name + type), and connections — everything needed to build the evaluation logic.

**From the metadata:**

| Block        | Release           | Debug                          |
|--------------|-------------------|--------------------------------|
| `ports`      | poke/peek codegen | poke/peek codegen + `.shdb`    |
| `timing`     | optional annotation | `.shdb` (drives `settle()`)  |
| `stats`      | optional planning | `.shdb`                        |
| `hierarchy`, `source_map`, `constants`, `monitors`, `doc` | ignored | written to `.shdb` |

---

## 10. Deliverables Summary

| Build   | Artifacts                                                                  |
|---------|-----------------------------------------------------------------------------|
| Release | Shared library: `reset`, `poke`, `peek`, `step` — fully optimized           |
| Debug   | Shared library: release ABI + `peek_gate`, `peek_gate_prev`, `get_cycle`, `get_num_gates`, `get_gate_info` • `.shdb` JSON (full metadata + State Region layout) |

Both builds produce functionally identical simulation results. The only differences are performance characteristics and the availability of introspection.