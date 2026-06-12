"""settle(): exactly step(max_depth) on combinational circuits, refused under
feedback (V.2); step_settle as the exposed fixed-point optimization."""

from __future__ import annotations

import pytest

from pyshdl import Circuit, MetadataUnavailableError, SettleRefusedError

BASE_WITHOUT_META = """\
component Buf(A) -> (O) {
    g: OR;
    connect { A -> g.A; A -> g.B; g.O -> O; }
}
"""


def test_settle_equals_explicit_step_max_depth(examples):
    with examples.fresh("adder8") as a, examples.fresh("adder8") as b:
        depth = a.timing.max_depth
        for x, y, cin in ((200, 55, 0), (255, 1, 0), (0, 0, 1), (170, 85, 1)):
            for c in (a, b):
                c["A"], c["B"], c["Cin"] = x, y, cin
            a.settle()
            b.step(depth)
            assert a["Sum"] == b["Sum"] and a["Cout"] == b["Cout"], (x, y, cin)
            assert a["Sum"] == (x + y + cin) % 256


def test_settle_completes_the_full_carry_ripple(examples):
    # 255 + 1 exercises the critical path end to end: only a full
    # max_depth advance shows the completely rippled result.
    with examples.fresh("adder8") as c:
        c["A"], c["B"] = 255, 1
        c.settle()
        assert (c["Sum"], c["Cout"]) == (0, 1)


@pytest.mark.parametrize("name", ["srLatch", "dLatch", "ringClock"])
def test_settle_refused_under_feedback(examples, name):
    with examples.fresh(name) as c:
        assert c.timing.has_feedback
        with pytest.raises(SettleRefusedError, match="step"):
            c.settle()


def test_settle_requires_timing_metadata():
    with Circuit.from_base(BASE_WITHOUT_META) as c:
        assert c.timing is None
        with pytest.raises(MetadataUnavailableError, match="timing"):
            c.settle()


def test_step_settle_early_exit_is_observably_identical(examples):
    with examples.fresh("adder8") as a, examples.fresh("adder8") as b:
        for c in (a, b):
            c["A"], c["B"] = 123, 45
        ran = a.step_settle(10_000)
        b.step(10_000)
        assert 1 <= ran < 10_000  # fixed point found long before the budget
        assert a["Sum"] == b["Sum"] == 168


def test_step_settle_on_a_fixed_point_costs_one_cycle(examples):
    with examples.fresh("ringClock") as c:
        # Power-on all-zero with seed low is already a fixed point: proving
        # it costs exactly one evaluation cycle.
        assert c.step_settle(10) == 1


def test_step_settle_never_exits_on_an_oscillator(examples):
    with examples.fresh("ringClock") as c:
        c["seed"] = 1
        c.step()  # inject the pulse
        c["seed"] = 0
        assert c.step_settle(40) == 40  # the pulse circulates forever
