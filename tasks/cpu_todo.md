# SR16 — 16-bit CPU in SHDL — Build Checklist

Approved design (2026-06-10): load-store RISC, 8 GPRs (R7 = SP), unified in-circuit
RAM (parameterized, default 256 words), multi-cycle FSM (FETCH/EXEC/MEMRD/HALTED),
flags + conditional branches, stack + CALL/RET, shift/rotate, two-phase
non-overlapping clock (phi1 = masters + RAM cells, phi2 = slaves).

Spec of record: `examples/CPU/ISA.md`. Per user direction (2026-06-10): finish
writing all CPU artifacts first; tests after.

- [x] 0. Learn SHDL; agree architecture with user; write this plan
- [x] 1. `examples/CPU/ISA.md` — full ISA + microarchitecture + pin/protocol spec
- [x] 2. `examples/CPU/seq.shdl` — MSFF, MSFFE (load-enable), RegE<N>; two-phase tests
- [x] 3. `examples/CPU/parts.shdl` — Mux8N/Mux16N, Dec2/3/4, Inc16, Or16; tests
- [x] 4. `examples/CPU/alu.shdl` — 16-bit ALU (ADD/SUB/ADC/AND/OR/XOR/MOV/NOT/shifts) + Z N C V; tests vs Python model
- [x] 5. `examples/CPU/regfile.shdl` — 8×16, 2R/1W; tests
- [x] 6. `examples/CPU/ram.shdl` — 256-word RAM, phi1-strobed write, combinational read
      — the "addr 64 aliasing" bug turned out to be power-on metastability of
      every SRLatch (see item 10); decode was always correct
- [x] 7. `examples/CPU/control.shdl` — FSM + decode → control word (flatten-checked)
- [x] 8. `examples/CPU/sr16.shdl` — top: datapath + control + loader/DMA + debug pins
      (flattens to ~917k lines of Base SHDL)
- [x] 9. `examples/CPU/sr16tools/` — assembler (`asm.py`), golden model (`golden.py`),
      driver (`driver.py`); asm+golden smoke-tested together (sum/stack/CALL program)
- [x] 10. Fix the "RAM bug" — root cause was NOT address decode:
      `srLatch.shdl` seeded only the NOR outputs, but `stdgates::NOR` is a
      composite (OR→NOT), so the internal OR nets stayed 0 — the seeded state
      was not a fixed point of the unit-delay loop and every never-written
      latch oscillated with period 4 from power-on (Q reads 0xFFFF at tick
      counts ≡ 2 mod 4 — hence the flaky "addr 64" symptom). Fix: rebuild
      SRLatch from the four primitive gates it contains and seed the complete
      loop state (o1=1, i1=0, o2=0, i2=1 — each seed equals what that gate
      computes from the others with S=R=0). Toolchain untouched & innocent:
      seeds flatten correctly; conformance stays green (the frozen `sr_latch`
      corpus case has its own copy of the old circuit).
      Verification plan for items 11–13 (2026-06-10):
      - [x] 10a. Power-on stability tests: BaseEval fixed-point check for
            SRLatch (full gate state reproduces itself, ticks 1–8) +
            power-on hold tests at multiple tick offsets up the whole stack:
            DLatch, MSFFE, RegE, RegFile, RAM256, SR16 visible state
            (`tests/cpu/test_poweron.py`). The two failing RAM tests must
            flip green UNCHANGED (verified: 52/52 pass).
      - [x] 10b. Audit other `init` blocks: only `tests/fixtures/srlatch.shdl`
            has the old pattern — intentionally kept: it is a compiler-fidelity
            fixture whose goldens are BaseEval-derived (test_feedback pins the
            oracle trace; test_model tests init resolution through composites).
            `examples/CPU/*.shdl` has no init blocks; ringClock has none.
- [x] 11. Per-instruction directed tests vs golden model, lockstep
      (state compared after EVERY instruction): all 8 ALU functs, all 8 shift
      functs (incl. reserved 6/7 = NOT), LDI/LDIH/LI, LD/ST (offset edges,
      mod-256 aliasing), ADDI, all 8 conds × taken/not-taken, JMP/CALL/JR/RET,
      PUSH/POP (incl. PUSH R7 old-value, POP R7 load-wins, SP wrap), NOP,
      HALT, reserved opcodes 0xB–0xF + reserved MISC functs 6/7 trap to HALT.
      Cycle costs compared per instruction (2, POP/RET 3).
- [x] 12. Program tests vs golden model: Fibonacci, array sum, GCD,
      nested CALL/stack (recursive sum, depth 6), memcpy — lockstep
      per-instruction + memory compare + hand-derived headline results.
- [x] 13. Settle-margin guard test (2× T_CAP/T_GAP/T_SETTLE ⇒ identical
      per-instruction architectural trace, GCD + memcpy); README.md; review below

---

## Review (2026-06-10, verification pass)

**Root cause found (item 10):** not address decode. `stdgates::NOR` is a
composite (OR→NOT), so the old SRLatch `init { n1.O=0; n2.O=1 }` seeded only
the two NOT outputs; the two internal OR nets stayed 0. In the unit-delay
model the state of a feedback loop is all four gate outputs, and that seeded
state was not a fixed point — every never-written latch fell into a period-4
limit cycle from power-on, reading 0xFFFF at tick counts ≡ 2 (mod 4). The
"write 0 appears at 64" symptom was a parity accident of one test's tick
arithmetic; in truth all 251 untouched cells were oscillating (the corruption
value was data-independent — the tell that it was never a decode overlap).
Fix: `examples/srLatch.shdl` rebuilt from the four primitive gates it
actually contains, seeding the complete loop state (o1=1, i1=0, o2=0, i2=1).
Same interface; docstring now states the fixed-point rule. The fix covers
registers, PC, IR, FSM state and RAM in one place since all CPU state flows
from SRLatch. Toolchain untouched (seeds always flattened correctly);
conformance stayed green throughout (`66 checks, 0 failures` — corpus cases
are self-contained copies). `tests/fixtures/srlatch.shdl` keeps the old
pattern deliberately: it is a compiler-fidelity fixture with BaseEval-derived
goldens (test_feedback pins the oscillating oracle trace; test_model tests
init resolution through composites).

**Coverage achieved (items 11–12):** every opcode 0x0–0xF, every ALU funct
(8), every shift funct incl. reserved 6/7-as-NOT (8), every MISC funct incl.
reserved 6/7-as-HALT (8), every branch condition taken AND not-taken (8×2),
reserved opcodes 0xB–0xF trap-to-HALT, LDI sign extension, LDIH byte merge,
LD/ST simm6 edges ±32/31 and mod-256 physical aliasing, ADDI flag edges,
PUSH-R7-old-value, POP-R7-load-wins, SP wrap 0→0xFFFF, CALL/RET nesting,
PC wrap at 0xFFFF, fetch aliasing (PC=0x105 → mem[5]), DMA load/readback of
all 256 words, HALTED terminal-state stability, per-instruction cycle costs
(2, POP/RET 3). All via the lockstep runner (`tests/cpu/conftest.py`):
architectural state compared after EVERY instruction, golden-written memory
compared at the end. Programs: Fibonacci(20)=6765, array sum with 16-bit
wraparound, GCD(252,105)=21, recursive CALL/stack sum(6)=21 with full
unwind, memcpy — each also pinned to hand-derived constants.

**Margin (item 13):** doubling T_CAP/T_GAP/T_SETTLE leaves the
per-instruction trace and memory bit-identical for GCD + memcpy.

**Numbers:** full CPU now flattens in ~1s, compiles in ~14s (perf work
landed earlier on 2026-06-10); one clock cycle ≈ 6ms; the whole
`tests/cpu` suite (84 tests) runs in ~2.5 min.

**Still open / deferred:**
- An init fixed-point lint in the flattener (warn when seeded gates don't
  reproduce under zeroed inputs; ringClock is the intentional exception) —
  filed separately by the user; toolchain deliberately untouched here.
- Golden model and ISA.md were cross-checked line-by-line; no divergence
  found, so no spec fixes were needed.
