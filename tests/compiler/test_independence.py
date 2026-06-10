"""Library instance isolation.

All compiled circuits export the same four symbol names; per-handle dlsym
(RTLD_LOCAL) must keep simultaneously loaded libraries fully independent.
Two instances of the SAME circuit additionally require distinct file paths,
because dlopen caches by path (see harness.load_fresh_copy).
"""

from __future__ import annotations

import random


def test_two_different_circuits_loaded_simultaneously(builds):
    dual_a = builds.dual_fixture("add2", seed="independence-add2")
    dual_s = builds.dual_fixture("srlatch", seed="independence-srlatch")
    rng = random.Random(0xADD2_57A7)
    for _ in range(40):
        if rng.random() < 0.6:
            dual_a.poke(rng.choice(dual_a.in_ports), rng.getrandbits(64))
        if rng.random() < 0.6:
            dual_s.poke(rng.choice(dual_s.in_ports), rng.getrandbits(64))
        # Interleave the stepping; each lib must track its OWN oracle.
        dual_a.step_compare(1)
        dual_s.step_compare(1)


def test_two_copies_of_same_circuit_are_independent(builds):
    # Each dual_fixture call loads a brand-new file copy of the dylib.
    dual1 = builds.dual_fixture("add2", seed="copy-1")
    dual2 = builds.dual_fixture("add2", seed="copy-2")
    assert dual1.sim.path != dual2.sim.path  # same path would dlopen-cache

    # Drive them to provably different states (1+2+0=3 vs 2+2+0=4).
    for port, v in [("A", 1), ("B", 2), ("Cin", 0)]:
        dual1.poke(port, v)
    for port, v in [("A", 2), ("B", 2), ("Cin", 0)]:
        dual2.poke(port, v)
    dual1.step_compare(6)
    dual2.step_compare(6)
    assert dual1.sim.peek("Sum") == 3 and dual1.sim.peek("Cout") == 0
    assert dual2.sim.peek("Sum") == 0 and dual2.sim.peek("Cout") == 1

    # Driving one further must not disturb the other.
    dual2.poke("A", 3)
    dual2.step_compare(6)
    assert dual1.sim.peek("Sum") == 3 and dual1.sim.peek("Cout") == 0
    dual1.compare_all()  # still bit-exact against its own oracle
