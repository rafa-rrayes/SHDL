"""Combinational library parts. Pure logic: poke, settle with step(), peek."""

from __future__ import annotations

import pytest

SETTLE = 40  # generous combinational settle for these shallow parts


def settled(sim, **pokes):
    for k, v in pokes.items():
        sim.poke(k, v)
    sim.step(SETTLE)


@pytest.mark.parametrize("sel", range(8))
def test_mux8n(cpu_builds, sel):
    s = cpu_builds.sim("parts", top="Mux8N")
    for i in range(8):
        s.poke(f"D{i}", 0x1111 * (i + 1))
    settled(s, S=sel)
    assert s.peek("O") == 0x1111 * (sel + 1)


@pytest.mark.parametrize("sel", [0, 1, 5, 9, 10, 15])
def test_mux16n(cpu_builds, sel):
    s = cpu_builds.sim("parts", top="Mux16N")
    for i in range(16):
        s.poke(f"D{i}", 0x1000 + i)
    settled(s, S=sel)
    assert s.peek("O") == 0x1000 + sel


@pytest.mark.parametrize("comp,bits", [("Dec2", 2), ("Dec3", 3), ("Dec4", 4)])
def test_decoders(cpu_builds, comp, bits):
    s = cpu_builds.sim("parts", top=comp)
    for sel in range(1 << bits):
        settled(s, S=sel)
        assert s.peek("O") == 1 << sel, f"{comp} sel={sel}"


@pytest.mark.parametrize("a", [0, 1, 2, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF, 0x1234])
def test_inc16(cpu_builds, a):
    s = cpu_builds.sim("parts", top="Inc16")
    settled(s, A=a)
    assert s.peek("Q") == (a + 1) & 0xFFFF


@pytest.mark.parametrize("a", [0, 1, 0x8000, 0xFFFF, 0x0010])
def test_or16(cpu_builds, a):
    s = cpu_builds.sim("parts", top="Or16")
    settled(s, A=a)
    assert s.peek("O") == (1 if a else 0)
