"""A runnable walkthrough of the PySHDL driver.

Run it from anywhere:

    uv run python examples/interacting.py

Every circuit it loads lives next to this file in ``examples/``; the paths
are resolved relative to ``__file__`` so the script works from any CWD.
"""

from __future__ import annotations

from pathlib import Path

from pyshdl import Circuit, SettleRefusedError

EXAMPLES = Path(__file__).resolve().parent


def adder_basics() -> None:
    """Load a combinational circuit, poke inputs, settle, peek outputs."""
    print("== Adder8: poke / settle / peek ==")
    # Circuit(path) is the front door: it flattens the .shdl file, compiles
    # it to a private shared library, and loads it. Used as a context manager
    # it cleans up the build artifacts on exit.
    with Circuit(EXAMPLES / "adder8.shdl") as c:
        # poke(name, value) / peek(name); c[name] is the same thing.
        c["A"] = 100
        c["B"] = 55
        c["Cin"] = 0
        # settle() advances the circuit exactly timing.max_depth cycles, the
        # number that lets every gate level propagate. Only valid because the
        # adder is combinational (no feedback).
        c.settle()
        print(f"  100 + 55 = {c['Sum']}  (Cout={c['Cout']})")

        # Multi-bit ports take ordinary ints; bit 0 is the LSB. Negative
        # values encode as two's complement within the port width.
        c["A"] = -1  # 8-bit port: same bits as 255
        c["B"] = 1
        c["Cin"] = 0
        c.settle()
        print(f"  255 + 1 wraps to Sum={c['Sum']}, Cout={c['Cout']}")


def batch() -> None:
    """run_batch drives many input frames through one C call."""
    print("== Adder8: run_batch ==")
    with Circuit(EXAMPLES / "adder8.shdl") as c:
        depth = c.timing.max_depth
        # Each frame is a dict of input -> value. Inputs a frame omits HOLD
        # their previous value, so the second frame keeps A = 10.
        frames = [{"A": 10, "B": 20}, {"B": 30}, {"A": 1, "B": 1, "Cin": 1}]
        rows = c.run_batch(frames, cycles=depth)
        for frame, row in zip(frames, rows):
            print(f"  {frame!s:<32} -> Sum={row['Sum']}, Cout={row['Cout']}")


def introspection() -> None:
    """The read-only metadata surface: ports, widths, timing, stats."""
    print("== Adder8: introspection ==")
    with Circuit(EXAMPLES / "adder8.shdl") as c:
        print(f"  repr:     {c!r}")
        print(f"  name:     {c.name}")
        print(f"  inputs:   {c.inputs}")
        print(f"  outputs:  {c.outputs}")
        a = c.info.port("A")
        print(f"  port A:   width={a.width}, range {a.min_value}..{a.max_value}")
        t = c.timing
        print(f"  timing:   max_depth={t.max_depth}, feedback={t.has_feedback}")
        print(f"  gates:    {c.info.stats['total_gates']}")


def latch() -> None:
    """A sequential circuit: feedback refuses settle(); use step / step_settle."""
    print("== SRLatch: feedback, step_settle, reset ==")
    with Circuit(EXAMPLES / "srLatch.shdl") as c:
        # The latch powers on in its init-seeded fixed point, not all-zero.
        print(f"  power-on:        Q={c['Q']}, Qn={c['Qn']}")

        # settle() is refused on a feedback circuit: max_depth is not a settle
        # count for a loop that may oscillate. Advance it explicitly instead.
        try:
            c.settle()
        except SettleRefusedError:
            print("  settle() refused (circuit has feedback) -- expected")

        # Set S high and step. step_settle(n) runs at most n cycles, stopping
        # early at a fixed point, and returns how many it actually ran.
        c["S"] = 1
        ran = c.step_settle(20)
        print(f"  after S=1:       Q={c['Q']}, Qn={c['Qn']} (settled in {ran} cycles)")

        # reset() returns the circuit to its power-on state (init seeds,
        # inputs cleared) -- equivalent to a fresh load.
        c.reset()
        print(f"  after reset():   Q={c['Q']}, Qn={c['Qn']}")


def main() -> None:
    adder_basics()
    print()
    batch()
    print()
    introspection()
    print()
    latch()


if __name__ == "__main__":
    main()
