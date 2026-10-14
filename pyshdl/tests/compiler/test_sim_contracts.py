"""Simulation-model contracts: order independence, input persistence, 2-state.

- SIM-6: compute-commit order independence. Permuting the declaration order of
  instances and connections in a netlist (including feedback ones) yields
  byte-identical port traces -- the unit-delay model reads only the previous
  committed cycle, so evaluation order within a cycle is irrelevant.
- SIM-11: input persistence (shdl.md §11.1). A poked input holds its value
  across cycles until changed; dependent outputs stay consistent.
- SIM-10: 2-state guarantee. No single-bit wire ever shows a value other than
  0 or 1, under arbitrary drive. (Cheaply assertable at the port boundary;
  full internal-gate assertion is staged for the debug build, FUT V.1.)
"""

from __future__ import annotations

import random
import zlib

import pytest

from shdlc.sim.base_eval import BaseEval

from .harness import make_oracle, parse_with_ports

# ---------------------------------------------------------------------------
# SIM-6: order independence over permuted declarations.
# ---------------------------------------------------------------------------

# A combinational netlist (1-bit full-adder core) written two ways: a
# "canonical" declaration/connection order and a deliberately scrambled one.
# Same gates, same wiring -- only textual order differs.
FA_CANONICAL = """\
component FA(a, b, cin) -> (sum, cout) {
    x1: XOR;
    x2: XOR;
    a1: AND;
    a2: AND;
    o1: OR;
    connect {
        a -> x1.A; b -> x1.B;
        x1.O -> x2.A; cin -> x2.B;
        x1.O -> a1.A; cin -> a1.B;
        a -> a2.A; b -> a2.B;
        a1.O -> o1.A; a2.O -> o1.B;
        x2.O -> sum;
        o1.O -> cout;
    }
}
meta { "ports": { "inputs": { "A": ["a"], "B": ["b"], "Cin": ["cin"] },
                  "outputs": { "Sum": ["sum"], "Cout": ["cout"] } } }
"""

FA_SCRAMBLED = """\
component FA(a, b, cin) -> (sum, cout) {
    o1: OR;
    a2: AND;
    x2: XOR;
    a1: AND;
    x1: XOR;
    connect {
        o1.O -> cout;
        a2.O -> o1.B; a1.O -> o1.A;
        a -> a2.A; b -> a2.B;
        cin -> x2.B; x1.O -> x2.A;
        cin -> a1.B; x1.O -> a1.A;
        b -> x1.B; a -> x1.A;
        x2.O -> sum;
    }
}
meta { "ports": { "inputs": { "A": ["a"], "B": ["b"], "Cin": ["cin"] },
                  "outputs": { "Sum": ["sum"], "Cout": ["cout"] } } }
"""

# A feedback netlist (SR latch from cross-coupled NOR = OR+NOT), canonical and
# scrambled. Feedback makes order independence non-trivial: a same-cycle read
# of a not-yet-committed value would diverge under reordering.
SR_CANONICAL = """\
component SR(s, r) -> (q, qn) {
    or1: OR;
    n1: NOT;
    or2: OR;
    n2: NOT;
    connect {
        s -> or1.A; n2.O -> or1.B;
        or1.O -> n1.A;
        r -> or2.A; n1.O -> or2.B;
        or2.O -> n2.A;
        n1.O -> q;
        n2.O -> qn;
    }
}
meta { "ports": { "inputs": { "S": ["s"], "R": ["r"] },
                  "outputs": { "Q": ["q"], "Qn": ["qn"] } },
       "init": { "q": 0, "qn": 1 } }
"""

SR_SCRAMBLED = """\
component SR(s, r) -> (q, qn) {
    n2: NOT;
    or2: OR;
    n1: NOT;
    or1: OR;
    connect {
        n2.O -> qn;
        n1.O -> q;
        or2.O -> n2.A;
        n1.O -> or2.B; r -> or2.A;
        or1.O -> n1.A;
        n2.O -> or1.B; s -> or1.A;
    }
}
meta { "ports": { "inputs": { "S": ["s"], "R": ["r"] },
                  "outputs": { "Q": ["q"], "Qn": ["qn"] } },
       "init": { "q": 0, "qn": 1 } }
"""


def _drive_trace(oracle: BaseEval, in_ports, out_ports, script, *, settle_each=1):
    """Run a poke/step script on an oracle, recording every output each step."""
    trace = []
    for pokes in script:
        for port, val in pokes.items():
            oracle.poke(port, val)
        oracle.step(settle_each)
        trace.append(tuple(oracle.peek(p) for p in out_ports))
    return trace


@pytest.mark.parametrize(
    ("canon", "scrambled", "in_ports", "out_ports", "feedback"),
    [
        (FA_CANONICAL, FA_SCRAMBLED, ("A", "B", "Cin"), ("Sum", "Cout"), False),
        (SR_CANONICAL, SR_SCRAMBLED, ("S", "R"), ("Q", "Qn"), True),
    ],
    ids=["combinational-fa", "feedback-srlatch"],
)
def test_declaration_order_independence_oracle(canon, scrambled, in_ports, out_ports, feedback):
    # SIM-6: identical port traces under permuted declaration/connection order.
    # Done at the oracle level, where "compute then commit" is the contract;
    # the lib's order independence rides on this plus its lockstep tests.
    seed = zlib.crc32(("SIM-6-" + out_ports[0]).encode())
    rng = random.Random(seed)
    script = []
    for _ in range(60):
        pokes = {p: rng.getrandbits(1) for p in in_ports if rng.random() < 0.6}
        script.append(pokes)

    a = make_oracle(canon)
    b = make_oracle(scrambled)
    # Power-on (init) state must already agree, before any drive.
    assert tuple(a.peek(p) for p in out_ports) == tuple(b.peek(p) for p in out_ports)
    trace_a = _drive_trace(a, in_ports, out_ports, script)
    # Re-run the SAME script on the scrambled netlist.
    b = make_oracle(scrambled)
    trace_b = _drive_trace(b, in_ports, out_ports, script)
    assert trace_a == trace_b, (
        f"order-dependence detected ({'feedback' if feedback else 'comb'}): "
        f"first divergence at step "
        f"{next(i for i, (x, y) in enumerate(zip(trace_a, trace_b)) if x != y)}\n"
        f"script={script}"
    )


def test_order_independence_lockstep_lib_vs_oracle(builds):
    # SIM-6 at the compiled-library level: the scrambled feedback netlist runs
    # bit-exactly against its own BaseEval, every port every cycle. The two
    # texts produce structurally different C (declaration order is preserved in
    # codegen) yet identical observable behavior.
    import random as _random

    dual_c = builds.dual_from_text("sim6-canon", SR_CANONICAL, seed="sim6-canon")
    dual_s = builds.dual_from_text("sim6-scram", SR_SCRAMBLED, seed="sim6-scram")
    dual_c.compare_all()
    dual_s.compare_all()
    rng = _random.Random(zlib.crc32(b"SIM-6-lockstep"))
    for _ in range(60):
        for port in ("S", "R"):
            if rng.random() < 0.5:
                dual_c.poke(port, rng.getrandbits(1))
        for port in ("S", "R"):
            if rng.random() < 0.5:
                dual_s.poke(port, rng.getrandbits(1))
        dual_c.step_compare(1)
        dual_s.step_compare(1)


# ---------------------------------------------------------------------------
# SIM-11: input persistence.
# ---------------------------------------------------------------------------


def test_input_persists_across_cycles_until_changed(builds):
    # shdl.md §11.1: a poked input holds across cycles. Poke once, then step
    # repeatedly with NO further pokes; the input peek must read the same value
    # every cycle, and the dependent output must stay consistent with it.
    dual = builds.dual_fixture("add2")
    dual.poke("A", 3)
    dual.poke("B", 1)
    dual.poke("Cin", 0)
    # Step well past the circuit's depth; inputs must not decay.
    for _ in range(10):
        dual.step_compare(1)
        # Input peeks (never tick) read the held value on both sides.
        assert dual.sim.peek("A") == 3
        assert dual.sim.peek("B") == 1
        assert dual.sim.peek("Cin") == 0
    # After settling: 3 + 1 = 0b100 -> Sum=0, Cout=1, held stable.
    assert dual.sim.peek("Sum") == 0
    assert dual.sim.peek("Cout") == 1


def test_input_persistence_named_contract_handwritten(builds):
    # SIM-11 on a minimal AND: held inputs keep the output pinned across many
    # cycles with no re-poke, then a single re-poke changes it.
    from .harness import AND_TEXT

    sim = builds.sim_from_text("hand_and", AND_TEXT)
    oracle = make_oracle(AND_TEXT)
    sim.poke("a", 1)
    sim.poke("b", 1)
    oracle.poke("a", 1)
    oracle.poke("b", 1)
    for _ in range(8):
        sim.step(1)
        oracle.step(1)
        assert sim.peek("a") == 1 and sim.peek("b") == 1  # never decay
        assert sim.peek("y") == oracle.peek("y") == 1
    # Change exactly one input: persistence ends only on an explicit poke.
    sim.poke("b", 0)
    oracle.poke("b", 0)
    sim.step(1)
    oracle.step(1)
    assert sim.peek("y") == oracle.peek("y") == 0


# ---------------------------------------------------------------------------
# SIM-10: 2-state guarantee at the port boundary.
# ---------------------------------------------------------------------------


def test_single_bit_wires_are_always_two_state(builds):
    # SIM-10 (cheaply assertable half): every single-bit port reads exactly 0
    # or 1, under randomized drive across feedback transients. The guarantee
    # comes from the poke per-bit `&1u` scatter plus Boolean closure of the
    # gate ops; here we witness it never producing a non-Boolean at a 1-bit
    # port. (Full internal-gate coverage is staged in FUT V.1's debug build.)
    comp = parse_with_ports(builds.fixture_text("srlatch"))
    ports = comp.meta["ports"]
    single_bit = [
        p for grp in ("inputs", "outputs") for p, wires in ports[grp].items() if len(wires) == 1
    ]
    assert single_bit, "expected single-bit ports on srlatch"
    sim = builds.sim_fixture("srlatch")
    rng = random.Random(zlib.crc32(b"SIM-10-srlatch"))
    for _ in range(120):
        for p in ("S", "R"):
            if rng.random() < 0.5:
                sim.poke(p, rng.getrandbits(1))
        sim.step(1)
        for p in single_bit:
            v = sim.peek(p)
            assert v in (0, 1), f"port {p!r} showed non-2-state value {v:#x}"
