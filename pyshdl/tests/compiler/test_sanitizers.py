"""CCT-5: sanitizer tier -- generated C under -fsanitize=address,undefined.

UB in the generated C (out-of-bounds wire indexing, signed overflow, bad
shifts, NULL misuse) is invisible to a normal differential run. This tier
compiles a representative slice of circuits *together with a driver* into a
sanitized executable and runs it as a subprocess, so AddressSanitizer's
interceptors are installed at process start (they cannot be, reliably, when a
sanitized library is dlopen'd into the Python host -- the macOS limitation).

The driver reproduces a BaseEval-derived trace and self-checks every observed
output; a sanitizer fault or a value mismatch makes the subprocess exit
nonzero. Expected values come from BaseEval, never from the C under test.

Gating: skipped unless a working ``cc`` accepts the sanitizer flags (a one-time
probe). macOS clang and Linux gcc/clang support both sanitizers.
"""

from __future__ import annotations

import json
import subprocess
import textwrap

import pytest

from shdlc.cc import find_cc
from shdlc.compile import compile_text

from .harness import (
    AND_TEXT,
    VCC_NOT_TEXT,
    WIDE64_TEXT,
    make_oracle,
    parse_with_ports,
)

# A cross-coupled NOR (OR+NOT) SR latch: feedback, so the driver exercises the
# two-buffer swap and transient states under the sanitizer.
SR_TEXT = """\
component SanSR(s, r) -> (q, qn) {
    or1: OR;
    n1: NOT;
    or2: OR;
    n2: NOT;
    connect {
        s -> or1.A; n2.O -> or1.B;
        or1.O -> n1.A;
        r -> or2.A; n1.O -> or2.B;
        or2.O -> n2.A;
        n1.O -> q;
        n2.O -> qn;
    }
}
meta { "ports": { "inputs": { "S": ["s"], "R": ["r"] },
                  "outputs": { "Q": ["q"], "Qn": ["qn"] } },
       "init": { "q": 0, "qn": 1 } }
"""

SAN_CFLAGS = (
    "-std=c11",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-pedantic",
    "-O1",
    "-g",
    "-fsanitize=address,undefined",
    "-fno-sanitize-recover=undefined",
    "-fno-omit-frame-pointer",
)


def _sanitizers_available() -> bool:
    """Probe once: does the host cc build and run a trivial sanitized exe?"""
    try:
        cc = find_cc()
    except Exception:
        return False
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "probe.c"
        src.write_text("int main(void){return 0;}\n")
        exe = Path(d) / "probe"
        proc = subprocess.run(
            [*cc, *SAN_CFLAGS, "-o", str(exe), str(src)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return False
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        return run.returncode == 0


_SANITIZERS = _sanitizers_available()

pytestmark = pytest.mark.skipif(
    not _SANITIZERS, reason="cc does not provide a working ASAN/UBSAN toolchain"
)


def _expected_trace(base_text: str, script):
    """BaseEval-derived (input-poke, expected-outputs) trace for the driver."""
    comp = parse_with_ports(base_text)
    ports = comp.meta["ports"]
    in_ports = list(ports["inputs"])
    out_ports = list(ports["outputs"])
    oracle = make_oracle(base_text)
    frames = []
    for pokes in script:
        for port, val in pokes.items():
            oracle.poke(port, val)
        oracle.step(1)
        frames.append((pokes, {p: oracle.peek(p) for p in out_ports}))
    return in_ports, out_ports, frames


def _emit_driver(frames) -> str:
    """A C main() that replays `frames` against the ABI and self-checks."""
    body = []
    for pokes, outs in frames:
        for port, val in pokes.items():
            body.append(f'    poke("{port}", {val}ull);')
        body.append("    step(1);")
        for port, val in outs.items():
            body.append(
                f'    if (peek("{port}") != {val}ull) {{ '
                f'fprintf(stderr, "mismatch {port}\\n"); return 2; }}'
            )
    steps = "\n".join(body)
    return (
        textwrap.dedent(
            """\
        #include <stdint.h>
        #include <stdio.h>
        extern void reset(void);
        extern void poke(const char *s, uint64_t v);
        extern uint64_t peek(const char *s);
        extern void step(int n);
        extern int step_settle(int n);
        int main(void) {
            reset();
        %s
            /* Exercise the guarded cold paths under the sanitizer too. */
            poke(0, 1); (void)peek(0); (void)peek("definitely-unknown");
            (void)step_settle(3);
            return 0;
        }
        """
        )
        % steps
    )


def _build_and_run_sanitized(tmp_path, name, base_text, script):
    in_ports, out_ports, frames = _expected_trace(base_text, script)
    _, c_source = compile_text(base_text)
    c_file = tmp_path / f"{name}.c"
    c_file.write_text(c_source)
    driver = tmp_path / f"{name}_driver.c"
    driver.write_text(_emit_driver(frames))
    exe = tmp_path / f"{name}_san"
    cc = find_cc()
    build = subprocess.run(
        [*cc, *SAN_CFLAGS, "-o", str(exe), str(c_file), str(driver)],
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, f"sanitized build failed:\n{build.stderr}"
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    # A sanitizer fault prints a report and a nonzero exit; a value mismatch
    # exits 2. Either way, surface the full output for replay.
    assert run.returncode == 0, (
        f"sanitized run failed (rc={run.returncode}) for {name}:\n"
        f"--- stdout ---\n{run.stdout}\n--- stderr ---\n{run.stderr}\n"
        f"--- script ---\n{json.dumps(script)}"
    )
    # No leaked sanitizer diagnostics on a clean run.
    assert "runtime error" not in run.stderr, run.stderr
    assert "ERROR: AddressSanitizer" not in run.stderr, run.stderr


# Deterministic scripts (small, hand-fixed): the sanitizer cares about code
# paths exercised, not statistical coverage.
AND_SCRIPT = [{"a": 1, "b": 1}, {"a": 1, "b": 0}, {"b": 1}, {"a": 0}]
VCC_NOT_SCRIPT = [{}, {}, {}, {}]  # zero-input: just steps, watches the trace
SR_SCRIPT = (
    [{"S": 0, "R": 0}] * 2 + [{"S": 1}] * 4 + [{"S": 0}] * 3 + [{"R": 1}] * 4 + [{"R": 0}] * 3
)
WIDE_SCRIPT = [
    {"B": 0xFFFFFFFFFFFFFFFF},
    {"B": 0x8000000000000000},
    {"B": 0xA5A5A5A5A5A5A5A5},
    {"B": 1},
    {"B": 0},
]


@pytest.mark.parametrize(
    ("name", "text", "script"),
    [
        ("and", AND_TEXT, AND_SCRIPT),
        ("vcc_not", VCC_NOT_TEXT, VCC_NOT_SCRIPT),
        ("srlatch", SR_TEXT, SR_SCRIPT),
        ("wide64", WIDE64_TEXT, WIDE_SCRIPT),
    ],
    ids=["and", "vcc_not", "srlatch", "wide64"],
)
def test_generated_c_is_sanitizer_clean(tmp_path, name, text, script):
    # CCT-5: each representative circuit compiles + runs clean under
    # ASAN+UBSAN, matching its BaseEval trace exactly.
    _build_and_run_sanitized(tmp_path, name, text, script)
