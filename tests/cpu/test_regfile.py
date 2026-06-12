"""Register file: write/read ports, write-enable gating, debug outputs."""

from __future__ import annotations

from .conftest import clock

SETTLE = 40  # read mux settle after changing a read address


def test_write_read_all_registers(cpu_builds):
    s = cpu_builds.sim("regfile")
    for r in range(8):
        s.poke("WAddr", r)
        s.poke("WData", 0x1100 + r)
        s.poke("WE", 1)
        clock(s)
    s.poke("WE", 0)

    for r in range(8):
        s.poke("RAddr1", r)
        s.poke("RAddr2", 7 - r)
        s.step(SETTLE)
        assert s.peek("RD1") == 0x1100 + r
        assert s.peek("RD2") == 0x1100 + (7 - r)
        assert s.peek(f"Q{r}") == 0x1100 + r


def test_we_gates_writes(cpu_builds):
    s = cpu_builds.sim("regfile")
    s.poke("WAddr", 3)
    s.poke("WData", 0xDEAD)
    s.poke("WE", 1)
    clock(s)

    s.poke("WData", 0xBEEF)
    s.poke("WE", 0)
    clock(s, 2)

    s.poke("RAddr1", 3)
    s.step(SETTLE)
    assert s.peek("RD1") == 0xDEAD, "WE=0 must not write"


def test_write_only_targets_waddr(cpu_builds):
    s = cpu_builds.sim("regfile")
    s.poke("WAddr", 5)
    s.poke("WData", 0xCAFE)
    s.poke("WE", 1)
    clock(s)
    s.poke("WE", 0)
    s.step(SETTLE)
    for r in range(8):
        assert s.peek(f"Q{r}") == (0xCAFE if r == 5 else 0)
