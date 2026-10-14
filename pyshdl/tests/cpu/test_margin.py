"""Settle-margin guard (ISA.md §5): the pinned clock constants have headroom.

Doubling T_CAP / T_GAP / T_SETTLE gives every combinational path twice the
budget. If the pinned constants were near the edge — some path settling just
in time — the doubled run would capture different values somewhere and the
architectural traces would diverge. Identical traces are the hand-derivable
expectation: extra settle ticks must be invisible to a circuit whose budgets
are sufficient, because stable combinational logic is idempotent under step().
"""

from __future__ import annotations

from .test_programs import GCD, MEMCPY


def _trace(cpu, words, limit: int = 400):
    """Per-instruction architectural trace until HALT."""
    cpu.reset()
    cpu.load_program(words)
    out = []
    for _ in range(limit):
        cycles = cpu.step_instruction()
        st = cpu.state()
        out.append(
            (
                cycles,
                st["pc"],
                st["ir"],
                tuple(st["regs"]),
                st["z"],
                st["n"],
                st["c"],
                st["v"],
                st["halted"],
            )
        )
        if st["halted"]:
            return out
    raise AssertionError(f"not halted within {limit} instructions")


def test_doubled_clock_budgets_leave_trace_unchanged(cpu_builds, sr16):
    from sr16tools.asm import assemble
    from sr16tools.driver import SR16, T_CAP, T_GAP, T_SETTLE

    slow = SR16(
        cpu_builds.fresh_path("sr16"), t_cap=2 * T_CAP, t_gap=2 * T_GAP, t_settle=2 * T_SETTLE
    )

    for source in (GCD, MEMCPY):  # branches/ALU + RAM load/store traffic
        words = assemble(source)
        pinned = _trace(sr16, words)
        doubled = _trace(slow, words)
        assert pinned == doubled
        # memory agrees under both timings as well
        for addr in (0x40, 0x45, 0x70, 0x75, 0xF0):
            assert sr16.read_mem(addr) == slow.read_mem(addr)
