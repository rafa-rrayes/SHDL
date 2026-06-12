"""Random VALID Base SHDL netlists for differential fuzzing.

``gen_circuit`` builds a netlist that satisfies every structural invariant of
shdlc.model by construction (single driver per pin/output, no floating pins,
partitioned meta.ports of width 1..64, init seeds on gate outputs only), then
self-checks it through parse_base + BaseEval before returning the text.

Gates are wired DAG-by-construction (gate k only reads inputs and gates with
index < k); with probability 0.5 some gate input pins are then rewired to
arbitrary gates, creating feedback loops — well-defined under the unit-delay
model (shdl.md §11.2).
"""

from __future__ import annotations

import json
import random

from shdlc.baseshdl import parse_base
from shdlc.sim.base_eval import BaseEval

_GATES2 = ("AND", "OR", "XOR")


def gen_circuit(rng: random.Random) -> str:
    """Generate one random, valid Base SHDL artifact (text with meta)."""
    inputs = [f"in{k}" for k in range(rng.randint(1, 8))]
    n_gates = rng.randint(5, 80)

    types: list[str] = []
    for _ in range(n_gates):
        r = rng.random()
        if r < 0.04:
            types.append("__VCC__")
        elif r < 0.08:
            types.append("__GND__")
        elif r < 0.30:
            types.append("NOT")
        else:
            types.append(rng.choice(_GATES2))

    def pick_src(k: int) -> str:
        # DAG by construction: only inputs or earlier gates.
        if k > 0 and rng.random() < 0.7:
            return f"g{rng.randrange(k)}.O"
        return rng.choice(inputs)

    pins: dict[tuple[int, str], str] = {}
    for k, t in enumerate(types):
        if t in _GATES2:
            pins[(k, "A")] = pick_src(k)
            pins[(k, "B")] = pick_src(k)
        elif t == "NOT":
            pins[(k, "A")] = pick_src(k)

    # Feedback: rewire some gate inputs to arbitrary (possibly later) gates.
    if pins and rng.random() < 0.5:
        keys = sorted(pins)  # deterministic order before sampling
        for key in rng.sample(keys, k=rng.randint(1, max(1, len(keys) // 6))):
            pins[key] = f"g{rng.randrange(n_gates)}.O"

    outputs = [f"out{j}" for j in range(rng.randint(1, 12))]
    out_src = {w: f"g{rng.randrange(n_gates)}.O" for w in outputs}
    if rng.random() < 0.5:  # sometimes include an input->output passthrough
        w = f"out{len(outputs)}"
        outputs.append(w)
        out_src[w] = rng.choice(inputs)

    def group(wires: list[str], prefix: str) -> dict[str, list[str]]:
        # Partition shuffled wires into ports of width 1..64, LSB-first lists.
        pool = wires[:]
        rng.shuffle(pool)
        ports: dict[str, list[str]] = {}
        n = 0
        while pool:
            w = rng.randint(1, min(64, len(pool)))
            ports[f"{prefix}{n}"] = pool[:w]
            pool = pool[w:]
            n += 1
        return ports

    meta: dict = {"ports": {"inputs": group(inputs, "PI"), "outputs": group(outputs, "PO")}}
    n_seeds = rng.randint(0, max(1, n_gates // 5))
    if n_seeds:
        seeded = sorted(rng.sample(range(n_gates), k=n_seeds))
        meta["init"] = {f"g{k}.O": rng.randint(0, 1) for k in seeded}

    lines = [f"component Fuzz({', '.join(inputs)}) -> ({', '.join(outputs)}) {{"]
    for k, t in enumerate(types):
        lines.append(f"    g{k}: {t};")
    lines.append("    connect {")
    for k in range(len(types)):
        for pin in ("A", "B"):
            if (k, pin) in pins:
                lines.append(f"        {pins[(k, pin)]} -> g{k}.{pin};")
    for w in outputs:
        lines.append(f"        {out_src[w]} -> {w};")
    lines.append("    }")
    lines.append("}")
    text = "\n".join(lines) + "\nmeta " + json.dumps(meta, indent=2) + "\n"

    _self_check(text, rng)
    return text


def _self_check(text: str, rng: random.Random) -> None:
    """The generated text must parse and run under BaseEval before use."""
    comp = parse_base(text)
    oracle = BaseEval(comp)
    ports = comp.meta["ports"]
    for name, wires in ports["inputs"].items():
        oracle.poke(name, rng.getrandbits(len(wires)))
    oracle.step(3)
    for name in (*ports["inputs"], *ports["outputs"]):
        oracle.peek(name)
    oracle.reset()
    oracle.step(1)
