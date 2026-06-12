"""FUZ-3: the SHDL-source-level fuzzer (the flattener's first randomized adversary).

The flattener is SHDL's most complex component (six lowering phases over
parameters, generators, conditionals, slices, concat/replication, constants,
init, and hierarchy) and — until FUZ-3 — had no randomized adversary. This
driver generates random *high-level* SHDL programs (see ``fuzz_source_gen``)
that are valid by construction, then runs them through the full oracle chain
(golden_tests.md §1.1):

    source -> flatten (MUST succeed; a diagnostic on valid-by-construction
              input is the bug we hunt — failure embeds the full source)
           -> HighEval vs BaseEval lockstep, every port every cycle (~20)
           -> (env-gated subset) compiled C via shdlc, lockstep vs BaseEval

Independence: expected values come from BaseEval (the verified Base SHDL
reference, golden_tests.md §1.1) and HighEval (an independent interpreter of
the phase-3 model) — never from the C implementation under test.

Scale knobs (mirror tests/compiler/test_fuzz.py's SHDLC_FUZZ convention):
  SHDLC_SOURCE_FUZZ        number of fuzz programs (default 25; commit-time <60s)
  SHDLC_SOURCE_FUZZ_CYCLES lockstep cycles per program (default 20)
  SHDLC_SOURCE_FUZZ_CC     if set & truthy, also lockstep a small compiled-C
                           subset (skipped automatically when no CC is present)

Seeds are stable (base + index); every failure carries the seed, the full
generated program (all modules), and the stimulus log for deterministic replay.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest
from fuzz_source_gen import gen_program

from flattener.pipeline import flatten_program
from flattener.sim.high_eval import HighEval
from shdlc.baseshdl import parse_base
from shdlc.sim.base_eval import BaseEval

FUZZ_COUNT = int(os.environ.get("SHDLC_SOURCE_FUZZ", "25"))
FUZZ_CYCLES = int(os.environ.get("SHDLC_SOURCE_FUZZ_CYCLES", "20"))
FUZZ_SEED_BASE = 0x5_0FCE  # arbitrary, stable ("source")
TIMESTAMP = "2026-01-01T00:00:00Z"

# How many of the FUZZ_COUNT cases also go all the way to compiled C, when
# SHDLC_SOURCE_FUZZ_CC is set (the C path is ~100x slower than the interpreters).
CC_SUBSET = int(os.environ.get("SHDLC_SOURCE_FUZZ_CC_SUBSET", "5"))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _render(modules: dict[str, str], main: str) -> str:
    """The full multi-module program as one replay-able blob."""
    return "\n".join(
        f"=== module {mod}{' (main)' if mod == main else ''} ===\n{txt}"
        for mod, txt in modules.items()
    )


def _flatten_program(tmp_path: Path, modules: dict[str, str], main: str):
    """Write every module to ``tmp_path`` and flatten the main one."""
    for mod, txt in modules.items():
        (tmp_path / f"{mod}.shdl").write_text(txt, encoding="utf-8")
    return flatten_program(
        str(tmp_path / f"{main}.shdl"),
        include_dirs=[str(tmp_path)],
        timestamp=TIMESTAMP,
    )


def _lockstep_high_vs_base(out, seed: int, blob: str, cycles: int) -> list[str]:
    """HighEval vs BaseEval, every port every cycle. Returns the stimulus log.

    Raises AssertionError (with the program + log embedded) on the first port
    divergence — that is a real lowering bug, the thing FUZ-3 exists to find.
    """
    base = BaseEval(parse_base(out.text))
    high = HighEval(out.mono, out.expanded)
    in_ports = out.meta["ports"]["inputs"]
    out_ports = list(out.meta["ports"]["outputs"])
    rng = random.Random(seed ^ 0xABCD)
    log: list[str] = []

    def _compare(cyc: int) -> None:
        for port in out_ports:
            b = base.peek(port)
            h = high.peek(port)
            if b != h:
                tail = "\n  ".join(log[-25:]) or "(none)"
                raise AssertionError(
                    f"FUZ-3 HighEval/BaseEval divergence seed={seed:#x} "
                    f"cycle {cyc} port {port!r}: BaseEval={b:#x} HighEval={h:#x}\n"
                    f"--- stimulus ---\n  {tail}\n--- program ---\n{blob}"
                )

    # Init seeds must be visible identically at cycle 0 (before any step).
    _compare(0)
    for cyc in range(1, cycles + 1):
        pokes = []
        for port, wires in in_ports.items():
            v = rng.randrange(1 << len(wires))
            base.poke(port, v)
            high.poke(port, v)
            pokes.append(f"{port}={v:#x}")
        log.append(f"cycle {cyc}: poke {' '.join(pokes) or '(no inputs)'}; step(1)")
        base.step()
        high.step()
        _compare(cyc)
    return log


# --------------------------------------------------------------------------- #
# FUZ-3: flatten + HighEval vs BaseEval lockstep (commit-time tier)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("index", range(FUZZ_COUNT))
def test_fuzz_source_high_vs_base(tmp_path, index):
    # FUZ-3: random valid-by-construction high-level program -> flatten (must
    # succeed) -> HighEval vs BaseEval lockstep on random stimulus, every port
    # every cycle. A flatten diagnostic here is itself a FUZ-3 failure (the
    # generator promises validity by construction).
    seed = FUZZ_SEED_BASE + index
    rng = random.Random(seed)
    modules, main = gen_program(rng)
    blob = _render(modules, main)
    try:
        out = _flatten_program(tmp_path, modules, main)
    except Exception as e:  # noqa: BLE001
        raise AssertionError(
            f"FUZ-3 flatten of valid-by-construction program failed "
            f"(seed {seed:#x}): {e!r}\n--- program ---\n{blob}"
        ) from e
    _lockstep_high_vs_base(out, seed, blob, FUZZ_CYCLES)


# --------------------------------------------------------------------------- #
# FUZ-3 (env-gated): continue the strongest cases to compiled C and lockstep.
# --------------------------------------------------------------------------- #


def _cc_available() -> bool:
    from shdlc.cc import CCError, find_cc

    try:
        find_cc()
        return True
    except CCError:
        return False


@pytest.mark.skipif(
    not os.environ.get("SHDLC_SOURCE_FUZZ_CC"),
    reason="C lockstep is opt-in (set SHDLC_SOURCE_FUZZ_CC=1)",
)
@pytest.mark.skipif(not _cc_available(), reason="no C compiler on PATH")
@pytest.mark.parametrize("index", range(min(CC_SUBSET, FUZZ_COUNT)))
def test_fuzz_source_compiled_c(tmp_path, index):
    # FUZ-3 (deepest tier): the same generated program, flattened and compiled
    # all the way to a shared library via shdlc, lockstep-compared cycle by
    # cycle against BaseEval (the C side never sources an expected value).
    from shdlc.cc import lib_suffix
    from shdlc.compile import build_library
    from shdlc.harness import STRICT_CFLAGS, Sim

    seed = FUZZ_SEED_BASE + index
    rng = random.Random(seed)
    modules, main = gen_program(rng)
    blob = _render(modules, main)
    out = _flatten_program(tmp_path, modules, main)

    base_text = out.text
    lib = tmp_path / f"fuzz{index}{lib_suffix()}"
    try:
        build_library(base_text, lib, cflags=STRICT_CFLAGS)
    except Exception as e:  # noqa: BLE001
        raise AssertionError(
            f"FUZ-3 build of valid program failed (seed {seed:#x}): {e!r}\n"
            f"--- base shdl ---\n{base_text}\n--- program ---\n{blob}"
        ) from e
    sim = Sim(lib)
    sim.reset()
    oracle = BaseEval(parse_base(base_text))

    in_ports = out.meta["ports"]["inputs"]
    out_ports = list(out.meta["ports"]["outputs"])
    widths = {n: len(w) for n, w in in_ports.items()}
    drive = random.Random(seed ^ 0xC0FFEE)
    log: list[str] = []
    for cyc in range(1, FUZZ_CYCLES + 1):
        pokes = []
        for port in in_ports:
            raw = drive.getrandbits(64)
            sim.poke(port, raw)  # the lib must mask to port width
            oracle.poke(port, raw & ((1 << widths[port]) - 1))
            pokes.append(f"{port}={raw & ((1 << widths[port]) - 1):#x}")
        sim.step(1)
        oracle.step(1)
        log.append(f"cycle {cyc}: poke {' '.join(pokes) or '(no inputs)'}; step(1)")
        for port in out_ports:
            got = sim.peek(port)
            want = oracle.peek(port)
            if got != want:
                tail = "\n  ".join(log[-25:]) or "(none)"
                raise AssertionError(
                    f"FUZ-3 C/BaseEval divergence seed={seed:#x} cycle {cyc} "
                    f"port {port!r}: lib={got:#x} BaseEval={want:#x}\n"
                    f"--- stimulus ---\n  {tail}\n"
                    f"--- base shdl ---\n{base_text}\n--- program ---\n{blob}"
                )


# --------------------------------------------------------------------------- #
# Generator self-tests: the corpus the fuzzer rides on must hold its own
# valid-by-construction and feature-coverage contracts (so a future generator
# edit that quietly stops exercising, say, generators or params is caught).
# --------------------------------------------------------------------------- #


def test_generator_is_deterministic():
    # FUZ-3: byte-identical text for the same seed (seed-stable replay).
    a = gen_program(random.Random(0x1234))
    b = gen_program(random.Random(0x1234))
    assert a == b


def test_generator_feature_coverage():
    # FUZ-3: over a fixed seed window the generator must actually emit each
    # high-level feature class the obligation enumerates — params, generators
    # (single/compound/open + nesting), conditionals (full operator set,
    # when/else, decl- & conn-context), slices (all four forms), concat,
    # replication (incl. nested/multi-item), constants (+ width assertion &
    # per-bit refs), init, and a >=2-level hierarchy with imports.
    seen = {
        "param_default": False,
        "param_positional": False,
        "param_named": False,
        "param_dependent": False,
        "gen_single": False,
        "gen_compound": False,
        "gen_open": False,
        "gen_nested": False,  # >=2 levels
        "gen_nested3": False,  # 3 levels (the obligation's "nesting to 3")
        "when": False,
        "relop_eq": False,
        "relop_ne": False,
        "relop_lt": False,
        "relop_le": False,
        "relop_gt": False,
        "relop_ge": False,
        "bool_and": False,
        "bool_or": False,
        "paren_bool": False,
        "slice_range": False,  # [a:b]
        "slice_bit": False,  # [k]
        "concat": False,
        "replication": False,
        "constant": False,
        "const_width_assert": False,
        "init_block": False,
        "import": False,
        "multi_module": False,
    }
    import re

    for index in range(120):
        rng = random.Random(FUZZ_SEED_BASE + index)
        modules, main = gen_program(rng)
        if len(modules) > 1:
            seen["multi_module"] = True
        for txt in modules.values():
            if "use " in txt:
                seen["import"] = True
            if re.search(r":\s*\w+;", txt):
                seen["param_default"] = True
            if re.search(r"<\s*\d+\s*>", txt) or re.search(r"<\s*N[^=]*>", txt):
                seen["param_positional"] = True
            if re.search(r"<\s*N\s*=", txt):
                seen["param_named"] = True
            if re.search(r"<\s*N\s*[+*]", txt) or re.search(r"=\s*N\s*[+*]", txt):
                seen["param_dependent"] = True
            if ">i[" in txt or ">j[" in txt:
                if re.search(r">\w+\[\d+:\d+,", txt):
                    seen["gen_compound"] = True
                elif re.search(r">\w+\[\d+:\]", txt):
                    seen["gen_open"] = True
                elif re.search(r">\w+\[\d+\]", txt):
                    seen["gen_single"] = True
            if re.search(r">\w+\[[^\]]+\]\s*\{\s*>\w+", txt):
                seen["gen_nested"] = True
            if re.search(r">\w+\[[^\]]+\]\s*\{\s*>\w+\[[^\]]+\]\s*\{\s*>\w+", txt):
                seen["gen_nested3"] = True
            if "when {" in txt:
                seen["when"] = True
            if "==" in txt:
                seen["relop_eq"] = True
            if "!=" in txt:
                seen["relop_ne"] = True
            if re.search(r"[^<>=]<[^<=N]", txt) or re.search(r"<\s*N\s*\+?\s*1?\s*>", txt):
                pass  # '<' is overloaded with param lists; checked via conds below
            # RelOps inside a when condition (unambiguous there).
            for cond in re.findall(r"when\s*\{([^}]*)\}", txt):
                if "<=" in cond:
                    seen["relop_le"] = True
                if ">=" in cond:
                    seen["relop_ge"] = True
                if re.search(r"[^<>=]<[^<=]", cond):
                    seen["relop_lt"] = True
                if re.search(r"[^<>=-]>[^>=]", cond):
                    seen["relop_gt"] = True
                if "&&" in cond:
                    seen["bool_and"] = True
                if "||" in cond:
                    seen["bool_or"] = True
                if "(" in cond:
                    seen["paren_bool"] = True
            if re.search(r"\[\d+:\d+\]", txt):
                seen["slice_range"] = True
            if re.search(r"\.\w+\[\d+\]|[A-Z]\[\d+\]\s*->", txt) or re.search(r"K\[\d+\]", txt):
                seen["slice_bit"] = True
            if re.search(r"\{[^}]*,[^}]*\}", txt):
                seen["concat"] = True
            if re.search(r"\d+\{", txt):
                seen["replication"] = True
            if re.search(r"K(\[\d+\])?\s*=\s*\d+;", txt):
                seen["constant"] = True
            if re.search(r"K\[\d+\]\s*=", txt):
                seen["const_width_assert"] = True
            if "init {" in txt:
                seen["init_block"] = True

    missing = sorted(k for k, v in seen.items() if not v)
    assert not missing, f"generator never emitted: {missing}"


def test_all_generated_programs_flatten_and_agree(tmp_path):
    # FUZ-3 smoke: a tight loop over the default window proving the whole chain
    # (flatten + HighEval/BaseEval lockstep) is green — a fast guard that lives
    # outside the parametrized cases so a generator regression fails one obvious
    # test rather than scattering across N parametrizations.
    for index in range(min(FUZZ_COUNT, 10)):
        seed = FUZZ_SEED_BASE + 1000 + index
        rng = random.Random(seed)
        modules, main = gen_program(rng)
        blob = _render(modules, main)
        sub = tmp_path / f"p{index}"
        sub.mkdir()
        try:
            out = _flatten_program(sub, modules, main)
        except Exception as e:  # noqa: BLE001
            raise AssertionError(
                f"FUZ-3 flatten failed (seed {seed:#x}): {e!r}\n--- program ---\n{blob}"
            ) from e
        _lockstep_high_vs_base(out, seed, blob, 8)
