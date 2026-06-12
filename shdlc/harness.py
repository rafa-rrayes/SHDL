"""Shared simulation harness over compiled circuit libraries (release ABI).

The ctypes plumbing used everywhere a compiled library or the BaseEval oracle
must be driven: the compiler test-suite (``tests/compiler/harness.py``
re-exports these names), the CPU suite, and the conformance runner
(``conformance.runner``). Moved here verbatim from the test harness so
non-test consumers can import it; semantics are unchanged.
"""

from __future__ import annotations

import ctypes
import itertools
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from .baseshdl import BaseComponent, parse_base
from .sim.base_eval import BaseEval

#: Strict build flags: every build doubles as proof that the generated C is
#: warning-free under -Wall -Wextra -Werror -pedantic.
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
        lib.step_settle.argtypes = [ctypes.c_int]
        lib.step_settle.restype = ctypes.c_int
        lib.run_batch.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        lib.run_batch.restype = None
        self._lib = lib

    def reset(self) -> None:
        self._lib.reset()

    def poke(self, name: str, value: int) -> None:
        self._lib.poke(name.encode("utf-8"), value)

    def peek(self, name: str) -> int:
        return int(self._lib.peek(name.encode("utf-8")))

    def step(self, n: int = 1) -> None:
        self._lib.step(n)

    def step_settle(self, n: int = 1) -> int:
        """``step(n)`` with fixed-point early exit (observably identical).

        Returns the number of ticks actually run: < ``n`` iff the gate state
        reached a fixed point first; oscillators always run all ``n``.
        """
        return int(self._lib.step_settle(n))

    def run_batch(
        self,
        frames: Sequence[Sequence[int]],
        n_out: int,
        cycles: int,
        *,
        settle: bool = False,
    ) -> list[tuple[int, ...]]:
        """Drive ``frames`` through the circuit in one ``run_batch`` call.

        Each frame holds one uint64 per input port in declaration order;
        the result holds one tuple of output-port values per frame.
        Observably identical to poking every port, stepping ``cycles``
        (via ``step_settle`` when ``settle``), and peeking every output
        port, frame by frame.
        """
        count = len(frames)
        flat = [value for frame in frames for value in frame]
        in_buf = (ctypes.c_uint64 * max(1, len(flat)))(*flat)
        out_buf = (ctypes.c_uint64 * max(1, count * n_out))()
        self._lib.run_batch(in_buf, out_buf, count, cycles, 1 if settle else 0)
        return [tuple(out_buf[k * n_out : (k + 1) * n_out]) for k in range(count)]


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
