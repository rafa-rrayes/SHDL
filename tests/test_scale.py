"""Domain S — scale & stress fixtures (SCL-3/4/5/7).

These probe the toolchain's behavior on large and pathological inputs:

* **SCL-3** — a 10^5-gate synthetic circuit flattened, compiled under
  STRICT_CFLAGS, and run for 100 cycles in lockstep against BaseEval. This is
  the regression guard for the known clang misched blowup on a giant ``tick()``
  (see the large-circuit-perf memory): the chunked-tick mechanism must engage
  (``ng > _TICK_CHUNK`` => ``tick_chunk_*`` functions) so the giant basic block
  is split and the build does not blow up. Env-gated behind ``SHDLC_SCALE`` so
  commit-time runs stay fast; measured wall time recorded in the WP-K report.

* **SCL-4** — a generator emitting 10^4 instances (flatten correctness + sane
  time), 100 distinct monomorphization specializations (MON-7/MON-8), and a
  ~1 MB source file parsed end-to-end (generated programmatically).

* **SCL-5** — a 50-level-deep instantiation hierarchy (distinct from syntactic
  nesting); plus a probe of the phase-1 parser nesting cap
  (``parser.MAX_NESTING_DEPTH``): exactly-at-cap parses, one past it is a
  structured E0201 diagnostic, never a raw ``RecursionError``.

* **SCL-7** — the phase-1 instance-count cap on range materialization
  (``expand.MAX_RANGE_VALUES`` = 1_000_000, diagnostic E0601): a range at the
  cap is accepted by the guard, ``[1:10**9]`` fails fast (never an unbounded
  list materialization / OOM hang), and a parameter-driven instance count
  (``>i[N]`` with a huge default) is likewise guarded.

Every expected value comes from the implementation contract pinned by phase 1
(the cap constants and their E0601 messages) or from BaseEval — never from the
C implementation under test. Heavy builds reuse ``shdlc.harness`` (the shared,
non-test ctypes plumbing) so this file owns no test-harness code.
"""

from __future__ import annotations

import os
import random
import tempfile
import time
import zlib
from pathlib import Path

import pytest

from flattener.diagnostics import ErrorCode, SHDLError
from flattener.parser import MAX_NESTING_DEPTH, parse_source
from flattener.phases.expand import MAX_RANGE_VALUES
from flattener.pipeline import flatten_program
from flattener.source import SourceFile

from helpers import flatten_source  # tests/ is on sys.path (pytest prepend mode)

TS = "2026-01-01T00:00:00Z"

#: SCL-3 / the 10^5 builds are minutes-scale (a 17 s STRICT build + a 7 s Python
#: oracle replay on this machine); gate them so T0-T4 commit runs stay fast.
#: Nightly sets ``SHDLC_SCALE=1`` (see .github/workflows/nightly.yml).
SCALE = os.environ.get("SHDLC_SCALE", "") not in ("", "0")
scale_only = pytest.mark.skipif(
    not SCALE, reason="set SHDLC_SCALE=1 to run the minutes-scale stress builds"
)


def _seed(name: str) -> int:
    """Seed-stable randomness derived from a test name (golden_tests §1.3)."""
    return zlib.crc32(name.encode())


# --------------------------------------------------------------------------- #
# Base SHDL builders (string-built so no .shdl fixture file is needed and the
# circuit size is a single knob).
# --------------------------------------------------------------------------- #


def _chain_text(n: int, name: str = "Big") -> str:
    """An alternating NOT/XOR chain of ``n`` gates: ``g0 = NOT(a)``, then
    ``gi = XOR(g(i-1), b)`` (odd i) / ``gi = NOT(g(i-1))`` (even i); ``y`` is the
    last gate. Identical in shape to the chunked-tick fixture but sized large so
    the build crosses many ``_TICK_CHUNK`` boundaries."""
    decls = [f"    g{i}: {'XOR' if i % 2 else 'NOT'};" for i in range(n)]
    conns = ["        a -> g0.A;"]
    for i in range(1, n):
        conns.append(f"        g{i - 1}.O -> g{i}.A;")
        if i % 2:
            conns.append(f"        b -> g{i}.B;")
    conns.append(f"        g{n - 1}.O -> y;")
    body = ["    connect {", *conns, "    }"]
    return "\n".join([f"component {name}(a, b) -> (y) {{", *decls, *body, "}"]) + "\n"


# --------------------------------------------------------------------------- #
# SCL-3 — 10^5-gate synthetic: flatten + compile + 100-cycle differential.
# --------------------------------------------------------------------------- #

#: 10^5 gates => ~98 chunks past the 1024-gate _TICK_CHUNK threshold.
SCL3_GATES = 100_000


def test_scl3_100k_gate_chunking_engages_at_codegen():
    # SCL-3: a 10^5-gate netlist's generated C must split tick() into chunks
    # (the misched-blowup guard). This half is cheap (no compile), so it runs
    # at commit time; the build+differential half is env-gated below.
    from shdlc.codegen import _TICK_CHUNK, generate_c
    from shdlc.model import build_circuit
    from shdlc.baseshdl import parse_base

    text = _chain_text(SCL3_GATES)
    circuit = build_circuit(parse_base(text))
    assert len(circuit.gates) == SCL3_GATES
    assert len(circuit.gates) > _TICK_CHUNK, "must cross the chunk threshold"
    c_src = generate_c(circuit)
    # The chunked emission is what gets built: a giant single tick() body is
    # exactly the basic block that triggered the clang misched blowup.
    assert "tick_chunk_0(" in c_src
    assert "SHDLC_NOINLINE" in c_src
    last_chunk = (SCL3_GATES - 1) // _TICK_CHUNK
    assert f"tick_chunk_{last_chunk}(" in c_src


@scale_only
def test_scl3_100k_gate_build_and_differential(tmp_path):
    # SCL-3: the full regression guard. Flatten-free (string-built Base SHDL),
    # compile the 10^5-gate circuit under STRICT_CFLAGS (-Werror proves the
    # chunked emission is warning-free AND the build completes — a misched
    # blowup would manifest as a multi-minute / OOM compile), then 100 cycles
    # of poke/step lockstep against BaseEval, every output compared each cycle.
    from shdlc.cc import lib_suffix
    from shdlc.compile import build_library
    from shdlc.harness import STRICT_CFLAGS, load_fresh_copy, parse_with_ports
    from shdlc.sim.base_eval import BaseEval

    text = _chain_text(SCL3_GATES)
    out = tmp_path / f"scl3{lib_suffix()}"
    build_library(text, out, cflags=STRICT_CFLAGS)
    sim = load_fresh_copy(out, tmp_path)
    oracle = BaseEval(parse_with_ports(text))

    rng = random.Random(_seed("scl3"))
    log: list[str] = []
    for cycle in range(1, 101):
        if rng.random() < 0.3:
            for port in ("a", "b"):
                v = rng.getrandbits(1)
                sim.poke(port, v)
                oracle.poke(port, v)
                log.append(f"poke({port}, {v})")
        sim.step(1)
        oracle.step(1)
        log.append(f"step(1) -> cycle {cycle}")
        got, want = sim.peek("y"), oracle.peek("y")
        assert got == want, (
            f"SCL-3 differential mismatch at cycle {cycle}: "
            f"lib={got} BaseEval={want}\nactions:\n  " + "\n  ".join(log[-12:])
        )


# --------------------------------------------------------------------------- #
# SCL-4 — 10^4-instance generator, 100 specializations, ~1 MB source.
# --------------------------------------------------------------------------- #


def _generator_fan_source(n: int) -> str:
    """A parameterized component whose generator emits ``n`` NOT instances, one
    per bit of an ``n``-wide port. Flattens to exactly ``n`` gates."""
    return (
        f"component Fan<N = {n}>(In[N]) -> (Out[N]) {{\n"
        "    >i[N]{ g{i}: NOT; }\n"
        "    connect {\n"
        "        >i[N]{\n"
        "            In[{i}] -> g{i}.A;\n"
        "            g{i}.O -> Out[{i}];\n"
        "        }\n"
        "    }\n"
        "}\n"
    )


@scale_only
def test_scl4_generator_emits_10k_instances(tmp_path):
    # SCL-4: one generator over a 10^4-wide port must emit exactly 10^4 gates
    # (correctness) in a sane time. No superlinear blowup.
    n = 10_000
    t0 = time.perf_counter()
    out = flatten_source(tmp_path, _generator_fan_source(n))
    elapsed = time.perf_counter() - t0
    gates = out.flat.netlist.gates
    assert len(gates) == n, f"expected {n} gates, got {len(gates)}"
    # Spot-check the loop body lowered correctly: ranges are 1-based, so the
    # count form [N] iterates i = 1..N and emits gates g1..gN.
    assert "g1" in gates and f"g{n}" in gates
    # Generous ceiling: a quadratic regression (e.g. the historical add_line
    # O(n^2)) would blow far past this; the linear pipeline is ~2 s here.
    assert elapsed < 30.0, f"10^4-instance flatten took {elapsed:.1f}s (expected < 30s)"


def _hundred_spec_source(count: int) -> str:
    """A parameterized width-N NOT bank plus a top instantiating it at every
    width 1..count, producing ``count`` distinct specializations (MON-7) and
    sum(1..count) gates."""
    bank = (
        "component W<N = 1>(In[N]) -> (Out[N]) {\n"
        "    >i[N]{ g{i}: NOT; }\n"
        "    connect { >i[N]{ In[{i}] -> g{i}.A; g{i}.O -> Out[{i}]; } }\n"
        "}\n"
    )
    insts = "\n".join(f"    w{k}: W<{k}>;" for k in range(1, count + 1))
    in_ports = ", ".join(f"I{k}[{k}]" for k in range(1, count + 1))
    out_ports = ", ".join(f"O{k}[{k}]" for k in range(1, count + 1))
    conns = "\n".join(
        f"        I{k} -> w{k}.In;\n        w{k}.Out -> O{k};" for k in range(1, count + 1)
    )
    top = (
        f"top component Top({in_ports}) -> ({out_ports}) {{\n"
        f"{insts}\n    connect {{\n{conns}\n    }}\n}}\n"
    )
    return bank + top


def test_scl4_hundred_specializations(tmp_path):
    # SCL-4 / MON-7: 100 distinct W<k> instantiations each produce their own
    # specialization (no over-merge), and gate count is sum(1..100) = 5050.
    # Cheap (5050 gates) so it runs at commit time.
    count = 100
    out = flatten_source(tmp_path, _hundred_spec_source(count))
    non_top = [k for k in out.mono.specs if k != out.mono.top_key]
    assert len(non_top) == count, f"expected {count} specializations, got {len(non_top)}"
    assert len(out.flat.netlist.gates) == count * (count + 1) // 2


def test_scl4_one_megabyte_source_parses(tmp_path):
    # SCL-4: a ~1 MB hand-written (non-generator) source flattens end to end in
    # a sane time -- exercises the lexer/parser at scale, not the expander.
    n = 20_000  # ~1.13 MB of source text
    source = _chain_text(n, name="Mega")
    nbytes = len(source.encode("utf-8"))
    assert nbytes > 1_000_000, f"source is {nbytes} bytes, expected > 1 MB"
    t0 = time.perf_counter()
    out = flatten_source(tmp_path, source)
    elapsed = time.perf_counter() - t0
    assert len(out.flat.netlist.gates) == n
    assert elapsed < 30.0, f"1 MB parse+flatten took {elapsed:.1f}s (expected < 30s)"


# --------------------------------------------------------------------------- #
# SCL-5 — 50-level instantiation hierarchy + parser nesting cap.
# --------------------------------------------------------------------------- #


def _deep_hierarchy_source(depth: int) -> str:
    """``depth`` levels of single-child instantiation (L0 instantiates L1 ...
    L(depth-1) instantiates L(depth), the NOT leaf). This is *instantiation*
    depth -- distinct from syntactic nesting -- so it does not approach the
    parser cap; it stresses hierarchy prefixing."""
    lines = [f"component L{depth}(a) -> (y) {{ g: NOT; connect {{ a -> g.A; g.O -> y; }} }}"]
    for k in range(depth - 1, -1, -1):
        marker = "top " if k == 0 else ""
        lines.append(
            f"{marker}component L{k}(a) -> (y) {{ c: L{k + 1}; connect {{ a -> c.a; c.y -> y; }} }}"
        )
    return "\n".join(lines) + "\n"


def test_scl5_fifty_level_hierarchy(tmp_path):
    # SCL-5: a 50-level-deep instantiation chain flattens to a single NOT gate
    # whose name carries one prefix segment per level (deep prefixing, FLT-1 at
    # scale). The CPU's measured max nesting is only 6, so this is the deepest
    # hierarchy the suite exercises.
    depth = 50
    out = flatten_source(tmp_path, _deep_hierarchy_source(depth))
    gates = list(out.flat.netlist.gates)
    assert len(gates) == 1, f"expected 1 leaf gate, got {gates}"
    leaf = gates[0]
    # 50 instance prefixes ("c_" each) then the leaf gate "g".
    assert leaf.count("c_") == depth, f"expected {depth} prefix segments, got {leaf!r}"
    assert leaf.endswith("g")


def _nested_generators_source(levels: int) -> str:
    """``levels`` directly-nested generators, the innermost declaring one gate.
    Each generator body opens a brace counted by the parser's ``_enter`` guard,
    so this is the lever that exercises ``MAX_NESTING_DEPTH``."""
    head = "".join(f">a{k}[1]{{" for k in range(levels))
    tail = "}" * levels
    return f"component Deep() -> (y) {{\n    {head}g: NOT;{tail}\n    connect {{ g.O -> y; }}\n}}\n"


def _parse(source: str):
    parse_source(SourceFile("deep.shdl", "deep.shdl", source), "deep")


def test_scl5_generator_nesting_at_cap_parses():
    # SCL-5: exactly MAX_NESTING_DEPTH levels of generator nesting parse without
    # error -- the cap is inclusive on its boundary.
    _parse(_nested_generators_source(MAX_NESTING_DEPTH))  # no raise == pass


def test_scl5_generator_nesting_past_cap_is_e0201_not_recursionerror():
    # SCL-5 / PAR-8: one level past the cap is a structured E0201 diagnostic
    # with a real position, never a raw RecursionError (the phase-1 fix).
    over = MAX_NESTING_DEPTH + 1
    with pytest.raises(SHDLError) as ei:
        _parse(_nested_generators_source(over))
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0201, d
    assert str(MAX_NESTING_DEPTH) in d.message
    assert d.pos.line >= 1 and d.pos.col >= 1, d


# --------------------------------------------------------------------------- #
# SCL-7 — instance-count cap on range materialization (the range bomb).
# --------------------------------------------------------------------------- #


@scale_only
def test_scl7_range_at_cap_passes_the_span_guard(tmp_path):
    # SCL-7: a range of exactly MAX_RANGE_VALUES values is accepted by the span
    # guard (the cap is inclusive). It materializes the list and then fails for
    # an *unrelated* downstream reason (floating gate inputs, E0502) -- proving
    # the guard itself did NOT fire at the cap. The point is bounded behavior,
    # not success; we only assert the diagnostic is not the cap's E0601 text.
    # Env-gated: materializing 10^6 gates is a ~2 s stress operation.
    source = (
        f"component AtCap() -> (Y) {{\n"
        f"    >i[{MAX_RANGE_VALUES}]{{ g{{i}}: NOT; }}\n"
        "    connect { g0.O -> Y; }\n"
        "}\n"
    )
    with pytest.raises(SHDLError) as ei:
        flatten_source(tmp_path, source)
    d = ei.value.diagnostic
    assert "instance-count cap" not in d.message, (
        f"the span guard fired AT the cap, but {MAX_RANGE_VALUES} is supposed to "
        f"be inclusive; got: {d}"
    )


def test_scl7_range_just_past_cap_fails_fast(tmp_path):
    # SCL-7: a [1:10**9] range must fail fast with the structured E0601
    # diagnostic naming the cap, never materialize a billion-entry list / OOM
    # hang. Timed to catch an accidental list build (the unguarded path took
    # seconds-to-OOM; the guard is sub-millisecond).
    source = (
        "component Bomb() -> (Y) {\n"
        "    >i[1:1000000000]{ g{i}: NOT; }\n"
        "    connect { g1.O -> Y; }\n"
        "}\n"
    )
    t0 = time.perf_counter()
    with pytest.raises(SHDLError) as ei:
        flatten_source(tmp_path, source)
    elapsed = time.perf_counter() - t0
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0601, d
    assert "instance-count cap" in d.message and str(MAX_RANGE_VALUES) in d.message, d
    assert d.pos.line >= 1 and d.pos.col >= 1, d
    assert elapsed < 2.0, (
        f"the range bomb took {elapsed:.2f}s -- the guard must fire BEFORE any "
        f"list materialization (expected sub-millisecond)"
    )


def test_scl7_param_driven_count_is_guarded(tmp_path):
    # SCL-7: a parameter-driven instance count (a generator range whose bound is
    # a parameter with a huge default) is guarded the same way -- the cap is
    # checked after parameter binding, before the list is built.
    source = (
        "component PBomb<N = 1000000000>() -> (Y) {\n"
        "    >i[N]{ g{i}: NOT; }\n"
        "    connect { g0.O -> Y; }\n"
        "}\n"
    )
    t0 = time.perf_counter()
    with pytest.raises(SHDLError) as ei:
        flatten_source(tmp_path, source)
    elapsed = time.perf_counter() - t0
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0601, d
    assert "instance-count cap" in d.message, d
    assert elapsed < 2.0, f"param-driven count bomb took {elapsed:.2f}s (expected fast)"


def test_scl7_open_range_param_bound_is_guarded(tmp_path):
    # SCL-7: the open-ended range form (RangeTo, [:N]) is also span-guarded when
    # its bound resolves to a value past the cap -- the fourth range_values site.
    source = (
        "component OpenBomb<N = 1000000000>(In[2]) -> (Y) {\n"
        "    >i[:N]{ g{i}: NOT; }\n"
        "    connect { g1.O -> Y; }\n"
        "}\n"
    )
    with pytest.raises(SHDLError) as ei:
        flatten_source(tmp_path, source)
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0601, d
    assert "instance-count cap" in d.message, d


def test_scl7_literal_replication_count_is_guarded(tmp_path):
    # SCL-7: a literal-count replication bomb (1000000000{Sign}) is span-guarded
    # at the RRepl resolve site -- the count is checked before RRepl is built,
    # so no billion-entry bit list can materialize in the expander.
    source = (
        "component RBomb(Sign) -> (Y) {\n"
        "    connect { {1000000000{Sign}} -> Y; }\n"
        "}\n"
    )
    t0 = time.perf_counter()
    with pytest.raises(SHDLError) as ei:
        flatten_source(tmp_path, source)
    elapsed = time.perf_counter() - t0
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0601, d
    assert "instance-count cap" in d.message and "replication" in d.message, d
    assert elapsed < 2.0, f"replication bomb took {elapsed:.2f}s (expected fast)"
