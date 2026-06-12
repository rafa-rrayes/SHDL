"""CPU-8 (freeze half): LdEn freezes a RUNNING CPU (ISA.md §6).

The full-image DMA load/readback fidelity is already covered
(test_instructions.test_program_load_fidelity_full_image). The §6 contract
also says LdEn "freezes the CPU (all CPU state-write enables masked)" — so far
only *implied* by programs starting cleanly after a load. Here we assert it
directly against a mid-execution CPU:

  1. load + run a program for a few instructions,
  2. capture the full visible architectural state,
  3. raise LdEn (LdWe low: a pure freeze, no DMA write), clock several times,
  4. assert no visible architectural state changed,
  5. lower LdEn and run to completion,
  6. assert the program produced exactly the result it would have unfrozen.

control.shdl gates IrWe/PcWe/RegWe/RamWe/StateWe and all three flag-write
enables behind runN = !LdEn, so a frozen CPU must hold every latch.
"""

from __future__ import annotations

from .conftest import lockstep

# A short, deterministic program with a loop so the freeze can land in the
# middle of meaningful work (not on a HALT). Computes 4+3+2+1 = 10 into r2.
TRIANGLE = """
        LI   r1, 4
        LI   r2, 0
loop:   ADD  r2, r2, r1
        ADDI r1, r1, -1
        CMP  r1, r0
        BNE  loop
        LI   r3, 0x60
        ST   [r3], r2          ; mem[0x60] = 10
        HALT
"""


def _full_state(cpu) -> dict:
    """Every peekable architectural pin, as one comparable snapshot."""
    st = cpu.state()
    # also fold in a few memory words so a RAM write leaking past the freeze
    # would be caught (read_mem itself drives LdEn, so do it after capture).
    return st


def test_ldEn_freezes_running_cpu(sr16):
    # CPU-8: direct freeze assertion against a mid-execution CPU.
    from sr16tools.asm import assemble

    words = assemble(TRIANGLE)
    sr16.reset()
    sr16.load_program(words)

    # Run a handful of instructions so we are demonstrably mid-execution
    # (inside the loop, not halted, FSM cycling).
    for _ in range(5):
        sr16.step_instruction()
    assert not sr16.peek("Halted"), "should still be running before the freeze"

    before = _full_state(sr16)
    mem_before = {a: sr16.read_mem(a) for a in (0x60, 0x00, 0xFF)}

    # --- freeze: LdEn high, LdWe low (no DMA write) ---
    sr16.poke("LdEn", 1)
    sr16.poke("LdWe", 0)
    # Clock several full two-phase cycles while frozen; nothing may change.
    for i in range(6):
        sr16.clock()
        frozen = sr16.state()
        # read_mem toggles LdEn internally, so compare the pin snapshot here
        assert frozen == before, (
            f"frozen state changed after {i + 1} clock(s):\n"
            f"  before={before}\n  after ={frozen}"
        )

    # RAM also untouched while frozen (LdWe low, every CPU write masked).
    for a, want in mem_before.items():
        got = sr16.read_mem(a)
        assert got == want, f"mem[{a:#04x}] changed during freeze: {got:#06x} != {want:#06x}"

    # --- unfreeze and run to completion ---
    sr16.poke("LdEn", 0)
    sr16.poke("LdWe", 0)
    sr16.run()
    assert sr16.peek("Halted")
    assert sr16.read_mem(0x60) == 10, "program must finish correctly after unfreeze"
    # registers landed: r2 = 10, r1 ran down to 0
    final = sr16.state()
    assert final["regs"][2] == 10
    assert final["regs"][1] == 0


def test_freeze_then_resume_matches_uninterrupted_run(sr16):
    """Freezing mid-run must not perturb the final architectural result.

    Reference: the same program run start-to-finish with no freeze (via the
    lockstep harness, also checked against the golden model). Then a second run
    that freezes mid-execution must reach the identical visible end state.
    """
    # CPU-8
    from sr16tools.asm import assemble

    # Reference run (lockstep also validates it against the golden model).
    ref_golden = lockstep(sr16, TRIANGLE)
    ref_regs = list(ref_golden.regs)
    ref_flags = (ref_golden.z, ref_golden.n, ref_golden.c, ref_golden.v)
    ref_mem60 = ref_golden.mem[0x60]
    assert ref_mem60 == 10  # hand-derived: 4+3+2+1

    # Interrupted run.
    words = assemble(TRIANGLE)
    sr16.reset()
    sr16.load_program(words)
    for _ in range(3):
        sr16.step_instruction()
    sr16.poke("LdEn", 1)
    sr16.poke("LdWe", 0)
    sr16.clock(4)
    sr16.poke("LdEn", 0)
    sr16.run()
    assert sr16.peek("Halted")

    st = sr16.state()
    assert st["regs"] == ref_regs, f"regs after freeze {st['regs']} != uninterrupted {ref_regs}"
    got_flags = (st["z"], st["n"], st["c"], st["v"])
    assert got_flags == ref_flags, f"flags after freeze {got_flags} != {ref_flags}"
    assert sr16.read_mem(0x60) == ref_mem60
