# Lessons

## Debugging gate-level circuits (2026-06-10, SR16 RAM "decode bug")

- **A "corrupted" read whose value is data-independent points at
  initialization/oscillation, not decode.** The RAM bug read 0xFFFF
  regardless of what was written (even 0x1234); a decode overlap would
  have echoed written data. The first probe to run: change *only* the
  number of settle ticks and re-read — a value that flickers with tick
  parity is an oscillating feedback loop, not a wiring error.
- **Don't trust a bug's filed title; reproduce the symptom and widen the
  net first.** "Write to 0 appears at 64" was actually "all 251
  untouched cells oscillate"; the single-address symptom was a parity
  accident of that test's tick counts. A full-space scan after each
  write (cheap) falsified the decode theory in one run.
- **In the unit-delay model, the state of a feedback loop is ALL of its
  gate outputs, and `init` must seed a fixed point.** Seeding only the
  visible outputs of a composite gate (stdgates::NOR = OR→NOT) leaves
  the internal nets at 0; a symmetric state never breaks symmetry in a
  deterministic network — it oscillates forever (period 4 here, so the
  bug hid at 3 of every 4 tick offsets). A component that seeds a loop
  must own every gate in the loop.
- **Tests that write-then-read never catch power-on bugs.** Every
  stateful component test passed because it wrote before reading; only
  the RAM test read a never-written cell. Power-on/hold tests at
  multiple tick offsets (1–8 plus a window around the settle count)
  belong in the suite for every stateful part.

## Timing-budget validation (2026-06-10, SR16 settle-margin profiling)

- **A budget that passes at one settle count can be passing by parity luck.**
  Settle 26–28 on SR16 was a marginal band where pass/fail flickered with
  tick parity per program (27: program A ok / B fails; 28: A fails / B ok)
  — a value still in flight at the strobe gets captured as a bit-mixed
  hybrid (PC=1 captured when the choice was 9 vs 3). Validate a
  *contiguous stable region* (every value from the candidate up through
  ~1.5×, plus the contract value), never a single point.
- **The minimal budget must be searched with worst-case data paths in the
  corpus.** mul/popcount/maxarray all pass at settle=27; 65535×65535
  (full 16-bit carry/shift chains) fails until 28. Corpus-minimal ≠
  path-minimal; include all-ones operands when timing adders/shifters.
