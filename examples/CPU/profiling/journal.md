# SR16 profiling journal — mul.s on the compiled gate-level simulator

**Date:** 2026-06-10 · **Machine:** Apple M1 Max (8 P-cores), 32 GB · **Python:** 3.14.4 (uv) · **clang:** Apple 17.0.0
**Artifact under test:** `/tmp/sr16.dylib` (629 KB, built from `examples/CPU/sr16.shdl`, -O2 chunked codegen)
**Workload:** `programs/mul.s` — 12 × 11 by repeated addition → 74 clock cycles, halts with R3 = 132.

## Cost model (from codegen + driver, before measuring anything)

- The netlist is **42,530 gates**, 6 input ports, 14 output ports (183 output bits).
- `step(n)` = n × `tick()`; every tick re-evaluates **all 42,530 gates** (unit-delay, full re-eval,
  no event-driven shortcut) + packs all 183 output bits in `recompute_outputs()`.
- `peek(name)` = linear `strcmp` over 14 out-port names (then 6 in-port names); lazy `tick()` only if
  an input was poked since the last tick (`dirty`). `poke(name, v)` = linear `strcmp` over 6 in-ports + bit scatter.
- One driver clock (`SR16.clock`) = `step(200) + Phi1↑ step(16) + Phi1↓ step(4) + Phi2↑ step(16) + Phi2↓ step(4)`
  = **240 ticks + 4 pokes**.
- Every instruction = 2 clocks (POP/RET: 3). `step_instruction` peeks `Halted` + `State` after each clock;
  `run()` peeks `Halted` once more per instruction.
- Program load = 220 ticks/word + 200 final settle. mul.s = 7 words → 1,740 ticks.
- Predicted tick total for the stock mul.s run: 1,740 (load) + 74 × 240 = 17,760 (run) ≈ **19,500 ticks**,
  ~8.3 × 10⁸ gate evaluations end-to-end.

---
## Exp 0 — Baseline: where does the stock run's time go?

**Method:** subclass `SR16` counting every ABI call + `perf_counter` around reset/load/run/state
(`profiling/exp0_baseline.py`, stock budgets T_SETTLE=200/T_CAP=16/T_GAP=4).

| Phase | Time | Ticks | Notes |
|---|---|---|---|
| reset | 1.3 ms | 0 | memset + init seeds + recompute_outputs |
| load_program (7 words) | 41.7 ms | 1,740 | 220 ticks/word + final settle |
| run (74 clocks, 37 instr) | 410.4 ms | 17,760 | 240 ticks/clock |
| state() | 0.02 ms | 0 | 13 peeks, no ticks |
| **total (in-process)** | **453 ms** | **19,500** | CLI adds ~110 ms interpreter+import startup → 0.56 s wall |

Call counts: 392 step / 328 poke / 198 peek. Tick count matched the cost-model prediction exactly.

**Findings:**
- **One 12×11 multiply costs ~0.45 s** with the stock driver — ≈ 2.2 multiplications/second.
- Run-phase throughput: **43.3k ticks/s ≈ 23.1 µs/tick ≈ 1.84 G gate-evals/s** (0.54 ns per gate eval — the
  compiled tick is fast; the volume of ticks is the problem).
- Ticks dominate: 19,500 ticks × 23 µs ≈ 451 ms accounts for essentially the whole in-process time.
  step/poke/peek *call overhead* (920 ctypes calls) is invisible at this scale — to be quantified in Exp 1.
- 91% of ticks are clocking; 78% of each clock's ticks are the T_SETTLE=200 budget → settle margin (Exp 4)
  is the highest-leverage knob, then host overhead (Exp 5) once ticks shrink.

---
## Exp 1 — ABI microbenchmarks: what do step / peek / poke actually cost per call?

**Method:** `profiling/exp1_micro.py` — median-of-reps timing on raw `ctypes` handles;
`step(n)` for n ∈ {0,1,2,4,16,64,240,1000} + least-squares fit; poke/peek by port-scan position;
dirty-peek (forces the lazy tick); wrapper-vs-raw comparison.

```
step fit:  t = 4.2 µs + n × 23.23 µs/tick     (r² ≈ 1, perfectly linear)
poke:      345–363 ns/call  (1-bit Phi1 vs 16-bit LdData: scan position+width ≈ noise)
peek:      230–267 ns/call  (clean; Halted first in scan, R7out last: +34 ns)
peek dirty: 24.4 µs/call    (= poke 0.3µs + one full lazy tick 23.2µs + peek 0.3µs)
ctypes dispatch floor: ~250 ns/call; Python method+encode wrapper adds ~0–30 ns
```

**Findings (answers the "what's slowest: step/peek/poke" question):**
- **`step()` is everything.** One tick = **23.2 µs** = 0.546 ns × 42,530 gate evals. A stock clock
  (240 ticks) = 5.6 ms of pure C; the 4 pokes + 2 peeks around it = ~2 µs (**0.03%**).
- **peek ≈ 0.25 µs, poke ≈ 0.35 µs** — both ~70–100× cheaper than a *single* tick. Linear strcmp port
  scan is irrelevant (14 names, +34 ns worst case). Not worth optimizing.
- **A peek after a poke costs a hidden tick** (24.4 µs measured = exactly poke+tick+peek). The driver's
  call pattern never hits this (peeks happen post-step when clean), but a custom probe loop would.
- Python wrapper overhead is ≈ 0: ctypes itself is the 250 ns floor.
- Implication: total time ≈ ticks × 23.2 µs. **Reduce ticks** (settle budget, Exp 4) or **make ticks
  cheaper** (compiler work, out of scope today). Host-language tricks can't matter until a clock
  costs ~µs, i.e. ~1000× from here.

---
## Exp 2 — cProfile of the full run: confirm the distribution

**Method:** `cProfile` around reset + load + run + state on `/tmp/sr16.dylib` (in-process).

```
465 ms total, 1,761 Python calls
  step (392 calls)  462 ms   99.4%   <- all of it
  poke (328 calls)    1 ms    0.2%
  peek (198 calls)  0.4 ms    0.1%
  assemble + reset + everything else: < 1 ms
```

**Findings:** matches Exp 1's prediction to the millisecond (19,500 ticks × 23.2 µs = 452 ms).
The Python driver, assembler, and ABI chatter are free; **the simulation is 99.4% `tick()`**.
No profiling ambiguity remains at the host level — everything else is about *which ticks we can avoid*.

---
## Exp 3 — Per-asm-op census: which instructions cost the most?

**Method:** `profiling/exp3_op_census.py` — step one instruction at a time, decode MEM[PC] to a
mnemonic, accumulate clocks + wall time per opcode. Run on mul.s and on a 23-instruction probe
touching every instruction class (ALU, shift, LD/ST, PUSH/POP, CALL/RET, JMP, Bcc, NOP, HALT).

mul.s (37 instr, 74 clocks, 413 ms):

| op | n | clocks | ms | % of run |
|---|---|---|---|---|
| ADD | 11 | 22 | 122.8 | 29.8% |
| ADDI | 11 | 22 | 122.7 | 29.7% |
| BNE | 11 | 22 | 122.7 | 29.7% |
| LDI | 3 | 6 | 33.1 | 8.0% |
| HALT | 1 | 2 | 11.3 | 2.7% |

All-ops probe — **ms/op by class**:

```
POP   16.6 ms (3 clocks)      RET  16.6 ms (3 clocks)
everything else 11.0–11.3 ms (2 clocks): ADD SUB AND OR XOR MOV CMP ADC,
SHL SHR SAR ROL ROR NOT, LDI LDIH ADDI, LD ST, PUSH CALL JMP Bcc JR NOP HALT
```

**Findings:**
- Wall time per asm op is **purely its clock count × 5.6 ms/clock**; the *kind* of work in EXEC is
  free (a tick evaluates all 42,530 gates whether they're doing a 16-bit add or a NOP).
- **POP and RET are the slowest ops** (3 clocks, +50%); every other instruction is identical.
- In mul.s the loop body trio ADD/ADDI/BNE burns **89.2%** of the run, evenly split — the only
  asm-level optimization possible is *fewer loop iterations / fewer instructions*, not "cheaper" ones.
- Multiply-by-repeated-addition costs `6 + 6n` clocks for multiplier n (3 LDI + n×(ADD+ADDI+BNE) + HALT)
  → 12×11 = 74 clocks ✓. Worst case (n = 65,535): **393,216 clocks ≈ 36 minutes** stock. Algorithm matters (Exp 6).

---
## Exp 4 — Settle-margin search: how many of the 240 ticks/clock are real?

**Method:** `profiling/exp4_settle.py` — binary-search each budget (t_settle, t_cap, t_gap) for the
smallest value where **all three example programs** (mul, popcount, maxarray) stay in full architectural
lockstep with `sr16tools.golden` after *every* instruction (pc, regs, flags, halted, cycle counts).

```
t_settle sweep (cap=16, gap=4): 200..27 PASS | 26 FAIL (mul never halts)
                                            | 25 FAIL (mul flags Z wrong)
                                            | 12 FAIL (regs corrupt) | 6 FAIL (worse)
t_cap: 16 minimal (15 fails -> mul flags; 8 -> garbage regs)
t_gap:  4 minimal (3 fails -> mul pc diverges; 0 -> maxarray pc diverges)

minimal verified clock: settle=27 cap=16 gap=4  =  67 ticks/clock   (stock: 240)
mul.s run: 115.9 ms @ 67 ticks/clock -> 3.6x speedup    (margin +25%: 82 ticks, 142 ms, 2.9x)
```

**Findings:**
- **Stock T_SETTLE=200 carries ~7× margin**: the real critical path needs only 27 pre-Phi1 settle ticks
  on these programs. (The "~120 gate levels" comment in driver.py describes the full decode→writeback
  path, but much of it settles concurrently with the previous phase's cap/gap ticks.)
- **t_cap=16 and t_gap=4 are exactly at the edge** — whoever pinned them tuned them; no headroom there.
  The failure modes at the edge are instructive: first flags mis-capture (Z lost → loop never exits),
  then PC divergence, then full register corruption as budgets shrink.
- 67-tick clock = 1.56 ms/clock; **3.6× end-to-end speedup with zero correctness loss on the corpus.**
- Caveat: 27 is corpus-minimal, not proven worst-case-path-minimal; a data pattern exercising a longer
  carry chain could need more. For a *contract* change you'd want the doubled-budget guard test +
  margin (e.g. 34/20/4 = 82 ticks, still 2.9×). For peak-throughput experiments below I use 67.

---
## Exp 5 — Can the floor itself move? (host overhead + compiler flags)

**5a — host-overhead ceiling** (`profiling/exp5_hostcost.py`): time 74 clocks three ways —
one giant `step(n)` call (zero host involvement), the Python `clock()` loop, and full
`step_instruction()` with its peeks:

```
stock (17,760 ticks): raw 411.7 ms | clock loop 439.2 ms (+6.7%) | step_instruction 418.6 ms (+1.7%)
tuned ( 4,958 ticks): raw 116.8 ms | clock loop 115.2 ms (-1.4%) | step_instruction 116.0 ms (-0.6%)
```

The deltas are run-to-run noise (the tuned loop measured *faster* than the floor). Per Exp 1
arithmetic the true orchestration cost is ~0.03%. **A C driver / batched ABI / fewer peeks would buy
nothing.** Python is the right place for the driver.

**5b — compiler flags** (`profiling/exp5b_cflags.py`): reflatten + rebuild sr16 under flag variants,
measure ns/tick (median of 5 × 8k-tick runs):

| variant | build | µs/tick | ns/gate-eval | vs stock |
|---|---|---|---|---|
| -O2 (stock) | 19.2s | 23.35 | 0.549 | 1.00× |
| -O3 | 19.1s | 23.28 | 0.547 | 1.00× |
| -O2 -mcpu=native | 18.8s | 23.33 | 0.549 | 1.00× |
| -O3 -mcpu=native | 18.9s | 23.20 | 0.546 | 1.01× |
| -O1 | 27.5s | 23.49 | 0.552 | 0.99× |

**Findings:** 0.55 ns/gate-eval is a hard plateau — the tick is bound by the serial dependence
structure of 42.5k byte loads/stores, not by instruction selection. Within today's scope (no codegen
changes) the floor is **23.2 µs/tick, fixed**; the only remaining levers are *fewer ticks* (Exp 4)
and *fewer clocks per multiply* (Exp 6). (Word-packed or event-driven codegen could move ns/gate,
but that's compiler work, noted for later.)

---
## Exp 4b — The caveat bites: worst-case operands break t_settle=27

**What happened:** while bringing up Exp 6, the lockstep check on a *worst-case* multiply
(shift-add, 65535 × 65535 — every ADD/SHL propagates a full 16-bit carry/shift chain) **diverged at
instruction #102 of 102** with `t_settle=27`: the gate CPU mis-executed right at the end (PC went to 8
instead of halting at 12) while all registers still matched. One settle tick more fixes it:

```
t_settle=27: FAIL (diverged @ instr 102)     t_settle=28..64: PASS
```

**Findings:**
- **Exp 4's "minimal" was corpus-minimal, not path-minimal** — mul/popcount/maxarray never drive the
  longest data-dependent carry chain. The all-ones multiply needs **28** pre-Phi1 settle ticks.
- A 1-tick deficit produced a *control-flow* failure (missed halt) after 101 perfect instructions —
  exactly the silent, data-dependent corruption mode the doubled-budget guard test exists for.
- Lab rule reaffirmed: **a timing budget validated only on typical data is not validated.**
  All further experiments use `t_settle=28, t_cap=16, t_gap=4` → **68 ticks/clock (3.53×)**, and the
  shootout's lockstep gate re-verifies every program at that budget.

---
**Update (same session):** settle=28 then broke shiftadd-12×11 — which had PASSED at 27 (while the
worst case fails 27, passes 28). Non-monotonic! Dense sweep 26–48 + 200 over an 8-program corpus
(3 examples + shiftadd 12×11 + shiftadd 65535² + constfold + both throughput loops):

```
settle 26: sa12x11 FAIL  saWORST FAIL  saloop FAIL     (even)
settle 27: sa12x11 ok    saWORST FAIL  saloop FAIL     (odd)
settle 28: sa12x11 FAIL  saWORST ok    saloop FAIL     (even)
settle 29–48, 200: ALL ok                              (both parities)
```

- 26–28 is a **marginal band that flickers with tick parity** — the classic signature (see
  tasks/lessons.md) of a value still in flight (or a period-2 transient) when Phi1 strobes: which
  snapshot you capture depends on whether the settle count is odd or even. The failure at 28 captured
  `PC=1` when the choice was between 9 (fall-through) and 3 (taken) — a bit-mixed mid-flight mux output.
- **"Passes at N" for one N proves nothing in the band.** The defensible minimum is the start of the
  *stable region*: settle = **29** (verified continuously 29–48 and at 200) → **69 ticks/clock, 3.48×**.
- All Exp 6 numbers below use settle=29/cap=16/gap=4, lockstep-re-verified per program.

---
## Exp 6 — Multiplication throughput shootout

**Method:** `profiling/exp6_mulshootout.py`. Three algorithms, all golden- and gate-lockstep-verified
at the tuned clock (settle=29/cap=16/gap=4 = 69 ticks/clock) before timing:
- `repadd` — `programs/mul.s` as-is: repeated addition, `6+6n` clocks (n = multiplier)
- `shiftadd` — generic 16×16 early-exit shift-add (SHR multiplier; BCC skip; ADD; SHL; CMP/BNE):
  `~6 + 10·bits(b) + 2·popcount(b) + 2` clocks
- `constfold` — straight-line Horner chain for ×11 (SHL/SHL/ADD/SHL/ADD): what a compiler emits
  for a constant multiplier — 16 clocks total

Single multiply, 12 × 11 (reset + load + run):

| algorithm | budget | clocks | load ms | run ms | total ms | mults/s |
|---|---|---|---|---|---|---|
| repadd | stock | 74 | 40 | 416 | 456 | 2.2 |
| repadd | tuned | 74 | 9 | 118 | 126 | 7.9 |
| shiftadd | stock | 54 | 55 | 299 | 353 | 2.8 |
| shiftadd | tuned | 54 | 13 | 89 | 102 | 9.8 |
| constfold | stock | 16 | 47 | 90 | 137 | 7.3 |
| constfold | tuned | 16 | 10 | 26 | **35** | **28.2** |

Back-to-back (K mults in one loaded program, amortizes load; run phase):

```
shiftadd  K=30: 56.1 clocks/mult   stock  3.2/s   tuned 11.0/s
constfold K=80: 16.1 clocks/mult   stock 11.1/s   tuned 38.0/s
```

Worst-case operands, tuned: shiftadd 65535×65535 = 204 clocks = 330 ms.
(repadd would take 393,216 clocks ≈ 10 min tuned, ≈ 36 min stock — algorithm choice is worth 1900×
on adversarial inputs.)

Process-level scaling (`--parallel`, N processes × 80 constfold mults, own dylib state per process):

```
N=1: 37.5/s   N=2: 74.8/s   N=4: 149.7/s   N=8: 285.4/s (7.6x)   N=10: 325.3/s
```

**Findings:**
- Measured clock counts hit the hand-computed predictions exactly (54, 16, 56.1, 16.1, 204).
- **Best single generic 16×16 multiply: ~102 ms** (shiftadd, tuned). Constant-by-known-multiplier: 35 ms.
- **Best sustained throughput: 38 generic-constant mults/s on one core, 325/s on the machine** —
  vs 2.2/s for the stock command line. **~150× overall**, decomposed as:
  3.5× fewer ticks/clock (Exp 4/4b) × ~3.5–4.6× fewer clocks/mult (algorithm) × 7.6–8.7× cores.
- Remaining ceiling is unchanged from Exp 5: 23.2 µs/tick × 69 ticks/clock × 2 clocks/instr ≈
  3.2 ms/instruction ≈ 312 instr/s/core. Anything past that needs cheaper ticks (compiler: word-packed
  or event-driven evaluation), not driver or asm work.

---

## Conclusions

**Q1 — How many 16-bit multiplications in the least time?**
Stock setup: **2.2 mults/s** (456 ms each). With the clock budget cut to its verified-stable minimum
(69 vs 240 ticks/clock), a smarter algorithm, back-to-back execution, and all cores:
**325 mults/s sustained (≈ 38/s single-core)**; minimum latency for one arbitrary 16×16 multiply is
**~102 ms** (54 clocks, shift-add). Each factor is independently verified lockstep-clean against the
golden model.

**Q2a — Which asm operations take longest?** POP and RET (3 clocks ≈ 16.6 ms stock); every other
instruction is exactly 2 clocks ≈ 11.2 ms. Cost is purely clocks × tick-budget — the datapath work
inside an instruction is free (every tick evaluates all 42,530 gates regardless). In mul.s, the loop
trio ADD/ADDI/BNE consumes 89% of the run in equal thirds.

**Q2b — Which of step/peek/poke takes longest?** `step()`, overwhelmingly: 99.4% of wall time
(cProfile). One tick = 23.2 µs (0.55 ns/gate-eval, flag-invariant plateau); clean peek = 0.25 µs;
poke = 0.35 µs; ctypes floor ≈ 0.25 µs. One pitfall: **a peek after a poke costs a hidden lazy tick**
(24.4 µs). Host-side optimization is pointless — a single giant `step()` call is no faster than the
Python clock loop.

**Surprise of the day (Exp 4b):** the settle minimum is not a clean threshold. 26–28 ticks is a
marginal band that passes/fails *by tick parity* per program (mid-flight PC capture: PC=1 vs {9, 3}).
Timing budgets must be validated as a *contiguous stable region* over a corpus that includes
worst-case carry chains — single-point passes can be parity luck.

**Not changed:** `sr16tools/driver.py` budgets stay at the pinned contract values (200/16/4); all
tuned numbers come from per-instance overrides in the experiment scripts. If the contract should move
to 240→69-ish ticks/clock, it needs the deferred doubled-budget guard test plus margin (e.g. 40/16/4).

**Artifacts:** `profiling/exp0_baseline.py`, `exp1_micro.py`, `exp3_op_census.py`, `exp4_settle.py`,
`exp5_hostcost.py`, `exp5b_cflags.py`, `exp6_mulshootout.py` (this file's numbers are reproducible
from these). Flag-variant dylibs in `/tmp/sr16_flags/` (disposable).
