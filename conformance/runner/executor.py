"""Trace replay: one op-walker shared by checking, lockstep verification, and
golden generation.

An ``expect`` op is an *observation with ABI semantics*: it performs a real
``peek``, which on an output port triggers the one hidden tick iff the dirty
flag is armed. Observations are therefore part of the stimulus — removing or
reordering an ``expect`` changes the meaning of every op after it. This is
deliberate: it is how the Tier C traces pin the lazy-peek rules exactly.

``replay`` drives any number of simulators through the same op sequence in
lockstep. Each simulator only needs the release-ABI surface: ``reset()``,
``poke(signal, value)``, ``peek(signal) -> int``, ``step(cycles)``. Poke
values are forwarded raw (possibly wider than the port) — masking to port
width is the simulator's job, and the traces exercise exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    """One ``expect`` op's outcome across all simulators driven in lockstep."""

    op_index: int
    signal: str
    expected: int  # the golden value stored in the trace
    values: dict[str, int]  # simulator name -> peeked value


def trace_signals(ops) -> set[str]:
    """All signal names a trace touches (for upfront port validation)."""
    return {op["signal"] for op in ops if op["op"] in ("poke", "expect")}


def replay(ops, sims: dict[str, object]) -> list[Observation]:
    """Drive every simulator through ``ops``; collect one Observation per expect."""
    observations: list[Observation] = []
    for index, op in enumerate(ops):
        match op["op"]:
            case "reset":
                for sim in sims.values():
                    sim.reset()
            case "poke":
                for sim in sims.values():
                    sim.poke(op["signal"], op["value"])
            case "step":
                for sim in sims.values():
                    sim.step(op["cycles"])
            case "expect":
                values = {name: sim.peek(op["signal"]) for name, sim in sims.items()}
                observations.append(
                    Observation(
                        op_index=index,
                        signal=op["signal"],
                        expected=op["value"],
                        values=values,
                    )
                )
    return observations


def mismatches(observations: list[Observation], sim_name: str) -> list[str]:
    """Report lines for every observation where ``sim_name`` missed the golden."""
    lines = []
    for obs in observations:
        got = obs.values[sim_name]
        if got != obs.expected:
            lines.append(
                f"op[{obs.op_index}] expect {obs.signal}: golden {obs.expected}, {sim_name} {got}"
            )
    return lines


def disagreements(observations: list[Observation], left: str, right: str) -> list[str]:
    """Report lines for every observation where two simulators disagree."""
    lines = []
    for obs in observations:
        a, b = obs.values[left], obs.values[right]
        if a != b:
            lines.append(f"op[{obs.op_index}] expect {obs.signal}: {left} {a}, {right} {b}")
    return lines
