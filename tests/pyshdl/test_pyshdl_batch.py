"""run_batch: observably identical to the poke/step/peek loop it replaces,
including settle=True and the hold semantics for omitted inputs."""

from __future__ import annotations

import random

import pytest

from pyshdl import MetadataUnavailableError, PortValueError, SignalNotFoundError


def loop_reference(c, frames, *, cycles, settle):
    """The batch contract, spelled out one ABI call at a time: every frame
    pokes EVERY input port (omitted ones at their held value), advances, and
    peeks every output."""
    held = {name: c.peek(name) for name in c.inputs}
    rows = []
    for frame in frames:
        held.update(frame)
        for name, value in held.items():
            c.poke(name, value)
        if settle:
            c.step_settle(cycles)
        else:
            c.step(cycles)
        rows.append({name: c.peek(name) for name in c.outputs})
    return rows


def random_frames(rng, n):
    frames = []
    for _ in range(n):
        frame = {}
        if rng.random() < 0.8:
            frame["A"] = rng.randrange(256)
        if rng.random() < 0.8:
            frame["B"] = rng.randrange(256)
        if rng.random() < 0.3:
            frame["Cin"] = rng.randrange(2)
        frames.append(frame)
    return frames


@pytest.mark.parametrize("settle", [False, True])
def test_batch_equals_the_explicit_loop(examples, settle):
    rng = random.Random(f"pyshdl-batch-{settle}")
    frames = random_frames(rng, 50)
    with examples.fresh("adder8") as batched, examples.fresh("adder8") as looped:
        cycles = batched.timing.max_depth
        got = batched.run_batch(frames, cycles=cycles, settle=settle)
        want = loop_reference(looped, frames, cycles=cycles, settle=settle)
    assert got == want


def test_batch_holds_omitted_inputs(examples):
    with examples.fresh("adder8") as c:
        depth = c.timing.max_depth
        out = c.run_batch(
            [{"A": 10, "B": 20}, {"B": 30}, {}],
            cycles=depth,
        )
        assert [row["Sum"] for row in out] == [30, 40, 40]


def test_batch_hold_starts_from_current_input_values(examples):
    with examples.fresh("adder8") as c:
        c["A"] = 5
        out = c.run_batch([{"B": 7}], cycles=c.timing.max_depth)
        assert out[0]["Sum"] == 12


def test_batch_with_lazy_evaluation_cycles_zero(examples):
    # cycles=0 leaves the pokes pending; the gather applies the ABI's lazy
    # evaluation cycle, exactly like a peek after step(0).
    frames = [{"A": 1, "B": 2}, {"A": 3}]
    with examples.fresh("adder8") as batched, examples.fresh("adder8") as looped:
        got = batched.run_batch(frames, cycles=0)
        want = loop_reference(looped, frames, cycles=0, settle=False)
    assert got == want


def test_batch_validates_names_and_values(examples):
    with examples.fresh("adder8") as c:
        with pytest.raises(SignalNotFoundError, match="frame 1"):
            c.run_batch([{"A": 1}, {"Sum": 2}])
        with pytest.raises(PortValueError):
            c.run_batch([{"A": 999}])


def test_batch_of_nothing(examples):
    with examples.fresh("adder8") as c:
        assert c.run_batch([]) == []


def test_batch_requires_metadata(examples):
    from pyshdl import Circuit

    lib, _ = examples.artifacts("adder8")
    with Circuit.from_library(lib) as bare:
        with pytest.raises(MetadataUnavailableError):
            bare.run_batch([{"A": 1}])
