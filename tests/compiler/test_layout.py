"""Planner invariants for :mod:`shdlc.layout`, proven in pure Python.

A tiny evaluator mirrors what the emitted C does with a word's gather groups
(shift / broadcast / mask), so the placement and the masking rules are
checked against gate-by-gate truth on random states without compiling
anything. Circuits are built by hand or string-built Base SHDL.
"""

from __future__ import annotations

import random

from shdlc.baseshdl import parse_base
from shdlc.layout import FULL, LANES, Gather, Group, Layout, Word, plan, stats
from shdlc.model import Circuit, Gate, PortGroup, Ref, build_circuit

_OPS = {"AND": lambda a, b: a & b, "OR": lambda a, b: a | b, "XOR": lambda a, b: a ^ b}


def _in(n: int) -> Ref:
    return Ref("in", n)


def _g(n: int) -> Ref:
    return Ref("gate", n)


def _circuit(name="C", inputs=(), gates=(), outputs=(), in_ports=(), out_ports=(), init=()):
    return Circuit(
        name=name,
        inputs=tuple(inputs),
        gates=tuple(gates),
        outputs=tuple(outputs),
        in_ports=tuple(in_ports),
        out_ports=tuple(out_ports),
        init=tuple(init),
    )


def random_netlist(n: int, seed: int, n_in: int = 16) -> str:
    """Base SHDL with random gate types and uniformly random operands: the
    packing worst case (nothing lines up)."""
    rng = random.Random(seed)
    ins = [f"a{i}" for i in range(n_in)]
    decls, conns, srcs = [], [], list(ins)
    for i in range(n):
        t = rng.choice(["AND", "OR", "XOR", "NOT"])
        decls.append(f"    g{i}: {t};")
        for p in ["A"] if t == "NOT" else ["A", "B"]:
            conns.append(f"        {rng.choice(srcs)} -> g{i}.{p};")
        srcs.append(f"g{i}.O")
    outs = [f"y{k}" for k in range(8)]
    conns.extend(f"        g{n - 1 - k}.O -> {o};" for k, o in enumerate(outs))
    ports = (
        '{ "ports": { "inputs": { "A": ['
        + ", ".join(f'"{x}"' for x in ins)
        + '] }, "outputs": { "Y": ['
        + ", ".join(f'"{x}"' for x in outs)
        + "] } } }"
    )
    return (
        f"component Rand({', '.join(ins)}) -> ({', '.join(outs)}) {{\n"
        + "\n".join(decls)
        + "\n    connect {\n"
        + "\n".join(conns)
        + "\n    }\n}\nmeta "
        + ports
        + "\n"
    )


def tree_netlist(width: int) -> str:
    """A ``width``-bit AND bus feeding a pairwise OR reduction tree (the
    shape the placer is tuned for: shift 0 and +stride gathers)."""
    ins = [f"a{i}" for i in range(width)] + [f"b{i}" for i in range(width)]
    decls = [f"    x{i}: AND;" for i in range(width)]
    conns = [f"        a{i} -> x{i}.A;\n        b{i} -> x{i}.B;" for i in range(width)]
    level = [f"x{i}" for i in range(width)]
    depth = 0
    while len(level) > 1:
        nxt = []
        for k in range(0, len(level) - 1, 2):
            name = f"t{depth}_{k // 2}"
            decls.append(f"    {name}: OR;")
            conns.append(
                f"        {level[k]}.O -> {name}.A;\n        {level[k + 1]}.O -> {name}.B;"
            )
            nxt.append(name)
        if len(level) % 2:
            nxt.append(level[-1])
        level, depth = nxt, depth + 1
    conns.append(f"        {level[0]}.O -> y;")
    bus = lambda p: ", ".join(f'"{p}{i}"' for i in range(width))  # noqa: E731
    meta = f'meta {{ "ports": {{ "inputs": {{ "A": [{bus("a")}], "B": [{bus("b")}] }}, "outputs": {{ "Y": ["y"] }} }} }}'
    return (
        "\n".join(
            [
                f"component Tree({', '.join(ins)}) -> (y) {{",
                *decls,
                "    connect {",
                *conns,
                "    }",
                "}",
                meta,
            ]
        )
        + "\n"
    )


def hand_circuits() -> list[Circuit]:
    ring = tuple(Gate(f"n{i}", "NOT", _g((i - 1) % 70), None) for i in range(70))
    return [
        _circuit(name="Empty"),
        _circuit(
            name="Power",
            gates=(Gate("p", "VCC", None, None), Gate("z", "GND", None, None)),
            out_ports=(PortGroup("Hi", (_g(0),)), PortGroup("Lo", (_g(1),))),
        ),
        _circuit(
            name="Ring",
            gates=ring,
            out_ports=(PortGroup("o", (_g(0), _g(69))),),
            init=((0, 1),),
        ),
        _circuit(  # wire b is covered by no port: stuck at 0
            name="Stuck",
            inputs=("a", "b"),
            gates=(Gate("g", "OR", _in(0), _in(1)), Gate("h", "XOR", _in(1), _in(0))),
            in_ports=(PortGroup("a", (_in(0),)),),
            out_ports=(PortGroup("o", (_g(0), _g(1), _in(1))),),
        ),
        _circuit(  # one select bit fanning out over a bus
            name="Fanout",
            inputs=("s", "d0", "d1", "d2"),
            gates=tuple(Gate(f"a{k}", "OR", _in(0), _in(1 + k)) for k in range(3)),
            in_ports=(PortGroup("S", (_in(0),)), PortGroup("D", (_in(1), _in(2), _in(3)))),
            out_ports=(PortGroup("Y", (_g(2), _g(0), _g(1))),),
        ),
    ]


def text_circuits() -> list[Circuit]:
    texts = [
        random_netlist(300, 1),
        random_netlist(3000, 2, n_in=64),
        tree_netlist(64),
        tree_netlist(37),
    ]
    return [build_circuit(parse_base(t)) for t in texts]


# --- evaluator mirroring the emitted C ------------------------------------------


def _eval_group(g: Group, state: dict) -> int:
    base = state[(g.array, g.index)]
    if g.bcast:
        val = FULL if (base >> g.shift) & 1 else 0
    elif g.shift >= 0:
        val = base >> g.shift
    else:
        val = (base << -g.shift) & FULL
    return val & g.lanes if g.masked else val


def _eval_gather(groups: tuple[Group, ...], state: dict) -> int:
    val = 0
    for g in groups:
        val |= _eval_group(g, state)
    return val


def _eval_word(word: Word, state: dict) -> int:
    if word.type in _OPS:
        r = _OPS[word.type](_eval_gather(word.a, state), _eval_gather(word.b, state))
    elif word.type == "NOT":
        r = ~_eval_gather(word.a, state) & FULL
    elif word.type == "VCC":
        r = word.mask
    else:
        assert word.type == "GND"
        r = 0
    return r & word.mask if word.masked else r


def _eval_output(gather: Gather, state: dict) -> int:
    r = _eval_gather(gather.groups, state)
    return r & gather.mask if gather.masked else r


def _source_bit(circuit: Circuit, layout: Layout, state: dict, ref: Ref | None) -> int:
    if ref is None:
        return 0
    if ref.kind == "in":
        at = layout.in_place[ref.index]
        return 0 if at is None else (state[("in", at[0])] >> at[1]) & 1
    w, lane = layout.place[ref.index]
    return (state[("c", w)] >> lane) & 1


def _truth(circuit: Circuit, layout: Layout, state: dict) -> list[int]:
    bits = []
    for gate in circuit.gates:
        a = _source_bit(circuit, layout, state, gate.a)
        b = _source_bit(circuit, layout, state, gate.b)
        if gate.type in _OPS:
            bits.append(_OPS[gate.type](a, b))
        elif gate.type == "NOT":
            bits.append(a ^ 1)
        else:
            bits.append(1 if gate.type == "VCC" else 0)
    return bits


def _random_state(circuit: Circuit, layout: Layout, rng: random.Random) -> dict:
    """Committed words and input words: random within the used lanes, zero
    elsewhere (the invariant both buffers keep)."""
    state = {("c", w): rng.getrandbits(LANES) & word.mask for w, word in enumerate(layout.words)}
    for p, port in enumerate(circuit.in_ports):
        state[("in", p)] = rng.getrandbits(LANES) & ((1 << len(port.refs)) - 1)
    return state


# --- tests ------------------------------------------------------------------------


def _all() -> list[Circuit]:
    return hand_circuits() + text_circuits()


def test_every_gate_placed_once_in_a_word_of_its_type():
    for circuit in _all():
        layout = plan(circuit)
        assert len(layout.place) == len(circuit.gates)
        seen = set()
        for g, (w, lane) in enumerate(layout.place):
            assert 0 <= lane < LANES
            assert (w, lane) not in seen
            seen.add((w, lane))
            word = layout.words[w]
            assert word.type == circuit.gates[g].type
            assert (lane, g) in word.gates
            assert word.mask >> lane & 1
        for w, word in enumerate(layout.words):
            assert word.gates, "empty word"
            assert list(word.gates) == sorted(word.gates)
            assert word.mask == sum(1 << lane for lane, _ in word.gates)
            assert all(layout.place[g] == (w, lane) for lane, g in word.gates)
        for ref in (ref for p in circuit.in_ports for ref in p.refs):
            assert layout.in_place[ref.index] is not None
        covered = {ref.index for p in circuit.in_ports for ref in p.refs}
        for i, at in enumerate(layout.in_place):
            assert (at is not None) == (i in covered)


def test_groups_are_well_formed_and_cover_exactly_the_sourced_lanes():
    for circuit in _all():
        layout = plan(circuit)
        gathers = [(word.a, word.mask) for word in layout.words] + [
            (word.b, word.mask) for word in layout.words
        ]
        gathers += [(o.groups, o.mask) for o in layout.outputs]
        for groups, mask in gathers:
            covered = 0
            for g in groups:
                assert g.array in ("c", "in")
                assert g.lanes and g.lanes & ~mask == 0
                assert g.lanes & covered == 0, "overlapping groups"
                covered |= g.lanes
                assert 0 <= g.shift < LANES if g.bcast else -LANES < g.shift < LANES
                if g.array == "c":
                    assert 0 <= g.index < len(layout.words)
                else:
                    assert 0 <= g.index < len(circuit.in_ports)


def test_words_and_outputs_match_gate_by_gate_truth_on_random_states():
    rng = random.Random(2024)
    for circuit in _all():
        layout = plan(circuit)
        for _ in range(25):
            state = _random_state(circuit, layout, rng)
            truth = _truth(circuit, layout, state)
            for w, word in enumerate(layout.words):
                want = sum(truth[g] << lane for lane, g in word.gates)
                got = _eval_word(word, state)
                assert got == want, (circuit.name, w, word)
                assert got & ~word.mask == 0
            for q, port in enumerate(circuit.out_ports):
                want = sum(
                    _source_bit(circuit, layout, state, ref) << b for b, ref in enumerate(port.refs)
                )
                assert _eval_output(layout.outputs[q], state) == want, (circuit.name, port.name)


def test_masks_are_only_where_junk_could_reach_a_used_lane():
    # Truth on random states (above) proves every mask that *is* there
    # suffices; this pins that the placer also leaves masks *out* where it
    # can. The AND bus reads two whole input words: one unmasked shift-0
    # group each, no word mask. The OR tree packs into one full word whose
    # per-group masks keep the result clean, so it needs no word mask
    # either -- and nothing needs a third word.
    layout = plan(build_circuit(parse_base(tree_netlist(64))))
    st = stats(layout)
    assert st["gates"] == 127 and st["words"] == 2
    assert st["masked_words"] == 0
    bus, tree = layout.words
    assert bus.type == "AND" and len(bus.gates) == LANES and not bus.masked
    assert [(g.array, g.index, g.shift, g.masked) for g in bus.a] == [("in", 0, 0, False)]
    assert [(g.array, g.index, g.shift, g.masked) for g in bus.b] == [("in", 1, 0, False)]
    assert tree.type == "OR" and len(tree.gates) == 63 and not tree.masked
    assert all(g.masked for g in tree.a + tree.b)


def test_plan_is_deterministic():
    for circuit in _all():
        assert plan(circuit) == plan(circuit)


def test_stats_keys():
    st = stats(plan(hand_circuits()[2]))
    assert st["gates"] == 70 and st["words"] == 2 and st["lane_use"] > 0.5
    assert set(st) >= {"groups", "groups_per_word", "bcast_groups", "masked_groups", "full_words"}
