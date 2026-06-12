"""Power-on stability of every stateful layer (ISA.md §1: all latches 0).

Regression net for the SRLatch metastability bug (tasks/cpu_todo.md item 10):
the old latch seeded only the composite-NOR outputs, leaving the internal OR
nets at 0 — not a fixed point of the unit-delay loop — so every never-written
latch oscillated with period 4 and read 0xFFFF at tick counts ≡ 2 (mod 4).

Every assertion here is therefore made at MULTIPLE tick offsets (small ones
plus a window around the unit tests' settle budget) so that no oscillation of
any period up to 8 can hide in a parity accident. Expected values are
hand-derived from ISA.md §1 / srLatch.shdl seeds: everything reads 0 at every
offset (latch Qn reads 1).
"""

from __future__ import annotations

from compiler.harness import make_oracle

from .conftest import clock

# Small offsets catch short-period limit cycles from the seeded state; the
# 55..63 window brackets the RAM tests' settle budget (the original bug fired
# at 58 and 62 — ≡ 2 mod 4 — and hid everywhere else).
OFFSETS = [1, 2, 3, 4, 5, 6, 7, 8, 55, 57, 58, 59, 61, 62, 63]


# --- SRLatch: the seeds are a fixed point of the loop (BaseEval, no C) ------


def test_srlatch_seed_is_fixed_point(cpu_builds):
    oracle = make_oracle(cpu_builds.text("srLatch"))
    oracle.reset()
    seeded = dict(oracle.state)
    assert any(seeded.values()), "expected nonzero init seeds"
    for tick in range(1, 9):
        oracle.step(1)
        assert oracle.state == seeded, f"state diverged from seeds at tick {tick}"
        assert oracle.peek("Q") == 0, f"Q at tick {tick}"
        assert oracle.peek("Qn") == 1, f"Qn at tick {tick}"


def test_srlatch_still_latches(cpu_builds):
    """The rebuilt latch is functionally an SR latch (set / hold / reset)."""
    oracle = make_oracle(cpu_builds.text("srLatch"))
    oracle.reset()
    oracle.poke("S", 1)
    oracle.step(8)
    assert (oracle.peek("Q"), oracle.peek("Qn")) == (1, 0)
    oracle.poke("S", 0)
    oracle.step(8)
    assert (oracle.peek("Q"), oracle.peek("Qn")) == (1, 0), "hold after set"
    oracle.poke("R", 1)
    oracle.step(8)
    assert (oracle.peek("Q"), oracle.peek("Qn")) == (0, 1)
    oracle.poke("R", 0)
    oracle.step(8)
    assert (oracle.peek("Q"), oracle.peek("Qn")) == (0, 1), "hold after reset"


# --- DLatch ------------------------------------------------------------------


def test_dlatch_poweron_hold(cpu_builds):
    s = cpu_builds.sim("dLatch")
    for off in OFFSETS:
        s.reset()
        s.step(off)
        assert s.peek("Q") == 0, f"Q at offset {off}"
        assert s.peek("Qn") == 1, f"Qn at offset {off}"
    # D wiggling with EN low must not disturb the held 0
    s.reset()
    for d in (1, 0, 1, 1, 0):
        s.poke("D", d)
        s.step(7)  # odd on purpose
        assert s.peek("Q") == 0
        assert s.peek("Qn") == 1


# --- MSFFE / RegE (seq.shdl) -------------------------------------------------


def test_msffe_poweron_hold(cpu_builds):
    s = cpu_builds.sim("seq", top="MSFFE")
    for off in OFFSETS:
        s.reset()
        s.step(off)
        assert s.peek("Q") == 0, f"Q at offset {off}"
    # unclocked, then clocked-but-not-loaded: still 0
    s.reset()
    s.poke("D", 1)
    s.step(9)
    assert s.peek("Q") == 0
    clock(s, 3)  # LD = 0
    assert s.peek("Q") == 0
    s.poke("LD", 1)  # sanity: the part still loads
    clock(s)
    assert s.peek("Q") == 1


def test_rege_poweron_hold(cpu_builds):
    s = cpu_builds.sim("seq")  # top RegE<16>
    for off in OFFSETS:
        s.reset()
        s.step(off)
        assert s.peek("Q") == 0, f"Q at offset {off}"
    s.reset()
    s.poke("D", 0xFFFF)
    clock(s, 2)  # LD = 0: hold
    assert s.peek("Q") == 0
    s.poke("LD", 1)
    clock(s)
    assert s.peek("Q") == 0xFFFF


# --- RegFile -----------------------------------------------------------------


def test_regfile_poweron_hold(cpu_builds):
    s = cpu_builds.sim("regfile")
    for off in OFFSETS:
        s.reset()
        s.step(off)
        for port in ("RD1", "RD2", *(f"Q{i}" for i in range(8))):
            assert s.peek(port) == 0, f"{port} at offset {off}"
    # sweep both read addresses with odd settles, nothing written yet
    s.reset()
    for r in range(8):
        s.poke("RAddr1", r)
        s.poke("RAddr2", 7 - r)
        s.step(41)
        assert s.peek("RD1") == 0, f"RD1 sel {r}"
        assert s.peek("RD2") == 0, f"RD2 sel {7 - r}"


# --- RAM256: the test that would have caught the original bug ----------------


def test_ram_poweron_hold_all_offsets(cpu_builds):
    s = cpu_builds.sim("ram")
    for addr in (0, 1, 63, 64, 65, 128, 255):
        for off in OFFSETS:
            s.reset()
            s.poke("Addr", addr)
            s.step(off)
            assert s.peek("Q") == 0, f"addr {addr} at offset {off}"


def test_ram_write_isolation_all_offsets(cpu_builds):
    """After one write, every other word reads 0 at every parity."""
    s = cpu_builds.sim("ram")
    s.poke("Addr", 0)
    s.poke("WData", 0x1234)
    s.poke("WE", 1)
    s.step(60)
    s.poke("Phi1", 1)
    s.step(10)
    s.poke("Phi1", 0)
    s.poke("WE", 0)
    s.step(4)
    for addr in (1, 2, 63, 64, 65, 127, 128, 192, 255):
        for settle in (57, 58, 59, 60, 61, 62):
            s.poke("Addr", 0)
            s.step(4)  # force a re-decode for every probe
            s.poke("Addr", addr)
            s.step(settle)
            assert s.peek("Q") == 0, f"addr {addr} at settle {settle}"
    s.poke("Addr", 0)
    s.step(60)
    assert s.peek("Q") == 0x1234


# --- SR16 top: full visible architectural state ------------------------------


def test_sr16_poweron_state(cpu_builds, sr16):
    pins = ["Halted", "PCout", "IRout", "Flags", "State", "MemOut",
            *(f"R{i}out" for i in range(8))]
    for off in OFFSETS:
        sr16.reset()
        sr16.step(off)
        for pin in pins:
            assert sr16.peek(pin) == 0, f"{pin} at offset {off}"
