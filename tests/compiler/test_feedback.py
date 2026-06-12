"""Feedback circuits: SR latch transients and the 20-stage ring clock.

The latch's NORs are flattened to OR+NOT pairs, so the loop is four gate
levels deep and the set/reset transients pass through states that look
inconsistent (Q == Qn) — the compiled library must reproduce them exactly.
"""

from __future__ import annotations

from .harness import make_oracle

# Scripted (S, R) sequence, one entry per cycle: idle, set, idle, reset,
# idle, set.
SRLATCH_SCRIPT = (
    [(0, 0)] * 2 + [(1, 0)] * 4 + [(0, 0)] * 3 + [(0, 1)] * 4 + [(0, 0)] * 3 + [(1, 0)] * 4
)
# (Q, Qn) observed AFTER each scripted cycle, derived from BaseEval
# (scratch run 2026-06-10). Fresh power-on state is Q=0, Qn=1 (meta.init).
SRLATCH_TRACE = [
    (1, 1),
    (0, 1),  # idle transient from the init seeds
    (0, 0),
    (0, 0),
    (1, 0),
    (1, 0),  # set: Q reaches 1 on the 3rd set cycle
    (1, 0),
    (1, 0),
    (1, 0),  # idle: holds the set state
    (1, 0),
    (0, 0),
    (0, 0),
    (0, 1),  # reset: Qn reaches 1 on the 4th cycle
    (0, 1),
    (0, 1),
    (0, 1),  # idle: holds the reset state
    (0, 1),
    (0, 0),
    (0, 0),
    (1, 0),  # set again
]

RING_BITS = 20


def rotl20(v: int) -> int:
    return ((v << 1) | (v >> (RING_BITS - 1))) & ((1 << RING_BITS) - 1)


def test_oracle_srlatch_trace_is_pinned(builds):
    """Pure-oracle pinning (passes today): catches BaseEval/fixture drift."""
    oracle = make_oracle(builds.fixture_text("srlatch"))
    assert (oracle.peek("Q"), oracle.peek("Qn")) == (0, 1)
    got = []
    for s, r in SRLATCH_SCRIPT:
        oracle.poke("S", s)
        oracle.poke("R", r)
        oracle.step(1)
        got.append((oracle.peek("Q"), oracle.peek("Qn")))
    assert got == SRLATCH_TRACE


def test_srlatch_scripted_sequence(builds):
    dual = builds.dual_fixture("srlatch")
    # Power-on: init seeds applied, dirty clear (no hidden tick on peek).
    assert (dual.sim.peek("Q"), dual.sim.peek("Qn")) == (0, 1)
    got = []
    for s, r in SRLATCH_SCRIPT:
        dual.poke("S", s)
        dual.poke("R", r)
        dual.step_compare(1)  # every transient compared against BaseEval
        got.append((dual.sim.peek("Q"), dual.sim.peek("Qn")))
    assert got == SRLATCH_TRACE


def test_oracle_clock_rotation_is_pinned(builds):
    """Pure-oracle pinning (passes today) of the ring-rotation law."""
    oracle = make_oracle(builds.fixture_text("clock"))
    oracle.poke("clk", 1)
    oracle.step(1)
    vals = [oracle.peek("out")]
    assert vals[0] == 0x1
    oracle.poke("clk", 0)
    for _ in range(45):
        oracle.step(1)
        vals.append(oracle.peek("out"))
    assert all(v.bit_count() == 1 for v in vals)
    assert all(vals[k + 1] == rotl20(vals[k]) for k in range(len(vals) - 1))


def test_clock_ring_one_hot_rotation(builds):
    dual = builds.dual_fixture("clock")
    assert dual.sim.peek("out") == 0  # cycle 0: ring is empty
    # Inject a single-cycle pulse, then let it circulate.
    dual.poke("clk", 1)
    dual.step_compare(1)
    vals = [dual.sim.peek("out")]
    assert vals[0] == 0x1  # derived from BaseEval: pulse enters stage 1
    dual.poke("clk", 0)
    for _ in range(45):
        dual.step_compare(1)  # lib vs BaseEval on all ports, every cycle
        vals.append(dual.sim.peek("out"))
    # The pulse is one-hot and rotates one stage per cycle, wrapping 20 -> 1.
    assert all(v.bit_count() == 1 for v in vals), vals
    for k in range(len(vals) - 1):
        assert vals[k + 1] == rotl20(vals[k]), (k, vals[k], vals[k + 1])
    assert vals[20] == 0x1  # full revolution: cycle 21 repeats cycle 1
