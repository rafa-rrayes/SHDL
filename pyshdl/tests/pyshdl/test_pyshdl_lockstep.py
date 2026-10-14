"""Oracle lockstep: Circuit and the BaseEval reference oracle driven through
identical random stimulus, every port compared after every action.

OracleSim wraps BaseEval (``make_oracle``'s evaluator) in the release-ABI
poke/peek discipline, so peeks must interleave identically on both sides —
a peek of a dirty output is itself a stimulus (the lazy evaluation cycle).
"""

from __future__ import annotations

import random

import pytest

from conformance.runner.oracle import OracleSim

FIXTURES = ["adder8", "mux2", "srLatch", "dLatch"]


@pytest.mark.parametrize("name", FIXTURES)
def test_random_stimulus_lockstep(examples, name):
    oracle = OracleSim(examples.base_text(name))
    rng = random.Random(f"pyshdl-lockstep-{name}")
    with examples.fresh(name, strict=False) as circuit:
        ports = (*circuit.inputs, *circuit.outputs)
        for action_no in range(150):
            roll = rng.random()
            if roll < 0.55:
                port = rng.choice(circuit.inputs)
                value = rng.randrange(1 << 66)  # often over-wide: masking in lockstep
                circuit.poke(port, value)
                oracle.poke(port, value)
            elif roll < 0.92:
                cycles = rng.randrange(5)
                circuit.step(cycles)
                oracle.step(cycles)
            else:
                circuit.reset()
                oracle.reset()
            for port in ports:
                got, want = circuit.peek(port), oracle.peek(port)
                assert got == want, f"{name}: action {action_no}, port {port}: {got} != {want}"
