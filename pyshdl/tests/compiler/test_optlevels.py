"""Determinism across C optimization levels: -O0 and -O3 traces identical.

shdlc_goals.md §7.2: same call sequence, same results, at every optimization
level.
"""

from __future__ import annotations

import random
import zlib

import pytest

from .harness import STRICT_CFLAGS, load_fresh_copy, make_oracle, parse_with_ports


def _with_opt(level: str) -> tuple[str, ...]:
    # Keep -shared/-fPIC/-Werror etc.; swap only the optimization level.
    return tuple(level if flag == "-O2" else flag for flag in STRICT_CFLAGS)


@pytest.mark.parametrize("name", ["add2", "srlatch"])
def test_o0_and_o3_traces_identical(builds, name):
    text = builds.fixture_text(name)
    lib0 = builds.lib_from_text(f"{name}-O0", text, cflags=_with_opt("-O0"))
    lib3 = builds.lib_from_text(f"{name}-O3", text, cflags=_with_opt("-O3"))
    sim0 = load_fresh_copy(lib0, builds.instances)
    sim3 = load_fresh_copy(lib3, builds.instances)

    oracle = make_oracle(text)
    ports = parse_with_ports(text).meta["ports"]
    in_ports = list(ports["inputs"])
    all_ports = [*ports["inputs"], *ports["outputs"]]
    widths = {n: len(w) for n, w in (ports["inputs"] | ports["outputs"]).items()}

    rng = random.Random(zlib.crc32(name.encode()) ^ 0x0030)  # stable script
    trace0, trace3 = [], []
    for cycle in range(1, 51):
        if in_ports and rng.random() < 0.6:
            port = rng.choice(in_ports)
            raw = rng.getrandbits(64)
            sim0.poke(port, raw)
            sim3.poke(port, raw)
            oracle.poke(port, raw & ((1 << widths[port]) - 1))
        sim0.step(1)
        sim3.step(1)
        oracle.step(1)
        snap0 = tuple(sim0.peek(p) for p in all_ports)
        snap3 = tuple(sim3.peek(p) for p in all_ports)
        want = tuple(oracle.peek(p) for p in all_ports)
        assert snap0 == want, (name, "O0", cycle)
        assert snap3 == want, (name, "O3", cycle)
        trace0.append(snap0)
        trace3.append(snap3)
    assert trace0 == trace3
