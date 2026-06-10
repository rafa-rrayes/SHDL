"""Verification harness for the Base SHDL -> C compiler (shdlc).

Every expected value in this suite comes from :class:`shdlc.sim.base_eval.BaseEval`
(the verified reference oracle) or directly from base_shdl.md / shdl.md — never
from the C implementation under test. Pinned literals in the test files were
derived by running BaseEval (see the per-constant comments).

Key ABI facts under test (shdlc_goals.md §2/§3, shdl.md §11):

- unit-delay two-buffer model: one gate level per tick, never settled;
- cycle 0 is all-zero except ``meta.init`` seeds; ``__VCC__`` reads 0 at
  cycle 0 and 1 from cycle 1;
- ``poke`` masks to port width and sets the dirty flag;
- ``peek`` of an OUTPUT does exactly one hidden tick iff dirty (then clears
  it); ``peek`` of an INPUT never ticks and never clears dirty;
- ``step(0)`` is a no-op that does NOT clear dirty; ``step(n>0)`` evaluates n
  cycles (and thereby clears dirty: the circuit has been evaluated since the
  last poke);
- ``reset`` is idempotent, clears inputs+state+dirty, applies init seeds; a
  constructor runs reset at load.
"""

from __future__ import annotations

import ctypes
import itertools
import json
import os
import shutil
from pathlib import Path

from shdlc.baseshdl import BaseComponent, parse_base
from shdlc.sim.base_eval import BaseEval

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
TIMESTAMP = "2026-01-01T00:00:00Z"

#: Used for ALL test builds: every build doubles as proof that the generated C
#: is warning-free under -Wall -Wextra -Werror -pedantic.
STRICT_CFLAGS = (
    "-std=c11",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-pedantic",
    "-O2",
    "-fPIC",
    "-shared",
    "-fvisibility=hidden",
)


def flatten_fixture_text(name: str) -> str:
    """Flatten ``tests/fixtures/<name>.shdl`` to Base SHDL text at test time."""
    from flattener.pipeline import flatten_program

    return flatten_program(str(FIXTURES / f"{name}.shdl"), timestamp=TIMESTAMP).text


def identity_ports(comp: BaseComponent) -> dict:
    """Single-bit identity port groups synthesized from the component header
    (mirrors model invariant 7 for artifacts without ``meta.ports``)."""
    return {
        "inputs": {n: [n] for n in comp.inputs},
        "outputs": {n: [n] for n in comp.outputs},
    }


def parse_with_ports(base_text: str) -> BaseComponent:
    comp = parse_base(base_text)
    comp.meta.setdefault("ports", identity_ports(comp))
    return comp


def make_oracle(base_text: str) -> BaseEval:
    """A fresh BaseEval over ``base_text`` (ports defaulted if absent)."""
    return BaseEval(parse_with_ports(base_text))


# --------------------------------------------------------------------------
# ctypes wrapper
# --------------------------------------------------------------------------


class Sim:
    """One loaded copy of a compiled circuit library (release ABI).

    dlopen caches by path, so two ``Sim`` instances over the *same* file share
    one global state. Use :func:`load_fresh_copy` whenever an independent
    instance (with a freshly run constructor) is required.
    """

    def __init__(self, lib_path: str | Path):
        self.path = Path(lib_path)
        lib = ctypes.CDLL(str(self.path), mode=os.RTLD_LOCAL)
        lib.reset.argtypes = []
        lib.reset.restype = None
        lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
        lib.poke.restype = None
        lib.peek.argtypes = [ctypes.c_char_p]
        lib.peek.restype = ctypes.c_uint64
        lib.step.argtypes = [ctypes.c_int]
        lib.step.restype = None
        self._lib = lib

    def reset(self) -> None:
        self._lib.reset()

    def poke(self, name: str, value: int) -> None:
        self._lib.poke(name.encode("utf-8"), value)

    def peek(self, name: str) -> int:
        return int(self._lib.peek(name.encode("utf-8")))

    def step(self, n: int = 1) -> None:
        self._lib.step(n)


_copy_counter = itertools.count()


def load_fresh_copy(lib_path: str | Path, work_dir: str | Path) -> Sim:
    """Copy the library file to a brand-new path and load that copy.

    dlopen caches by path: loading the same path twice shares state and skips
    the constructor. A file copy at a unique path guarantees an independent
    instance whose constructor (which must run reset) executes at load.
    """
    src = Path(lib_path)
    dst = Path(work_dir) / f"{src.stem}.copy{next(_copy_counter):04d}{src.suffix}"
    shutil.copy2(src, dst)
    return Sim(dst)


# --------------------------------------------------------------------------
# Differential driver
# --------------------------------------------------------------------------


class DualSim:
    """Lockstep driver: compiled library vs BaseEval over the same Base text.

    ORACLE MISMATCH RULE: BaseEval has no lazy-tick, so this driver only
    compares right after explicit ``step``/``reset`` (when the lib's dirty
    flag is clear and a peek cannot trigger a hidden tick). Pokes send the RAW
    64-bit value to the lib (continuously exercising its masking) but mask to
    the port width before BaseEval.poke, which raises on oversized values.
    """

    def __init__(self, sim: Sim, base_text: str, *, seed=None, label: str = ""):
        self.sim = sim
        self.comp = parse_with_ports(base_text)
        self.oracle = BaseEval(self.comp)
        ports = self.comp.meta["ports"]
        self.in_ports: list[str] = list(ports["inputs"])
        self.out_ports: list[str] = list(ports["outputs"])
        self.widths = {n: len(w) for n, w in (ports["inputs"] | ports["outputs"]).items()}
        self.seed = seed
        self.label = label or self.sim.path.name
        self.cycle = 0
        self.log: list[str] = []

    def reset(self) -> None:
        self.sim.reset()
        self.oracle.reset()
        self.cycle = 0
        self.log.append("reset()")

    def poke(self, port: str, raw: int) -> None:
        mask = (1 << self.widths[port]) - 1
        self.sim.poke(port, raw)  # raw: the lib must mask
        self.oracle.poke(port, raw & mask)  # oracle requires pre-masked
        self.log.append(f"poke({port!r}, {raw:#x})")

    def step_compare(self, n: int = 1) -> None:
        """Advance both sides one cycle at a time, comparing all ports."""
        for _ in range(n):
            self.sim.step(1)
            self.oracle.step(1)
            self.cycle += 1
            self.log.append(f"step(1)  # -> cycle {self.cycle}")
            self.compare_all()

    def compare_all(self) -> None:
        for port in self.in_ports + self.out_ports:
            want = self.oracle.peek(port)
            got = self.sim.peek(port)
            if got != want:
                tail = "\n  ".join(self.log[-20:]) or "(none)"
                raise AssertionError(
                    f"differential mismatch [{self.label}] seed={self.seed!r}: "
                    f"cycle {self.cycle}, port {port!r}: "
                    f"expected {want:#x} (BaseEval), got {got:#x} (lib)\n"
                    f"last actions:\n  {tail}"
                )


def random_drive(dual: DualSim, rng, cycles: int, *, p_reset: float = 0.02) -> None:
    """Seeded random poke/step/reset actions, comparing all ports every cycle."""
    done = 0
    while done < cycles:
        if rng.random() < p_reset:
            dual.reset()
            dual.compare_all()  # safe: reset clears dirty on both sides
        if dual.in_ports:
            for port in rng.sample(
                dual.in_ports, k=rng.randint(0, min(2, len(dual.in_ports)))
            ):
                dual.poke(port, rng.getrandbits(64))
        n = rng.randint(1, 3)
        dual.step_compare(n)
        done += n


# --------------------------------------------------------------------------
# Handwritten Base SHDL constants (syntax per base_shdl.md §3.2/§4.2).
# Each is self-checked against BaseEval in tests/compiler/test_primitives.py
# before anything else relies on it.
# --------------------------------------------------------------------------

AND_TEXT = """\
component HandAnd(a, b) -> (y) {
    g: AND;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"], "b": ["b"] }, "outputs": { "y": ["y"] } } }
"""

OR_TEXT = """\
component HandOr(a, b) -> (y) {
    g: OR;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"], "b": ["b"] }, "outputs": { "y": ["y"] } } }
"""

XOR_TEXT = """\
component HandXor(a, b) -> (y) {
    g: XOR;
    connect { a -> g.A; b -> g.B; g.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"], "b": ["b"] }, "outputs": { "y": ["y"] } } }
"""

NOT_TEXT = """\
component HandNot(a) -> (y) {
    g: NOT;
    connect { a -> g.A; g.O -> y; }
}
meta { "ports": { "inputs": { "a": ["a"] }, "outputs": { "y": ["y"] } } }
"""

#: Zero-input circuit: VCC straight to an output.
VCC_TEXT = """\
component HandVcc() -> (y) {
    v: __VCC__;
    connect { v.O -> y; }
}
meta { "ports": { "inputs": {}, "outputs": { "y": ["y"] } } }
"""

GND_TEXT = """\
component HandGnd() -> (y) {
    g: __GND__;
    connect { g.O -> y; }
}
meta { "ports": { "inputs": {}, "outputs": { "y": ["y"] } } }
"""

#: VCC -> NOT chain. BaseEval-derived output trace (cycles 0..6):
#: [0, 1, 0, 0, 0, 0, 0] — cycle 0 all-zero; cycle 1 the NOT still saw
#: VCC's cycle-0 value 0, so it outputs 1; from cycle 2 it sees 1 and
#: outputs 0 forever. This trace discriminates cycle semantics exactly.
VCC_NOT_TEXT = """\
component HandVccNot() -> (y) {
    v: __VCC__;
    n: NOT;
    connect { v.O -> n.A; n.O -> y; }
}
meta { "ports": { "inputs": {}, "outputs": { "y": ["y"] } } }
"""

#: Zero-gate passthrough: input wire straight to an output wire.
WIRE_TEXT = """\
component HandWire(a) -> (y) {
    connect { a -> y; }
}
meta { "ports": { "inputs": { "a": ["a"] }, "outputs": { "y": ["y"] } } }
"""

#: Zero-output circuit: an input and a gate, empty output list.
ZERO_OUTPUT_TEXT = """\
component HandSink(a) -> () {
    g: NOT;
    connect { a -> g.A; }
}
meta { "ports": { "inputs": { "a": ["a"] }, "outputs": {} } }
"""

#: 64-bit-wide passthrough port via meta.ports over 64 single-bit wires
#: (LSB-first lists): UB guard for full-width shifts/masks in generated C.
_WIDE_INS = [f"b{i}" for i in range(64)]
_WIDE_OUTS = [f"y{i}" for i in range(64)]
WIDE64_TEXT = (
    "component HandWide64("
    + ", ".join(_WIDE_INS)
    + ") -> ("
    + ", ".join(_WIDE_OUTS)
    + ") {\n    connect {\n"
    + "".join(f"        b{i} -> y{i};\n" for i in range(64))
    + "    }\n}\nmeta "
    + json.dumps({"ports": {"inputs": {"B": _WIDE_INS}, "outputs": {"Y": _WIDE_OUTS}}})
    + "\n"
)

#: All handwritten constants, keyed by a stable test id.
HANDWRITTEN: dict[str, str] = {
    "hand_and": AND_TEXT,
    "hand_or": OR_TEXT,
    "hand_xor": XOR_TEXT,
    "hand_not": NOT_TEXT,
    "hand_vcc": VCC_TEXT,
    "hand_gnd": GND_TEXT,
    "hand_vcc_not": VCC_NOT_TEXT,
    "hand_wire": WIRE_TEXT,
    "hand_sink": ZERO_OUTPUT_TEXT,
    "hand_wide64": WIDE64_TEXT,
}
