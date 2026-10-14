"""RAM256: combinational read, Phi1-strobed write, address decode."""

from __future__ import annotations

SETTLE = 60  # decode + read tree


def ram_write(s, addr, data):
    s.poke("Addr", addr)
    s.poke("WData", data)
    s.poke("WE", 1)
    s.step(SETTLE)  # decode settles before the strobe
    s.poke("Phi1", 1)
    s.step(10)  # latch capture
    s.poke("Phi1", 0)
    s.poke("WE", 0)
    s.step(4)


def ram_read(s, addr):
    s.poke("Addr", addr)
    s.step(SETTLE)
    return s.peek("Q")


def test_ram_write_read_corners(cpu_builds):
    s = cpu_builds.sim("ram")
    patterns = {0: 0xFFFF, 1: 0x0001, 127: 0xAAAA, 128: 0x5555, 255: 0x8001}
    for addr, data in patterns.items():
        ram_write(s, addr, data)
    for addr, data in patterns.items():
        assert ram_read(s, addr) == data, f"addr {addr}"
    # untouched cells stay zero
    assert ram_read(s, 64) == 0


def test_ram_overwrite_and_isolation(cpu_builds):
    s = cpu_builds.sim("ram")
    ram_write(s, 10, 0x1234)
    ram_write(s, 11, 0x4321)
    ram_write(s, 10, 0x5678)
    assert ram_read(s, 10) == 0x5678
    assert ram_read(s, 11) == 0x4321
    assert ram_read(s, 9) == 0
    assert ram_read(s, 12) == 0


def test_ram_no_write_without_strobe(cpu_builds):
    s = cpu_builds.sim("ram")
    s.poke("Addr", 42)
    s.poke("WData", 0x7777)
    s.poke("WE", 1)
    s.step(SETTLE)  # WE high but Phi1 never pulsed
    s.poke("WE", 0)
    assert ram_read(s, 42) == 0
