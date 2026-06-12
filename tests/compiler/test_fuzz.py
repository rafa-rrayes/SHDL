"""Differential fuzzing: random valid netlists from fuzz_gen vs BaseEval.

SHDLC_FUZZ (default 20) circuits, SHDLC_FUZZ_CYCLES (default 100) compared
cycles each. Seeds are stable (base + index); failures carry the seed, the
action log tail, and the full netlist text.

FUZ-5 (this file's second half) generalizes the action-sequence adversary:
randomized poke / peek / step / step_settle / reset / run_batch interleavings
emphasizing the dirty-flag state-machine corner cases (reset-after-poke, peek
storms, step(0) runs, double-poke-same-port), each oracle-checked through the
DualSim conventions in harness.py.
"""

from __future__ import annotations

import os
import random
import zlib

import pytest

from .fuzz_gen import gen_circuit
from .harness import random_drive

FUZZ_COUNT = int(os.environ.get("SHDLC_FUZZ", "20"))
FUZZ_CYCLES = int(os.environ.get("SHDLC_FUZZ_CYCLES", "100"))
FUZZ_SEED_BASE = 0x5_8D1C  # arbitrary, stable


@pytest.mark.parametrize("index", range(FUZZ_COUNT))
def test_fuzz_random_circuit(builds, index):
    seed = FUZZ_SEED_BASE + index
    rng = random.Random(seed)
    text = gen_circuit(rng)  # self-checked against BaseEval inside
    key = f"fuzz-{index}-{zlib.crc32(text.encode()):08x}"
    try:
        dual = builds.dual_from_text(key, text, seed=seed)
        dual.compare_all()
        random_drive(dual, rng, FUZZ_CYCLES)
    except AssertionError as e:
        raise AssertionError(
            f"{e}\n--- fuzz netlist (seed {seed}) ---\n{text}"
        ) from e
    except Exception as e:
        raise AssertionError(
            f"fuzz circuit failed to build/run (seed {seed}): {e!r}\n"
            f"--- fuzz netlist ---\n{text}"
        ) from e


# --------------------------------------------------------------------------- #
# FUZ-5: action-sequence adversary over the full release ABI.
# --------------------------------------------------------------------------- #
#
# The mutation-killing cases the original suite already had were a handful of
# hand-written reset-after-poke / step(0) tests. This generalizes them into a
# randomized, seed-stable driver that interleaves *every* ABI verb and
# emphasizes the dirty-flag transitions that distinguish a correct lib from a
# plausible-but-wrong one.
#
# Oracle rule (same as DualSim's): BaseEval has no lazy-tick, so a lib peek of
# an OUTPUT while the dirty flag is set triggers a hidden tick the oracle does
# not see. We therefore TRACK the lib's dirty flag and only diff the two sides
# at points where dirty is provably clear:
#   - poke / run_batch input scatter / step(0) / step_settle(<=0)  -> set/keep dirty
#   - step(n>0) / step_settle(n>0) / reset                         -> clear dirty
# When dirty, we still drive both sides; we only suppress the cross-check.
# A lib OUTPUT-peek while dirty also clears dirty on the lib (the hidden tick),
# which we mirror by stepping the oracle once before the next clean compare.

# Fixtures spanning the dirty-flag-relevant shapes: combinational (settles),
# stateful/feedback (never settles -> step_settle runs full budget), and a
# zero-input circuit. Picked by name so builds caches them once per session.
_FUZ5_FIXTURES = ["add2", "fullAdder", "srlatch", "clock", "gatesDemo"]
_FUZ5_RUNS = int(os.environ.get("SHDLC_FUZZ5_RUNS", "120"))
_FUZ5_SEED_BASE = 0xF5_AD00


class _ActionAdversary:
    """Drives one DualSim through randomized, dirty-aware ABI interleavings.

    Wraps the existing DualSim (lib + BaseEval over identical Base text). The
    lib's hidden dirty/lazy-tick state machine is modeled here so the oracle is
    advanced in lockstep and cross-checks fire only when they are sound.
    """

    def __init__(self, dual, rng):
        self.d = dual
        self.rng = rng
        self.dirty = False  # lib dirty flag, after the constructor's reset()
        self.actions: list[str] = []

    # -- helpers ---------------------------------------------------------- #

    def _note(self, s: str) -> None:
        self.actions.append(s)

    def _oracle_lazy_tick_if_dirty(self) -> None:
        """Mirror the lib's hidden output-peek tick onto the oracle.

        The lib hidden-ticks ONCE on the first output peek while dirty, then
        clears dirty. The oracle has no such tick, so to keep a future clean
        compare valid we step the oracle once and clear our model's dirty bit.
        """
        if self.dirty:
            self.d.oracle.step(1)
            self.dirty = False

    def _safe_compare(self) -> None:
        """Cross-check all ports, but only when dirty is provably clear."""
        if self.dirty:
            return  # comparing now would diverge by the lib's hidden tick
        self.d.compare_all()

    # -- ABI verbs -------------------------------------------------------- #

    def do_poke(self) -> None:
        if not self.d.in_ports:
            return
        port = self.rng.choice(self.d.in_ports)
        raw = self.rng.getrandbits(64)
        self.d.poke(port, raw)
        self.dirty = True
        self._note(f"poke({port!r}, {raw:#x}) -> dirty")

    def do_double_poke(self) -> None:
        """Two pokes to the SAME port: last-write-wins must hold on both sides."""
        if not self.d.in_ports:
            return
        port = self.rng.choice(self.d.in_ports)
        for raw in (self.rng.getrandbits(64), self.rng.getrandbits(64)):
            self.d.poke(port, raw)
        self.dirty = True
        self._note(f"double_poke({port!r}) -> dirty")

    def do_step(self) -> None:
        n = self.rng.randint(0, 4)
        self.d.sim.step(n)
        self.d.oracle.step(n)
        self._note(f"step({n})")
        if n > 0:
            self.dirty = False  # step(n>0) evaluates -> dirty cleared
            self.d.cycle += n
            self._safe_compare()
        # step(0): no-op, dirty unchanged, NOT compared if dirty.
        elif not self.dirty:
            self._safe_compare()

    def do_step_settle(self) -> None:
        n = self.rng.randint(0, 6)
        ran = self.d.sim.step_settle(n)
        assert 0 <= ran <= max(n, 0), f"step_settle({n}) returned {ran}"
        # Observable equivalence: step_settle(n) ≡ step(n) at the ports.
        self.d.oracle.step(max(n, 0))
        self._note(f"step_settle({n}) -> ran {ran}")
        if n > 0:
            self.dirty = False
            self.d.cycle += n
            self._safe_compare()
        elif not self.dirty:
            self._safe_compare()

    def do_peek_storm(self) -> None:
        """A burst of peeks. The FIRST output peek while dirty hidden-ticks the
        lib once and clears dirty; subsequent peeks are stable. We model that,
        then confirm the lib's post-storm state matches the oracle."""
        ports = self.d.in_ports + self.d.out_ports
        if not ports:
            return
        burst = [self.rng.choice(ports) for _ in range(self.rng.randint(1, 6))]
        touches_output = any(p in self.d.out_ports for p in burst)
        # The lib will lazy-tick on the first output peek iff dirty.
        if self.dirty and touches_output:
            self._oracle_lazy_tick_if_dirty()  # advances oracle, clears dirty
        got = {p: self.d.sim.peek(p) for p in burst}
        self._note(f"peek_storm({burst!r})")
        # If dirty is now clear (either it was, or the storm cleared it via an
        # output peek), every peeked port must agree with the oracle.
        if not self.dirty:
            for p in burst:
                want = self.d.oracle.peek(p)
                if got[p] != want:
                    tail = "\n  ".join(self.actions[-25:])
                    raise AssertionError(
                        f"FUZ-5 peek-storm mismatch [{self.d.label}] "
                        f"seed={self.d.seed!r}: port {p!r}: "
                        f"got {got[p]:#x} (lib), want {want:#x} (BaseEval)\n"
                        f"actions:\n  {tail}"
                    )

    def do_reset(self) -> None:
        self.d.sim.reset()
        self.d.oracle.reset()
        self.d.cycle = 0
        self.dirty = False  # reset clears dirty (and input/state) on both sides
        self._note("reset() -> clean")
        self._safe_compare()

    def do_run_batch(self) -> None:
        """run_batch over a few frames ≡ poke-all/step/peek-all, frame by frame.

        Cross-checked against the oracle directly (the batch path is its own
        ABI entry, so we replay the equivalent scalar sequence on BaseEval).

        The C ``run_batch`` (codegen.py) does, per frame: scatter every input
        port (dirty := 1), advance ``cycles`` (``step`` or, when ``settle``,
        ``step_settle`` with fixed-point early-exit), then gather every output
        port — and that gather lazy-ticks ONCE iff dirty is still set (only
        possible when ``cycles <= 0``) and there is at least one output port.
        We model that state machine exactly so the oracle advances in lockstep
        and the model's dirty bit ends equal to the lib's.
        """
        n_in = len(self.d.in_ports)
        n_out = len(self.d.out_ports)
        nframes = self.rng.randint(0, 4)
        cycles = self.rng.randint(0, 5)
        settle = self.rng.random() < 0.5
        frames = [
            tuple(self.rng.getrandbits(64) for _ in range(n_in))
            for _ in range(nframes)
        ]
        got = self.d.sim.run_batch(frames, n_out, cycles, settle=settle)
        self._note(
            f"run_batch(frames={nframes}, cycles={cycles}, settle={settle})"
        )
        # Replay the scalar-equivalent on the oracle, frame by frame, mirroring
        # the lib's per-frame scatter -> advance -> (lazy) gather precisely.
        for frame, outs in zip(frames, got):
            for port, raw in zip(self.d.in_ports, frame):
                mask = (1 << self.d.widths[port]) - 1
                self.d.oracle.poke(port, raw & mask)
            self.dirty = True  # scatter armed dirty on the lib
            advance = max(cycles, 0)
            self.d.oracle.step(advance)
            if advance > 0:
                self.dirty = False  # step/step_settle(cycles>0) cleared dirty
            # Gather: the lib lazy-ticks once iff dirty AND it has output ports.
            if self.dirty and n_out > 0:
                self.d.oracle.step(1)
                self.dirty = False
            want = tuple(self.d.oracle.peek(p) for p in self.d.out_ports)
            if outs != want:
                tail = "\n  ".join(self.actions[-25:])
                raise AssertionError(
                    f"FUZ-5 run_batch mismatch [{self.d.label}] "
                    f"seed={self.d.seed!r}: got {outs} (lib), "
                    f"want {want} (BaseEval), frame={frame}\n"
                    f"actions:\n  {tail}"
                )
        # After the loop the model dirty bit equals the lib's: clear when any
        # advance/lazy-tick happened, still set only in the (n_out == 0,
        # cycles <= 0, nframes > 0) corner where no gather tick could fire.

    _VERBS = (
        "do_poke",
        "do_double_poke",
        "do_step",
        "do_step_settle",
        "do_peek_storm",
        "do_reset",
        "do_run_batch",
    )
    # Weight toward the dirty-flag-sensitive verbs (peek storms, double pokes,
    # step(0) lives inside do_step/do_step_settle).
    _WEIGHTS = (3, 2, 3, 2, 4, 1, 2)

    def run(self, steps: int) -> None:
        for _ in range(steps):
            verb = self.rng.choices(self._VERBS, weights=self._WEIGHTS, k=1)[0]
            getattr(self, verb)()
        # Always finish on a clean point and do a final full compare.
        self.do_step()  # may be step(0); follow with a guaranteed clearing step
        self.d.sim.step(1)
        self.d.oracle.step(1)
        self.dirty = False
        self.d.compare_all()


@pytest.mark.parametrize("name", _FUZ5_FIXTURES)
def test_fuz5_action_sequence_adversary(builds, name):
    # FUZ-5: randomized poke/peek/step/step_settle/reset/run_batch interleavings,
    # dirty-flag-aware, oracle-checked through the DualSim conventions.
    seed = _FUZ5_SEED_BASE + zlib.crc32(name.encode())
    rng = random.Random(seed)
    dual = builds.dual_fixture(name, seed=seed)
    dual.compare_all()  # clean at construction (constructor ran reset)
    adv = _ActionAdversary(dual, rng)
    try:
        adv.run(_FUZ5_RUNS)
    except AssertionError:
        raise
    except Exception as e:  # noqa: BLE001
        tail = "\n  ".join(adv.actions[-25:])
        raise AssertionError(
            f"FUZ-5 [{name}] seed={seed!r}: action driver raised {e!r}\n"
            f"actions:\n  {tail}"
        ) from e


def test_fuz5_reset_after_poke_does_not_evaluate(builds):
    # FUZ-5 (mutation killer): poke then reset WITHOUT stepping. The poked
    # value must be discarded — reset returns to the power-on state, and a
    # post-reset peek must NOT reflect the poke. A lib that cleared dirty on
    # reset but kept the input value (or vice versa) would diverge here.
    dual = builds.dual_fixture("add2", seed=0x4E5E7)
    dual.poke("A", 3)
    dual.poke("B", 3)
    dual.reset()
    # reset is clean on both sides; every port reads its power-on value.
    dual.compare_all()
    for port in dual.in_ports + dual.out_ports:
        assert dual.sim.peek(port) == 0, port


def test_fuz5_step_zero_then_peek_lazy_ticks_once(builds):
    # FUZ-5 (mutation killer): step(0) is a no-op that does NOT clear dirty, so
    # the first OUTPUT peek must still hidden-tick exactly once. We verify the
    # lib against a sibling driven with an explicit step(1).
    lazy = builds.sim_fixture("add2")
    explicit = builds.sim_fixture("add2")
    for sim in (lazy, explicit):
        sim.reset()
        sim.poke("A", 1)
        sim.poke("B", 2)
        sim.poke("Cin", 0)
    lazy.step(0)        # no-op; dirty stays set
    explicit.step(1)    # one explicit cycle; dirty cleared
    # The lazy side hidden-ticks on this first output peek:
    assert lazy.peek("Sum") == explicit.peek("Sum")
    assert lazy.peek("Cout") == explicit.peek("Cout")


def test_fuz5_double_poke_same_port_last_write_wins(builds):
    # FUZ-5 (mutation killer; the named double-poke-same-port case): two pokes
    # to the SAME input port inside one dirty batch — the last value must win,
    # and the first OUTPUT peek must still hidden-tick exactly once (the extra
    # poke neither stacks a second tick nor reverts to the earlier value). A lib
    # that summed pokes, kept the first write, or re-armed an extra tick diverges
    # from the reference (which pokes only the winners) at every cycle.
    dp = builds.sim_fixture("add2")
    ref = builds.sim_fixture("add2")
    for sim in (dp, ref):
        sim.reset()
    # Double-poke A (1 then 2) and B (3 then 1); reference pokes only the winners
    # (A=2, B=1). add2 is a ripple adder (TIM-1: Cout at depth 5), so a single
    # lazy tick does NOT settle — we step both sides explicitly to the fixpoint
    # and assert the architectural sum 2 + 1 = 3, Cout 0.
    dp.poke("A", 1)
    dp.poke("A", 2)
    dp.poke("B", 3)
    dp.poke("B", 1)
    dp.poke("Cin", 0)
    ref.poke("A", 2)
    ref.poke("B", 1)
    ref.poke("Cin", 0)
    # Inputs read back the last-written value before any tick (input peek never
    # ticks, never clears dirty).
    assert dp.peek("A") == 2 and dp.peek("B") == 1
    assert ref.peek("A") == 2 and ref.peek("B") == 1
    # The first OUTPUT peek lazy-ticks exactly one cycle on each side; the
    # double-poked side must read identically to the single-poked reference.
    assert dp.peek("Sum") == ref.peek("Sum")
    assert dp.peek("Cout") == ref.peek("Cout")
    # Step both to the fixpoint: the winners' sum 2 + 1 = 3 appears, Cout 0.
    for sim in (dp, ref):
        sim.step(8)
    assert dp.peek("Sum") == ref.peek("Sum") == 3
    assert dp.peek("Cout") == ref.peek("Cout") == 0
