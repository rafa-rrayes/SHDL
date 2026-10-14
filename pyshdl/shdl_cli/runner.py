"""The test-vector runner: CCircus MANIFEST_FORMAT.md §3 semantics.

A faithful port of cc.py's replay loop with the Circuit factory injected, so
the same runner drives ``shdl test`` (project circuits), ``shdl
verify-package`` (a package's exports), and — in a follow-up — cc.py itself.
This module is the canonical home of these semantics.

Two case styles: a **vector table** (reset, poke every input, advance
``steps`` unit-delay cycles, check every output) and an **op sequence**
(explicit reset/poke/step/expect ops, for sequential circuits where timing
matters).
"""

from __future__ import annotations

from collections.abc import Callable


def _replay_ops(c, ops: list[dict]) -> list[str]:
    fails: list[str] = []
    for op in ops:
        kind = op["op"]
        if kind == "reset":
            c.reset()
        elif kind == "poke":
            c.poke(op["signal"], op["value"])
        elif kind == "step":
            c.step(op.get("cycles", 1))
        elif kind == "expect":
            got = c.peek(op["signal"])
            if got != op["value"]:
                fails.append(f"{op['signal']}={got} (want {op['value']})")
        else:
            fails.append(f"unknown op {kind!r}")
    return fails


def run_cases(
    open_circuit: Callable[[str], object],
    cases: list[dict],
) -> tuple[list[str], int, int]:
    """Run every case; returns (report lines, passed, total).

    ``open_circuit(component_name)`` must return a ready
    :class:`SHDL.Circuit`-like object (poke/peek/step/reset/close); the
    runner closes it.
    """
    lines: list[str] = []
    passed = total = 0
    for i, case in enumerate(cases):
        total += 1
        comp = case.get("component")
        if not comp:
            lines.append(f"  FAIL  cases[{i}]: missing 'component'")
            continue
        try:
            c = open_circuit(comp)
        except Exception as e:  # noqa: BLE001 - a build failure is a test failure
            lines.append(f"  FAIL  {comp}: build error: {e}")
            continue
        try:
            fails: list[str] = []
            try:
                if "ops" in case:
                    fails = _replay_ops(c, case["ops"])
                else:
                    steps = case.get("steps", 64)
                    for v in case["vectors"]:
                        c.reset()
                        for sig, val in v["in"].items():
                            c.poke(sig, val)
                        c.step(steps)
                        for sig, want in v["out"].items():
                            got = c.peek(sig)
                            if got != want:
                                fails.append(f"in={v['in']} {sig}={got} (want {want})")
            except Exception as e:  # noqa: BLE001 - a malformed case is a test failure
                fails.append(f"{type(e).__name__}: {e}")
            if fails:
                lines.append(f"  FAIL  {comp}: " + "; ".join(fails[:6]))
            else:
                passed += 1
                lines.append(f"  ok    {comp}")
        finally:
            c.close()
    return lines, passed, total
