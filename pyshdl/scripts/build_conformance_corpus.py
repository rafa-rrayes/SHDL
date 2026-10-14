"""One-shot authoring script for the conformance corpus (provenance record).

This script created the committed contents of ``conformance/cases/`` and
``conformance/MANIFEST.json``. It is kept in the repository as the durable
record of where every golden came from:

- ``expected.base.shdl``: ``flatten_program`` over the case's ``circuit.shdl``
  with the suite-wide pinned timestamp;
- trace ``expect`` values: :func:`conformance.runner.gen.fill_trace_ops`,
  i.e. the BaseEval-backed OracleSim — never the C implementation under test;
- ``step`` counts marked SETTLE below: the flattened circuit's
  ``timing.max_depth`` at authoring time, baked into the committed JSON.

It is NOT part of the maintenance loop. Goldens are frozen; after authoring,
the only sanctioned writer is ``shdl-conformance regen --case NAME --write``
(single case, reviewable diff). Re-running this script wholesale is the
"regenerate everything" anti-pattern the suite's policy forbids — do that
only for a deliberate, changelogged major version bump.

Run from the repo root:  uv run python scripts/build_conformance_corpus.py
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from conformance.runner.gen import fill_trace_ops, trace_json_text  # noqa: E402
from conformance.runner.schema import load_suite  # noqa: E402
from flattener.pipeline import flatten_program  # noqa: E402
from shdlc.baseshdl import parse_base  # noqa: E402

CONF = REPO / "conformance"
CASES = CONF / "cases"
TS = "2026-01-01T00:00:00Z"
SUITE_VERSION = "1.0.0"
CREATED = "2026-06-10"

PROV_BASE = (
    f"flattener flatten_program(circuit.shdl, timestamp={TS!r}) at suite v{SUITE_VERSION} "
    f"creation ({CREATED}); reviewed and frozen — modified only via 'shdl-conformance regen'"
)
PROV_TRACES = (
    "expect values computed by conformance.runner.oracle.OracleSim (the BaseEval "
    "reference oracle with release-ABI peek/poke discipline) replaying the ops over "
    "the frozen expected.base.shdl; never taken from the C implementation under test"
)

# --- op constructors -------------------------------------------------------

SETTLE = "SETTLE"  # replaced at build time with max(1, timing.max_depth)


def R() -> dict:
    return {"op": "reset"}


def P(signal: str, value: int) -> dict:
    return {"op": "poke", "signal": signal, "value": value}


def S(cycles) -> dict:
    return {"op": "step", "cycles": cycles}


def E(signal: str) -> dict:
    return {"op": "expect", "signal": signal, "value": None}  # filled by the oracle


def combo(pokes: dict[str, int], expects: list[str], settle=SETTLE) -> list[dict]:
    """poke each input, settle, observe each output — the Tier B idiom."""
    return [P(s, v) for s, v in pokes.items()] + [S(settle)] + [E(s) for s in expects]


@dataclass(frozen=True)
class TraceDef:
    name: str
    tier: str
    description: str
    ops: list


@dataclass(frozen=True)
class CaseDef:
    name: str
    title: str
    description: str
    tiers: tuple[str, ...]
    features: tuple[str, ...]
    # dest file name -> repo-relative source path, or ("inline", text)
    sources: dict[str, object]
    traces: list[TraceDef] = field(default_factory=list)
    top: str | None = None


# --------------------------------------------------------------------------
# Hand-authored circuits (committed into their case dirs by this script).
# --------------------------------------------------------------------------

ALLGATES_SHDL = '''\
"""Conformance: every primitive gate type observable in one circuit."""

top component AllGates(A, B) -> (AndO, OrO, XorO, NotO, Hi, Lo) {
    g1: AND;  g2: OR;  g3: XOR;  g4: NOT;
    hi: __VCC__;  lo: __GND__;

    connect {
        A -> g1.A;  B -> g1.B;  g1.O -> AndO;
        A -> g2.A;  B -> g2.B;  g2.O -> OrO;
        A -> g3.A;  B -> g3.B;  g3.O -> XorO;
        A -> g4.A;  g4.O -> NotO;
        hi.O -> Hi;
        lo.O -> Lo;
    }
}
'''

REPEATED_NAMES_SHDL = '''\
"""Conformance: the same instance name in sibling scopes must uniquify.

Each Cell owns a gate named `g`, and the top level declares its own `g`;
after flattening, three distinct NOT gates must survive (O = NOT^3(A)).
"""

component Cell(In) -> (Out) {
    g: NOT;
    connect { In -> g.A;  g.O -> Out; }
}

top component RepeatedNames(A) -> (O) {
    c1: Cell;  c2: Cell;  g: NOT;

    connect {
        A -> c1.In;
        c1.Out -> c2.In;
        c2.Out -> g.A;
        g.O -> O;
    }
}
'''

ADDER_N_MIXED_SHDL = '''\
"""Conformance: one generator-and-conditional component at two bindings.

AdderN's ripple loop uses `>i[N]` with a `when {i == 1} / else` boundary;
instantiating it at N = 2 and N = 3 in one artifact pins that generators and
conditionals elaborate correctly per binding.
"""

use adderN::{AdderN};

top component AdderNMixed(A[2], B[2], C[3], D[3]) -> (SumS[2], CoutS, SumL[3], CoutL) {
    small: AdderN<N = 2>;
    large: AdderN<N = 3>;
    z: __GND__;

    connect {
        A -> small.A;  B -> small.B;  z.O -> small.Cin;
        small.Sum -> SumS;  small.Cout -> CoutS;

        C -> large.A;  D -> large.B;  z.O -> large.Cin;
        large.Sum -> SumL;  large.Cout -> CoutL;
    }
}
'''

MASK_PROBE_SHDL = '''\
"""Conformance: pure 2-bit passthrough; the ABI poke-masking probe."""

top component MaskProbe(In[2]) -> (Out[2]) {
    connect { In -> Out; }
}
'''

VCC_PROBE_SHDL = '''\
"""Conformance: __VCC__ reads 0 at cycle 0 and 1 from cycle 1 on.

The NOT tap sees the cycle-0 zero exactly once, so HiInv goes 0, 1, 0, ...
— a trace only a faithful unit-delay implementation reproduces.
"""

top component VccProbe() -> (Hi, HiInv) {
    v: __VCC__;
    n: NOT;

    connect {
        v.O -> Hi;
        v.O -> n.A;
        n.O -> HiInv;
    }
}
'''


# --------------------------------------------------------------------------
# The corpus.
# --------------------------------------------------------------------------

FIX = "tests/fixtures"
EX = "examples"

CASE_DEFS: list[CaseDef] = [
    # --- degenerate shapes + primitives ------------------------------------
    CaseDef(
        name="passthru_wire",
        title="Gate-light passthrough through two levels of wire-only hierarchy",
        description=(
            "PassThru routes a 2-bit input through nested wire-only components "
            "(Wire2 wrapping Wire1) plus one XOR; the degenerate near-empty shape "
            "every flattener must get right."
        ),
        tiers=("A", "B"),
        features=("degenerate:passthru", "lang:hierarchy", "lang:multibit-ports"),
        sources={"circuit.shdl": f"{FIX}/passthru.shdl"},
        traces=[
            TraceDef(
                "exhaustive",
                "B",
                "All four values of A; B mirrors A and C is the parity A[1] XOR A[2].",
                [R(), E("B"), E("C")] + sum((combo({"A": a}, ["B", "C"]) for a in range(4)), []),
            )
        ],
    ),
    CaseDef(
        name="single_gate",
        title="Single NOT gate (Inverter)",
        description=(
            "The smallest non-trivial circuit: one NOT. The trace observes cycle 0 "
            "(gate state 0 before any tick) before letting the gate evaluate."
        ),
        tiers=("A", "B"),
        features=("degenerate:single-gate", "primitive:not"),
        sources={"circuit.shdl": f"{EX}/inverter.shdl"},
        traces=[
            TraceDef(
                "cycle_semantics",
                "B",
                "O is 0 at cycle 0 (no tick yet), 1 after one cycle with A=0, then follows NOT A.",
                [R(), E("O"), S(1), E("O"), P("A", 1), S(1), E("O"), P("A", 0), S(1), E("O")],
            )
        ],
    ),
    CaseDef(
        name="primitives_all",
        title="All six primitives in one circuit",
        description=(
            "Hand-authored AllGates exposes AND, OR, XOR, NOT plus __VCC__ and "
            "__GND__ directly on output ports; the truth-table trace pins each "
            "primitive's operator."
        ),
        tiers=("A", "B"),
        features=(
            "primitive:and",
            "primitive:or",
            "primitive:xor",
            "primitive:not",
            "primitive:vcc",
            "primitive:gnd",
        ),
        sources={"circuit.shdl": ("inline", ALLGATES_SHDL)},
        traces=[
            TraceDef(
                "truth_tables",
                "B",
                "All four (A, B) combinations after settling; Hi/Lo pin VCC=1, GND=0.",
                [R(), S(1)]
                + sum(
                    (
                        combo({"A": a, "B": b}, ["AndO", "OrO", "XorO", "NotO", "Hi", "Lo"])
                        for a, b in ((0, 0), (0, 1), (1, 0), (1, 1))
                    ),
                    [],
                ),
            ),
            TraceDef(
                "cycle0",
                "B",
                "At cycle 0 every gate output reads 0 — including __VCC__ — until the first tick.",
                [R(), E("Hi"), E("Lo"), E("NotO"), S(1), E("Hi"), E("NotO")],
            ),
        ],
    ),
    CaseDef(
        name="derived_gates",
        title="Derived gates NAND/NOR/XNOR from the stdgates library",
        description=(
            "GatesDemo imports NAND, NOR, XNOR (each a primitive plus a NOT); "
            "the trace runs their full truth tables."
        ),
        tiers=("A", "B"),
        features=("derived:nand", "derived:nor", "derived:xnor", "lang:imports"),
        sources={
            "circuit.shdl": f"{FIX}/gatesDemo.shdl",
            "stdgates.shdl": f"{FIX}/stdgates.shdl",
        },
        traces=[
            TraceDef(
                "truth_tables",
                "B",
                "All four (A, B) combinations; Na/No/Xn are NAND/NOR/XNOR of A, B.",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b}, ["Na", "No", "Xn"])
                        for a, b in ((0, 0), (0, 1), (1, 0), (1, 1))
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="repeated_names",
        title="Identical instance names in sibling scopes",
        description=(
            "Two Cell instances each own a gate named 'g', and the top level has "
            "its own 'g'; flattening must keep three distinct NOTs (O = NOT^3(A)). "
            "The trace watches the inversion wave cross the chain one gate per cycle."
        ),
        tiers=("A", "B"),
        features=("degenerate:repeated-names", "lang:hierarchy"),
        sources={"circuit.shdl": ("inline", REPEATED_NAMES_SHDL)},
        traces=[
            TraceDef(
                "propagation_wave",
                "B",
                "From all-zero, the three NOTs settle to O=1 over 3 cycles; after "
                "poking A=1 the new wave needs 3 more cycles to reach O=0.",
                [
                    R(),
                    E("O"),
                    S(1),
                    E("O"),
                    S(1),
                    E("O"),
                    S(1),
                    E("O"),
                    S(1),
                    E("O"),
                    P("A", 1),
                    S(1),
                    E("O"),
                    S(1),
                    E("O"),
                    S(1),
                    E("O"),
                    S(1),
                    E("O"),
                ],
            )
        ],
    ),
    # --- buses, slices, constants ------------------------------------------
    CaseDef(
        name="split_byte",
        title="Slices only: a byte split into nibbles with zero gates",
        description=(
            "SplitByte is pure wiring (In[:4] and In[5:8] slices); a zero-gate "
            "circuit is a degenerate shape both the flattener and the ABI must handle."
        ),
        tiers=("A", "B"),
        features=("lang:slices", "degenerate:zero-gate", "lang:multibit-ports"),
        sources={"circuit.shdl": f"{FIX}/splitByte.shdl"},
        traces=[
            TraceDef(
                "nibbles",
                "B",
                "Low/High are the low/high nibble of In for several byte patterns.",
                [R()]
                + sum(
                    (
                        combo({"In": v}, ["Low", "High"], settle=1)
                        for v in (0xA5, 0xF0, 0x0F, 0xFF, 0x00)
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="bus_ops",
        title="Sign extension via replication and concatenation",
        description=(
            "SignExtend builds Out[16] as {8{In[8]}, In}: replication of the sign "
            "bit concatenated with the value, all pure wiring."
        ),
        tiers=("A", "B"),
        features=("lang:replication", "lang:concatenation", "lang:slices", "lang:multibit-ports"),
        sources={"circuit.shdl": f"{EX}/busOps.shdl"},
        traces=[
            TraceDef(
                "sign_extend",
                "B",
                "Negative bytes (MSB set) extend with ones, positive with zeros.",
                [R()]
                + sum(
                    (combo({"In": v}, ["Out"], settle=1) for v in (0x80, 0x7F, 0xA5, 0x00, 0xFF)),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="concat_demo",
        title="Concatenation as source and destination, replication, bare braces",
        description=(
            "ConcatDemo exercises concatenation on both sides of '->', replication "
            "for sign extension, slice items inside braces, and a one-element "
            "concatenation feeding a gate."
        ),
        tiers=("A", "B"),
        features=("lang:concatenation", "lang:replication", "lang:slices"),
        sources={"circuit.shdl": f"{FIX}/concatDemo.shdl"},
        traces=[
            TraceDef(
                "wiring",
                "B",
                "Word/Ext/High/Low are rewirings of In and Sign; X = In[1] XOR Sign.",
                [R()]
                + sum(
                    (
                        combo({"In": i, "Sign": s}, ["Word", "Ext", "High", "Low", "X"])
                        for i, s in ((0b1010, 1), (0b0101, 0), (0b1111, 1), (0b0001, 0))
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="const_demo",
        title="Named constant bits become __VCC__/__GND__ drivers",
        description=(
            "ConstDemo declares FIVE[3] = 5 and reads bits 1, 2 and 9: set bit, "
            "clear bit, and beyond-width bit (reads as 0)."
        ),
        tiers=("A", "B"),
        features=("lang:named-constants", "primitive:vcc", "primitive:gnd"),
        sources={"circuit.shdl": f"{FIX}/constDemo.shdl"},
        traces=[
            TraceDef(
                "const_bits",
                "B",
                "With A=1: O1=FIVE[1]=1, O2=FIVE[2]=0, O3=FIVE[9]=0 (beyond width); all 0 when A=0.",
                [R(), S(SETTLE)]
                + combo({"A": 1}, ["O1", "O2", "O3"])
                + combo({"A": 0}, ["O1", "O2", "O3"]),
            )
        ],
    ),
    CaseDef(
        name="add100",
        title="Adder with one constant operand (Hundred[8] = 100)",
        description=(
            "Add100 wires the bits of a named multi-bit constant into a ripple "
            "adder's B inputs; Sum = A + 100 (mod 256) with Cout the carry."
        ),
        tiers=("A", "B"),
        features=("lang:named-constants", "lang:hierarchy", "lang:imports"),
        sources={
            "circuit.shdl": f"{FIX}/add100.shdl",
            "fullAdder.shdl": f"{FIX}/fullAdder.shdl",
        },
        traces=[
            TraceDef(
                "sums",
                "B",
                "A + 100: 0->100, 100->200, 156->0 carry 1, 255->99 carry 1.",
                [R()]
                + sum(
                    (combo({"A": a}, ["Sum", "Cout"]) for a in (0, 100, 156, 255)),
                    [],
                ),
            )
        ],
    ),
    # --- selection / parameterized -----------------------------------------
    CaseDef(
        name="mux2",
        title="2-to-1 single-bit multiplexer",
        description="Classic AND-OR select logic with fan-out on S.",
        tiers=("A", "B"),
        features=("primitive:and", "primitive:or", "primitive:not"),
        sources={"circuit.shdl": f"{EX}/mux2.shdl"},
        traces=[
            TraceDef(
                "select",
                "B",
                "O follows A when S=0 and B when S=1.",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b, "S": s}, ["O"])
                        for a, b, s in (
                            (1, 0, 0),
                            (1, 0, 1),
                            (0, 1, 0),
                            (0, 1, 1),
                            (1, 1, 1),
                            (0, 0, 0),
                        )
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="mux4n",
        title="4-way 8-bit mux tree (Mux4N over three MuxN instances)",
        description=(
            "Mux4N passes its parameter N straight through to three MuxN children; "
            "S[2] selects among four distinct byte patterns."
        ),
        tiers=("A", "B"),
        features=("lang:hierarchy", "lang:multibit-ports"),
        sources={"circuit.shdl": f"{EX}/muxN.shdl"},
        traces=[
            TraceDef(
                "select_tree",
                "B",
                "With D0..D3 = 0x11/0x22/0x44/0x88, O equals the bus picked by S.",
                [R(), P("D0", 0x11), P("D1", 0x22), P("D2", 0x44), P("D3", 0x88)]
                + sum((combo({"S": s}, ["O"]) for s in range(4)), []),
            )
        ],
    ),
    CaseDef(
        name="comparator",
        title="8-bit equality comparator (XNOR + AND-reduce)",
        description=(
            "EqualN XNORs each bit pair and AND-reduces with a chained generator "
            "using the when/else boundary idiom at N=8."
        ),
        tiers=("A", "B"),
        features=("derived:xnor", "lang:imports"),
        sources={
            "circuit.shdl": f"{EX}/comparator.shdl",
            "stdgates.shdl": f"{EX}/stdgates.shdl",
        },
        traces=[
            TraceDef(
                "equality",
                "B",
                "EQ=1 iff A==B: equal pairs, one-bit difference, full complement.",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b}, ["EQ"])
                        for a, b in ((0, 0), (0xA5, 0xA5), (0xA5, 0xA4), (0xFF, 0x00), (0x80, 0x80))
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="pipe",
        title="Three buffer stages instantiated with a loop-variable parameter",
        description=(
            "Pipe instantiates Stage<W = W, ID = i> inside a generator — the "
            "argument depends on the loop variable, so three distinct bindings "
            "elaborate. The trace watches the 3-cycle latency."
        ),
        tiers=("A", "B"),
        features=("lang:generators-multi-binding", "lang:hierarchy", "lang:multibit-ports"),
        sources={"circuit.shdl": f"{FIX}/pipe.shdl"},
        traces=[
            TraceDef(
                "latency",
                "B",
                "A new In value reaches Out exactly 3 cycles later (one per stage).",
                [
                    R(),
                    P("In", 3),
                    S(1),
                    E("Out"),
                    S(1),
                    E("Out"),
                    S(1),
                    E("Out"),
                    S(1),
                    E("Out"),
                    P("In", 1),
                    S(1),
                    E("Out"),
                    S(1),
                    E("Out"),
                    S(1),
                    E("Out"),
                    S(1),
                    E("Out"),
                ],
            )
        ],
    ),
    CaseDef(
        name="repeater",
        title="Nested generators with arithmetic index expressions",
        description=(
            "Repeater<N=2, M=3> replicates each input bit M times via nested "
            ">i[N]{ >j[M] } loops and the index expression (i-1)*M + j."
        ),
        tiers=("A", "B"),
        features=("lang:nested-generators", "lang:multibit-ports"),
        sources={"circuit.shdl": f"{FIX}/repeater.shdl"},
        traces=[
            TraceDef(
                "replication",
                "B",
                "Out = each In bit repeated 3 times: 1->7 (0b000111), 2->56 (0b111000), 3->63, 0->0.",
                [R()] + sum((combo({"In": v}, ["Out"]) for v in (1, 2, 3, 0)), []),
            )
        ],
    ),
    # --- adders --------------------------------------------------------------
    CaseDef(
        name="full_adder",
        title="Full adder from two half adders",
        description="The canonical hierarchy demo; the trace runs all 8 input combinations.",
        tiers=("A", "B"),
        features=("lang:hierarchy", "primitive:xor", "primitive:and", "primitive:or"),
        sources={"circuit.shdl": f"{FIX}/fullAdder.shdl"},
        traces=[
            TraceDef(
                "truth_table",
                "B",
                "Sum/Cout for every (A, B, Cin).",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b, "Cin": c}, ["Sum", "Cout"])
                        for a in (0, 1)
                        for b in (0, 1)
                        for c in (0, 1)
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="add2",
        title="2-bit ripple-carry adder, explicitly wired",
        description="Two FullAdders chained by hand (no generator).",
        tiers=("A", "B"),
        features=("lang:hierarchy", "lang:imports", "lang:multibit-ports"),
        sources={
            "circuit.shdl": f"{FIX}/add2.shdl",
            "fullAdder.shdl": f"{FIX}/fullAdder.shdl",
        },
        traces=[
            TraceDef(
                "sums",
                "B",
                "Sums covering no carry, internal carry, and carry out.",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b, "Cin": c}, ["Sum", "Cout"])
                        for a, b, c in ((1, 1, 0), (3, 1, 0), (2, 1, 1), (3, 3, 1), (0, 0, 0))
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="adder8_ripple",
        title="8-bit ripple-carry adder with a per-cycle carry-wave trace",
        description=(
            "Adder8 chains eight FullAdders with a generator. Besides settled "
            "sums, the carry_wave trace pokes A=0xFF then Cin=1 and observes "
            "Sum/Cout after every single cycle while the carry ripples down the "
            "chain — the unit-delay fidelity centerpiece."
        ),
        tiers=("A", "B"),
        features=(
            "adder:ripple-carry-per-cycle",
            "lang:hierarchy",
            "lang:imports",
            "lang:multibit-ports",
        ),
        sources={
            "circuit.shdl": f"{FIX}/adder8.shdl",
            "fullAdder.shdl": f"{FIX}/fullAdder.shdl",
        },
        traces=[
            TraceDef(
                "sums",
                "B",
                "Settled sums: carries crossing each boundary, overflow wrap.",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b, "Cin": c}, ["Sum", "Cout"])
                        for a, b, c in (
                            (0, 0, 0),
                            (1, 2, 0),
                            (0x7F, 0x01, 0),
                            (0xFF, 0x01, 0),
                            (0xFF, 0xFF, 1),
                            (0xA5, 0x5A, 0),
                        )
                    ),
                    [],
                ),
            ),
            TraceDef(
                "carry_wave",
                "B",
                "Settle A=0xFF + 0, then poke Cin=1 and observe Sum/Cout after "
                "every cycle: the carry advances one full-adder stage at a time "
                "(never instantly), ending at Sum=0, Cout=1.",
                [
                    R(),
                    P("A", 0xFF),
                    P("B", 0),
                    P("Cin", 0),
                    S(SETTLE),
                    E("Sum"),
                    E("Cout"),
                    P("Cin", 1),
                ]
                + sum(([S(1), E("Sum"), E("Cout")] for _ in range(20)), []),
            ),
        ],
    ),
    CaseDef(
        name="adder_n_default",
        title="Parameterized ripple adder at its default binding (N=4)",
        description=(
            "AdderN's generator with the when/else carry boundary, elaborated at the default N=4."
        ),
        tiers=("A", "B"),
        features=("lang:hierarchy", "lang:imports", "lang:multibit-ports"),
        sources={
            "circuit.shdl": f"{FIX}/adderN.shdl",
            "fullAdder.shdl": f"{FIX}/fullAdder.shdl",
        },
        traces=[
            TraceDef(
                "sums",
                "B",
                "4-bit sums including wraparound (15+1) and carry in.",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b, "Cin": c}, ["Sum", "Cout"])
                        for a, b, c in ((15, 1, 0), (5, 3, 0), (0, 0, 1), (9, 6, 1))
                    ),
                    [],
                ),
            )
        ],
    ),
    CaseDef(
        name="adder_n_mixed",
        title="One generator/conditional component at two parameter bindings",
        description=(
            "Hand-authored wrapper instantiating AdderN<N=2> and AdderN<N=3> side "
            "by side: the same `>i[N]` loop and `when {i == 1}/else` conditional "
            "elaborate twice with different shapes in a single artifact."
        ),
        tiers=("A", "B"),
        features=(
            "lang:generators-multi-binding",
            "lang:conditionals-multi-binding",
            "lang:hierarchy",
            "lang:imports",
        ),
        sources={
            "circuit.shdl": ("inline", ADDER_N_MIXED_SHDL),
            "adderN.shdl": f"{FIX}/adderN.shdl",
            "fullAdder.shdl": f"{FIX}/fullAdder.shdl",
        },
        traces=[
            TraceDef(
                "both_widths",
                "B",
                "2-bit and 3-bit sums computed by the two bindings independently.",
                [R()]
                + sum(
                    (
                        combo({"A": a, "B": b, "C": c, "D": d}, ["SumS", "CoutS", "SumL", "CoutL"])
                        for a, b, c, d in ((3, 1, 5, 3), (1, 1, 3, 4), (0, 0, 7, 1), (2, 2, 0, 0))
                    ),
                    [],
                ),
            )
        ],
    ),
    # --- state and feedback ---------------------------------------------------
    CaseDef(
        name="sr_latch",
        title="SR latch: feedback state with init-block power-on",
        description=(
            "Cross-coupled NORs hold state under the unit-delay model; the init "
            "block seeds Q=0, Qn=1 at cycle 0 instead of the inconsistent all-zeros."
        ),
        tiers=("A", "B"),
        features=("state:sr-latch", "lang:init-block", "derived:nor", "lang:imports"),
        sources={
            "circuit.shdl": f"{EX}/srLatch.shdl",
            "stdgates.shdl": f"{EX}/stdgates.shdl",
        },
        traces=[
            TraceDef(
                "set_hold_reset",
                "B",
                "Power-on seeded Q=0/Qn=1; S sets, inputs drop and the latch holds, R resets.",
                [
                    R(),
                    E("Q"),
                    E("Qn"),
                    P("S", 1),
                    S(4),
                    E("Q"),
                    E("Qn"),
                    P("S", 0),
                    S(4),
                    E("Q"),
                    E("Qn"),
                    P("R", 1),
                    S(4),
                    E("Q"),
                    E("Qn"),
                    P("R", 0),
                    S(4),
                    E("Q"),
                    E("Qn"),
                ],
            )
        ],
    ),
    CaseDef(
        name="d_latch",
        title="Gated D latch composed on SRLatch",
        description="Q follows D while EN is high and holds when EN drops.",
        tiers=("A", "B"),
        features=("state:d-latch", "lang:hierarchy", "lang:init-block"),
        sources={
            "circuit.shdl": f"{EX}/dLatch.shdl",
            "srLatch.shdl": f"{EX}/srLatch.shdl",
            "stdgates.shdl": f"{EX}/stdgates.shdl",
        },
        traces=[
            TraceDef(
                "track_and_hold",
                "B",
                "EN=1: Q tracks D. EN=0: Q holds the captured value through D changes.",
                [
                    R(),
                    P("D", 1),
                    P("EN", 1),
                    S(6),
                    E("Q"),
                    E("Qn"),
                    P("EN", 0),
                    S(2),
                    P("D", 0),
                    S(6),
                    E("Q"),
                    E("Qn"),
                    P("EN", 1),
                    S(6),
                    E("Q"),
                    E("Qn"),
                ],
            )
        ],
    ),
    CaseDef(
        name="register_n",
        title="8-bit load-enable register from D latches",
        description="A generator instantiating eight DLatch bits; LD gates capture.",
        tiers=("A", "B"),
        features=("state:d-latch", "lang:hierarchy", "lang:multibit-ports", "lang:init-block"),
        sources={
            "circuit.shdl": f"{EX}/registerN.shdl",
            "dLatch.shdl": f"{EX}/dLatch.shdl",
            "srLatch.shdl": f"{EX}/srLatch.shdl",
            "stdgates.shdl": f"{EX}/stdgates.shdl",
        },
        traces=[
            TraceDef(
                "load_hold_load",
                "B",
                "Load 0xA5; with LD low, D=0xFF must not disturb Q; reloading takes 0xFF.",
                [
                    R(),
                    P("D", 0xA5),
                    P("LD", 1),
                    S(8),
                    E("Q"),
                    P("LD", 0),
                    S(2),
                    P("D", 0xFF),
                    S(8),
                    E("Q"),
                    P("LD", 1),
                    S(8),
                    E("Q"),
                ],
            )
        ],
    ),
    CaseDef(
        name="ring_clock",
        title="8-stage ring oscillator",
        description=(
            "A closed ring of OR buffers circulates an injected pulse with period "
            "8 under the unit-delay model; the trace tracks the one-hot pulse for "
            "two full revolutions."
        ),
        tiers=("A", "B"),
        features=("state:ring-oscillator", "lang:multibit-ports"),
        sources={"circuit.shdl": f"{EX}/ringClock.shdl"},
        traces=[
            TraceDef(
                "oscillation",
                "B",
                "After a 1-cycle seed pulse, out is one-hot and rotates one stage "
                "per cycle, wrapping from stage 8 back to stage 1 (period 8).",
                [R(), E("out"), P("seed", 1), S(1), P("seed", 0)]
                + sum(([S(1), E("out")] for _ in range(16)), []),
            )
        ],
    ),
    CaseDef(
        name="cpu_rege",
        title="SR16 two-phase master-slave register (RegE, N=16)",
        description=(
            "The CPU building block: 16 MSFFE bits, each a master DLatch strobed "
            "by LD AND Phi1 and a slave published on Phi2. Driven with "
            "non-overlapping phases the trace pins edge-triggered capture, hold "
            "with LD low, and reload."
        ),
        tiers=("A", "B"),
        features=("composite:large", "state:d-latch", "lang:hierarchy", "lang:multibit-ports"),
        sources={
            "circuit.shdl": f"{EX}/CPU/seq.shdl",
            "dLatch.shdl": f"{EX}/dLatch.shdl",
            "srLatch.shdl": f"{EX}/srLatch.shdl",
            "stdgates.shdl": f"{EX}/stdgates.shdl",
        },
        traces=[
            TraceDef(
                "two_phase_load",
                "B",
                "Phi1 captures D into the masters (LD=1), Phi2 publishes to Q; "
                "with LD=0 a full clock leaves Q untouched; reloading takes the new D.",
                [
                    R(),
                    P("D", 0xBEEF),
                    P("LD", 1),
                    P("Phi1", 1),
                    S(12),
                    P("Phi1", 0),
                    S(2),
                    P("Phi2", 1),
                    S(12),
                    P("Phi2", 0),
                    S(2),
                    E("Q"),
                    P("LD", 0),
                    P("D", 0x1234),
                    P("Phi1", 1),
                    S(12),
                    P("Phi1", 0),
                    S(2),
                    P("Phi2", 1),
                    S(12),
                    P("Phi2", 0),
                    S(2),
                    E("Q"),
                    P("LD", 1),
                    P("Phi1", 1),
                    S(12),
                    P("Phi1", 0),
                    S(2),
                    P("Phi2", 1),
                    S(12),
                    P("Phi2", 0),
                    S(2),
                    E("Q"),
                ],
            )
        ],
    ),
    # --- large composite --------------------------------------------------------
    CaseDef(
        name="alu",
        title="8-bit ALU: AND/OR/XOR/ADD with Cout and Zero flags",
        description=(
            "The capstone composite: bitwise generator lanes, an AdderN<8> "
            "arithmetic lane, a Mux4N result select, and an OR-reduction Zero "
            "flag with the when/else boundary — most of the language in one "
            "artifact."
        ),
        tiers=("A", "B"),
        features=(
            "composite:large",
            "lang:named-constants",
            "lang:hierarchy",
            "lang:imports",
            "lang:conditionals-multi-binding",
            "lang:multibit-ports",
        ),
        sources={
            "circuit.shdl": f"{EX}/alu.shdl",
            "adderN.shdl": f"{EX}/adderN.shdl",
            "muxN.shdl": f"{EX}/muxN.shdl",
            "fullAdder.shdl": f"{EX}/fullAdder.shdl",
        },
        traces=[
            TraceDef(
                "all_ops",
                "B",
                "Op=0..3 over A=0xCC, B=0xAA: AND 0x88, OR 0xEE, XOR 0x66, "
                "ADD 0x76 carry 1; then XOR of equal operands raises Zero, and "
                "ADD 0+0 raises Zero with no carry.",
                [R()]
                + sum(
                    (
                        combo({"A": 0xCC, "B": 0xAA, "Op": op}, ["R", "Cout", "Zero"])
                        for op in range(4)
                    ),
                    [],
                )
                + combo({"A": 0x55, "B": 0x55, "Op": 2}, ["R", "Cout", "Zero"])
                + combo({"A": 0, "B": 0, "Op": 3}, ["R", "Cout", "Zero"]),
            )
        ],
    ),
    # --- Tier C: ABI semantics ----------------------------------------------------
    CaseDef(
        name="abi_poke_masking",
        title="ABI: poke masks the value to the port width",
        description=(
            "MaskProbe is a pure 2-bit passthrough. Poking 255 and 4 (0b100) "
            "into In[2] must store 3 and 0: the scatter keeps only bits within "
            "the port width, observable both by peeking the input back and "
            "through the passthrough output."
        ),
        tiers=("A", "C"),
        features=("abi:poke-masking",),
        sources={"circuit.shdl": ("inline", MASK_PROBE_SHDL)},
        traces=[
            TraceDef(
                "masking",
                "C",
                "poke 255 -> In reads 3; poke 4 -> In reads 0 (bit 3 dropped); "
                "in-range pokes pass through unchanged.",
                [
                    R(),
                    P("In", 255),
                    E("In"),
                    S(1),
                    E("Out"),
                    P("In", 4),
                    E("In"),
                    S(1),
                    E("Out"),
                    P("In", 2),
                    S(1),
                    E("Out"),
                    E("In"),
                ],
            )
        ],
    ),
    CaseDef(
        name="abi_lazy_peek",
        title="ABI: peek of an output ticks exactly once iff dirty",
        description=(
            "The 20-stage thermometer (out reads 2^n - 1 after n total ticks "
            "with clk held high) makes every hidden tick countable. Each poke "
            "arms the dirty flag; the first output peek after it must advance "
            "exactly one cycle, and further peeks none."
        ),
        tiers=("A", "C"),
        features=("abi:lazy-peek",),
        sources={"circuit.shdl": f"{FIX}/clock.shdl"},
        traces=[
            TraceDef(
                "hidden_tick_iff_dirty",
                "C",
                "reset: peek is tickless (0). After poke clk=1: first peek ticks "
                "once (1), second peek is clean (still 1). step(1) -> 3. A re-poke "
                "of the same value re-arms dirty (7); double-poke still ticks once (15).",
                [
                    R(),
                    E("out"),
                    P("clk", 1),
                    E("out"),
                    E("out"),
                    S(1),
                    E("out"),
                    E("out"),
                    P("clk", 1),
                    E("out"),
                    P("clk", 1),
                    P("clk", 1),
                    E("out"),
                    E("out"),
                ],
            )
        ],
    ),
    CaseDef(
        name="abi_peek_input",
        title="ABI: peek of an input never ticks and never clears dirty",
        description=(
            "After poke clk=1, two input peeks must return the poked value "
            "without advancing the circuit; the dirty flag must survive them, so "
            "the first output peek afterwards still ticks exactly once (out=1, "
            "not 3 or more)."
        ),
        tiers=("A", "C"),
        features=("abi:peek-input-never-ticks",),
        sources={"circuit.shdl": f"{FIX}/clock.shdl"},
        traces=[
            TraceDef(
                "input_peek_tickless",
                "C",
                "Input peeks return 1 with no ticks; the later output peek shows "
                "exactly one hidden tick happened in total.",
                [R(), P("clk", 1), E("clk"), E("clk"), E("out"), E("clk"), E("out")],
            )
        ],
    ),
    CaseDef(
        name="abi_step_zero",
        title="ABI: step(0) is a no-op that preserves the dirty flag",
        description=(
            "Two step(0) calls between poke and peek must neither advance the "
            "thermometer nor clear dirty: the following output peek reads 1 "
            "(one hidden tick), not 0 (dirty lost) nor 3 (steps executed). A "
            "step(1) afterwards must clear dirty: the next peek is tickless."
        ),
        tiers=("A", "C"),
        features=("abi:step-zero-preserves-dirty",),
        sources={"circuit.shdl": f"{FIX}/clock.shdl"},
        traces=[
            TraceDef(
                "step_zero_noop",
                "C",
                "poke; step(0); step(0); peek -> 1 proves no-op + dirty preserved; "
                "then poke; step(1); peek -> 3 proves step(n>0) cleared dirty.",
                [
                    R(),
                    P("clk", 1),
                    S(0),
                    S(0),
                    E("out"),
                    E("out"),
                    P("clk", 1),
                    S(1),
                    E("out"),
                    E("out"),
                ],
            )
        ],
    ),
    CaseDef(
        name="abi_reset_init",
        title="ABI: reset is idempotent, clears state and inputs, applies init seeds",
        description=(
            "The SR latch powers on seeded (Q=0, Qn=1). Repeated resets observe "
            "the same seeds; after setting the latch and poking S=1, one reset "
            "must restore the seeds AND forget the poked input, so the latch "
            "stays reset when stepped."
        ),
        tiers=("A", "C"),
        features=("abi:reset-idempotent", "abi:init-seeding", "lang:init-block"),
        sources={
            "circuit.shdl": f"{EX}/srLatch.shdl",
            "stdgates.shdl": f"{EX}/stdgates.shdl",
        },
        traces=[
            TraceDef(
                "reset_restores_seeds",
                "C",
                "Seeds visible at cycle 0; double reset identical; after S=1 set "
                "and reset, stepping shows S was cleared (latch stays Q=0).",
                [
                    R(),
                    E("Q"),
                    E("Qn"),
                    R(),
                    R(),
                    E("Q"),
                    E("Qn"),
                    P("S", 1),
                    S(4),
                    E("Q"),
                    E("Qn"),
                    R(),
                    E("Q"),
                    E("Qn"),
                    S(4),
                    E("Q"),
                    E("Qn"),
                ],
            )
        ],
    ),
    CaseDef(
        name="abi_vcc_cycle0",
        title="ABI: __VCC__ reads 0 at cycle 0 and 1 from cycle 1",
        description=(
            "VccProbe taps VCC directly (Hi) and through a NOT (HiInv). At cycle "
            "0 both read 0; after one tick Hi=1 and HiInv=1 (the NOT saw the "
            "cycle-0 zero); from cycle 2 on HiInv=0. The 0,1,0,... HiInv "
            "sequence is reproducible only with faithful cycle-0 semantics."
        ),
        tiers=("A", "C"),
        features=("abi:vcc-cycle0",),
        sources={"circuit.shdl": ("inline", VCC_PROBE_SHDL)},
        traces=[
            TraceDef(
                "vcc_wave",
                "C",
                "Hi: 0 then 1 forever. HiInv: 0, 1, 0, then stable 0.",
                [
                    R(),
                    E("Hi"),
                    E("HiInv"),
                    S(1),
                    E("Hi"),
                    E("HiInv"),
                    S(1),
                    E("Hi"),
                    E("HiInv"),
                    S(3),
                    E("Hi"),
                    E("HiInv"),
                ],
            )
        ],
    ),
]

REQUIRED_FEATURES: dict[str, str] = {
    "primitive:and": "AND gate compiled and simulated correctly",
    "primitive:or": "OR gate compiled and simulated correctly",
    "primitive:not": "NOT gate compiled and simulated correctly",
    "primitive:xor": "XOR gate compiled and simulated correctly",
    "primitive:vcc": "__VCC__ constant-1 driver (0 at cycle 0)",
    "primitive:gnd": "__GND__ constant-0 driver",
    "derived:nand": "NAND composed from primitives",
    "derived:nor": "NOR composed from primitives",
    "derived:xnor": "XNOR composed from primitives",
    "adder:ripple-carry-per-cycle": "carry observed advancing one stage per cycle, never instantly",
    "state:sr-latch": "cross-coupled feedback holds state",
    "state:d-latch": "gated latch tracks and holds",
    "state:ring-oscillator": "closed ring circulates a pulse with period N",
    "lang:init-block": "init seeds applied at cycle 0 through flattening",
    "lang:named-constants": "named constants become __VCC__/__GND__ drivers, incl. beyond-width reads",
    "lang:multibit-ports": "multi-bit ports flattened to _1_.._N_ wires, LSB first",
    "lang:slices": "slice wiring S[a:b]",
    "lang:concatenation": "concatenation as source and destination",
    "lang:replication": "replication N{...} inside concatenation",
    "lang:hierarchy": "component instantiation flattened through multiple levels",
    "lang:imports": "use module::{Component} resolution",
    "lang:generators-multi-binding": "the same generator elaborated at more than one binding",
    "lang:conditionals-multi-binding": "when/else elaborated at more than one binding",
    "lang:nested-generators": "generators nested inside generators with index arithmetic",
    "composite:large": "a large multi-component composite flattens and simulates",
    "degenerate:passthru": "wire-only components survive flattening",
    "degenerate:single-gate": "a one-gate circuit works end to end",
    "degenerate:repeated-names": "identical names in sibling scopes uniquified",
    "degenerate:zero-gate": "a circuit with no gates at all works end to end",
    "abi:poke-masking": "poke masks the value to the port width",
    "abi:lazy-peek": "peek of an output ticks exactly once iff dirty, then reads",
    "abi:peek-input-never-ticks": "peek of an input never ticks and never clears dirty",
    "abi:step-zero-preserves-dirty": "step(0) is a no-op that preserves the dirty flag",
    "abi:reset-idempotent": "reset is idempotent and clears inputs and state",
    "abi:init-seeding": "reset re-applies meta.init seeds",
    "abi:vcc-cycle0": "__VCC__ reads 0 at cycle 0 and 1 from cycle 1",
}


def build_case(case_def: CaseDef) -> None:
    case_dir = CASES / case_def.name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    (case_dir / "traces").mkdir(parents=True)

    for dest, src in sorted(case_def.sources.items()):
        if isinstance(src, tuple) and src[0] == "inline":
            (case_dir / dest).write_text(src[1], encoding="utf-8")
        else:
            shutil.copyfile(REPO / src, case_dir / dest)

    base_text = flatten_program(str(case_dir / "circuit.shdl"), top=case_def.top, timestamp=TS).text
    (case_dir / "expected.base.shdl").write_text(base_text, encoding="utf-8")

    settle = max(1, parse_base(base_text).meta["timing"]["max_depth"])
    trace_files = []
    for trace_def in case_def.traces:
        ops = [
            {"op": "step", "cycles": settle} if op == {"op": "step", "cycles": SETTLE} else op
            for op in trace_def.ops
        ]
        filled = fill_trace_ops(base_text, ops)
        trace_path = case_dir / "traces" / f"{trace_def.name}.json"
        trace_path.write_text(
            trace_json_text(
                {
                    "trace_format": 1,
                    "name": trace_def.name,
                    "tier": trace_def.tier,
                    "description": trace_def.description,
                    "provenance": PROV_TRACES,
                    "ops": filled,
                }
            ),
            encoding="utf-8",
        )
        trace_files.append(f"traces/{trace_def.name}.json")

    case_json = {
        "case_format": 1,
        "name": case_def.name,
        "title": case_def.title,
        "description": case_def.description,
        "tiers": list(case_def.tiers),
        "top": case_def.top,
        "circuit": "circuit.shdl",
        "sources": sorted(case_def.sources),
        "expected_base": "expected.base.shdl",
        "traces": sorted(trace_files),
        "features": list(case_def.features),
        "provenance": {"expected_base": PROV_BASE, "traces": PROV_TRACES},
    }
    (case_dir / "case.json").write_text(json.dumps(case_json, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    names = [c.name for c in CASE_DEFS]
    assert len(set(names)) == len(names), "duplicate case names"
    CASES.mkdir(parents=True, exist_ok=True)

    for case_def in CASE_DEFS:
        build_case(case_def)
        print(f"built {case_def.name}")

    manifest = {
        "manifest_format": 1,
        "suite_version": SUITE_VERSION,
        "flatten_timestamp": TS,
        "cases": sorted(names),
        "required_features": REQUIRED_FEATURES,
        "changelog": [
            {
                "version": SUITE_VERSION,
                "date": CREATED,
                "notes": (
                    "Initial corpus: 32 cases covering all primitives, derived "
                    "gates, adders (with per-cycle carry ripple), state/feedback, "
                    "language features at multiple bindings, large composites, "
                    "degenerate shapes, and the seven release-ABI semantics rules."
                ),
            }
        ],
    }
    (CONF / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote MANIFEST.json ({len(names)} cases)")

    suite = load_suite()  # loud self-check: schema, manifest<->disk, coverage
    total_traces = sum(len(c.traces) for c in suite.cases)
    print(
        f"validated: {len(suite.cases)} cases, {total_traces} traces, "
        f"{len(suite.manifest.required_features)} required features covered"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
