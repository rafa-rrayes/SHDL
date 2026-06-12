"""MSFFE / RegE: edge-triggered behavior from two-phase latches (ISA.md §5)."""

from __future__ import annotations

from .conftest import T_CAP, T_GAP, T_SETTLE, clock


def test_msffe_load_and_hold(cpu_builds):
    s = cpu_builds.sim("seq", top="MSFFE")
    assert s.peek("Q") == 0

    s.poke("D", 1)
    s.poke("LD", 0)
    clock(s, 2)
    assert s.peek("Q") == 0, "LD=0 must hold"

    s.poke("LD", 1)
    clock(s)
    assert s.peek("Q") == 1, "LD=1 must capture D"

    s.poke("D", 0)
    s.poke("LD", 0)
    clock(s, 3)
    assert s.peek("Q") == 1, "holds captured value across cycles"


def test_rege_basic(cpu_builds):
    s = cpu_builds.sim("seq")  # top RegE<16>
    assert s.peek("Q") == 0

    s.poke("D", 0xBEEF)
    s.poke("LD", 0)
    clock(s)
    assert s.peek("Q") == 0

    s.poke("LD", 1)
    clock(s)
    assert s.peek("Q") == 0xBEEF

    s.poke("D", 0x1234)
    s.poke("LD", 0)
    clock(s)
    assert s.peek("Q") == 0xBEEF

    s.poke("LD", 1)
    clock(s)
    assert s.peek("Q") == 0x1234


def test_rege_captures_on_phi1_not_phi2(cpu_builds):
    """The value sampled while Phi1 is high is what Phi2 publishes — a D
    change between the phases must NOT leak through (edge semantics)."""
    s = cpu_builds.sim("seq")
    s.poke("LD", 1)
    s.poke("D", 0xAAAA)

    s.poke("Phi1", 1)
    s.step(T_CAP)
    s.poke("Phi1", 0)
    s.step(T_GAP)

    s.poke("D", 0x5555)  # too late: master already closed
    s.step(T_GAP)

    s.poke("Phi2", 1)
    s.step(T_CAP)
    s.poke("Phi2", 0)
    s.step(T_SETTLE)

    assert s.peek("Q") == 0xAAAA
