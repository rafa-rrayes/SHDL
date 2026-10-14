"""The Circuit class: SHDL's ergonomic Python front door.

A Circuit owns one compiled simulation end to end: it runs the in-process
pipeline (flattener -> shdlc -> C compiler -> dlopen), keeps the build
artifacts in a managed directory, validates every port access in Python
*before* it reaches C, and exposes the release ABI as poke/peek/step plus
dict-style access and a context manager.

Construction is explicit — there is no content sniffing:

- ``Circuit(path)``              — a ``.shdl`` file (the front door).
- ``Circuit.from_source(text)``  — SHDL source held in a string.
- ``Circuit.from_base(base)``    — Base SHDL; a ``str`` is artifact text, a
  path object (``os.PathLike``) is a file to read.
- ``Circuit.from_library(lib)``  — a prebuilt shared library, with optional
  ``base=...`` supplying the metadata a bare library cannot.

Every constructor ends by loading a uniquely named *copy* of the shared
library: dlopen caches by path, so loading one file twice would silently
share a single global simulation state. The per-instance copy guarantees
two Circuits never share state, whatever they were built from.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from flattener.diagnostics import SHDLError
from flattener.pipeline import flatten_program
from shdlc.baseshdl import BaseComponent, BaseParseError, parse_base
from shdlc.cc import CCError, build_shared, lib_suffix
from shdlc.codegen import generate_c
from shdlc.harness import identity_ports, load_fresh_copy
from shdlc.model import ModelError, build_circuit

from .errors import (
    BuildError,
    ClosedCircuitError,
    CompileError,
    FlattenError,
    MetadataUnavailableError,
    PortValueError,
    SettleRefusedError,
    SignalNotFoundError,
)
from .info import CircuitInfo, PortInfo, TimingInfo, info_from_meta

#: step/step_settle/run_batch cross the ABI as a C ``int``.
_MAX_CYCLES = 2**31 - 1

#: poke crosses the ABI as a ``uint64_t``; without port metadata this is the
#: only masking PySHDL can apply.
_U64_MASK = 2**64 - 1

_MODULE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _check_cycles(cycles: int) -> int:
    if not isinstance(cycles, int):
        raise TypeError(f"cycles must be an int, got {type(cycles).__name__}")
    if not 0 <= cycles <= _MAX_CYCLES:
        raise ValueError(f"cycles must be in 0..{_MAX_CYCLES}, got {cycles}")
    return cycles


def _typed_text(base: str | os.PathLike[str]) -> str:
    """Typed dispatch, never sniffing: a str is text, a path object a file."""
    if isinstance(base, os.PathLike):
        return Path(base).read_text(encoding="utf-8")
    if isinstance(base, str):
        return base
    raise TypeError(
        "base must be Base SHDL text (str) or a path to it (os.PathLike), "
        f"got {type(base).__name__}"
    )


def _validated_parse(text: str) -> BaseComponent:
    """Parse Base SHDL and run the compiler's full structural validation.

    Returns the component with ``ports`` defaulted to identity single-bit
    groups when the block is wholly absent (model invariant 7), so the
    metadata-driven surface works for handwritten artifacts too.
    """
    try:
        comp = parse_base(text)
    except BaseParseError as e:
        raise CompileError(f"invalid Base SHDL: {e}") from e
    try:
        build_circuit(comp)
    except ModelError as e:
        raise CompileError(f"invalid circuit: {e}") from e
    comp.meta.setdefault("ports", identity_ports(comp))
    return comp


def _prepare_dir(build_dir: str | os.PathLike[str] | None) -> tuple[Path, bool]:
    """The artifact directory and whether this instance owns (may delete) it."""
    if build_dir is not None:
        directory = Path(build_dir)
        directory.mkdir(parents=True, exist_ok=True)
        return directory, False
    return Path(tempfile.mkdtemp(prefix="shdl-")), True


class Circuit:
    """One independent simulation of a compiled SHDL circuit.

    Use as a context manager (recommended) or call :meth:`close` when done;
    by default every build artifact lives in a managed temporary directory
    that ``close()`` removes. Pass ``keep_artifacts=True`` (or an explicit
    ``build_dir=...``) to retain the flattened Base SHDL, the generated C,
    and the shared library for inspection under :attr:`build_dir`.

    ``strict=True`` (the default) validates every poke in Python: unknown
    names and values that do not fit the port raise immediately, and
    negative values encode as two's complement within the port's width.
    ``strict=False`` defers to the ABI's documented masking (mod 2^width).
    """

    # Class-level default so ``__del__`` after a failed construction no-ops.
    _closed: bool = True

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        top: str | None = None,
        include_dirs: Sequence[str | os.PathLike[str]] = (),
        strict: bool = True,
        build_dir: str | os.PathLike[str] | None = None,
        keep_artifacts: bool = False,
        cc: str | None = None,
        cflags: Sequence[str] | None = None,
    ):
        dirs = [os.fspath(d) for d in include_dirs]
        try:
            flat = flatten_program(os.fspath(path), dirs or None, top)
        except SHDLError as e:
            raise FlattenError(e.diagnostic) from e
        self._setup_from_base(
            flat.text,
            strict=strict,
            build_dir=build_dir,
            keep_artifacts=keep_artifacts,
            cc=cc,
            cflags=cflags,
        )

    @classmethod
    def from_source(
        cls,
        text: str,
        *,
        name: str = "circuit",
        top: str | None = None,
        include_dirs: Sequence[str | os.PathLike[str]] = (),
        strict: bool = True,
        build_dir: str | os.PathLike[str] | None = None,
        keep_artifacts: bool = False,
        cc: str | None = None,
        cflags: Sequence[str] | None = None,
    ) -> Circuit:
        """Compile SHDL source held in a string.

        ``name`` is the module name the text is written under (it must be a
        valid identifier); imports in the text resolve from ``include_dirs``.
        """
        if not _MODULE_NAME.fullmatch(name):
            raise ValueError(f"module name must be an identifier, got {name!r}")
        with tempfile.TemporaryDirectory(prefix="shdl-source-") as tmp:
            src = Path(tmp) / f"{name}.shdl"
            src.write_text(text, encoding="utf-8")
            return cls(
                src,
                top=top,
                include_dirs=include_dirs,
                strict=strict,
                build_dir=build_dir,
                keep_artifacts=keep_artifacts,
                cc=cc,
                cflags=cflags,
            )

    @classmethod
    def from_base(
        cls,
        base: str | os.PathLike[str],
        *,
        strict: bool = True,
        build_dir: str | os.PathLike[str] | None = None,
        keep_artifacts: bool = False,
        cc: str | None = None,
        cflags: Sequence[str] | None = None,
    ) -> Circuit:
        """Compile a Base SHDL artifact: text if ``base`` is a str, a file if
        it is a path object (typed dispatch — never content sniffing)."""
        self = cls.__new__(cls)
        self._setup_from_base(
            _typed_text(base),
            strict=strict,
            build_dir=build_dir,
            keep_artifacts=keep_artifacts,
            cc=cc,
            cflags=cflags,
        )
        return self

    @classmethod
    def from_library(
        cls,
        lib_path: str | os.PathLike[str],
        *,
        base: str | os.PathLike[str] | None = None,
        strict: bool | None = None,
        build_dir: str | os.PathLike[str] | None = None,
        keep_artifacts: bool = False,
    ) -> Circuit:
        """Load a prebuilt shared library (no compilation).

        A bare library exports only the six ABI symbols — port names, widths,
        timing, and init seeds are unrecoverable from it. Pass ``base=...``
        (the Base SHDL it was compiled from; str = text, path object = file)
        to restore full metadata. Without it the circuit degrades explicitly:

        - ``poke``/``peek`` pass names straight through to the C library,
          whose unknown-name path reports an error and does nothing
          (``peek`` then returns 0) — PySHDL cannot pre-validate.
        - ``inputs``/``outputs``/``info``/``in``/``settle()``/``run_batch()``
          raise :class:`MetadataUnavailableError`.
        - ``strict`` defaults to False and requesting True raises, since
          width validation is impossible.
        """
        lib = Path(os.fspath(lib_path))
        if not lib.is_file():
            raise FileNotFoundError(f"shared library not found: {lib}")
        if strict is None:
            strict = base is not None
        if strict and base is None:
            raise MetadataUnavailableError(
                "strict validation requires port metadata; pass base=... or strict=False"
            )
        comp = _validated_parse(_typed_text(base)) if base is not None else None
        self = cls.__new__(cls)
        directory, owns = _prepare_dir(build_dir)
        try:
            self._attach(
                name=comp.name if comp is not None else lib.stem,
                meta=comp.meta if comp is not None else None,
                lib_path=lib,
                strict=strict,
                directory=directory,
                owns_dir=owns,
                keep=keep_artifacts,
            )
        except BaseException:
            if owns:
                shutil.rmtree(directory, ignore_errors=True)
            raise
        return self

    # -- construction internals ----------------------------------------------

    def _setup_from_base(
        self,
        text: str,
        *,
        strict: bool,
        build_dir: str | os.PathLike[str] | None,
        keep_artifacts: bool,
        cc: str | None,
        cflags: Sequence[str] | None,
    ) -> None:
        comp = _validated_parse(text)
        circuit = build_circuit(comp)  # cannot fail: _validated_parse just did
        directory, owns = _prepare_dir(build_dir)
        try:
            (directory / f"{comp.name}.base.shdl").write_text(text, encoding="utf-8")
            c_path = directory / f"{comp.name}.c"
            c_path.write_text(generate_c(circuit), encoding="utf-8")
            try:
                lib = build_shared(
                    c_path, directory / f"{comp.name}{lib_suffix()}", cc=cc, cflags=cflags
                )
            except CCError as e:
                raise BuildError(str(e), argv=e.argv, stderr=e.stderr) from e
            self._attach(
                name=comp.name,
                meta=comp.meta,
                lib_path=lib,
                strict=strict,
                directory=directory,
                owns_dir=owns,
                keep=keep_artifacts,
            )
        except BaseException:
            if owns:
                shutil.rmtree(directory, ignore_errors=True)
            raise

    def _attach(
        self,
        *,
        name: str,
        meta: dict | None,
        lib_path: Path,
        strict: bool,
        directory: Path,
        owns_dir: bool,
        keep: bool,
    ) -> None:
        self._name = name
        self._strict = strict
        self._dir = directory
        self._owns_dir = owns_dir
        self._keep = keep
        if meta is not None:
            self._info: CircuitInfo | None = info_from_meta(name, meta)
            self._in_table: dict[str, PortInfo] | None = {p.name: p for p in self._info.inputs}
            self._out_table: dict[str, PortInfo] | None = {p.name: p for p in self._info.outputs}
        else:
            self._info = None
            self._in_table = None
            self._out_table = None
        # The independence guarantee: a uniquely named copy per instance.
        self._sim = load_fresh_copy(lib_path, directory)
        self._closed = False

    # -- simulation ------------------------------------------------------------

    def poke(self, name: str, value: int) -> None:
        """Set input port ``name`` to ``value`` (bit 0 = the port's LSB)."""
        sim = self._live()
        if self._in_table is None:  # bare library: pass through, mask to the ABI's u64
            if not isinstance(value, int):
                raise TypeError(f"poke value must be an int, got {type(value).__name__}")
            sim.poke(name, value & _U64_MASK)
            return
        port = self._in_table.get(name)
        if port is None:
            raise SignalNotFoundError(self._no_such_input(name))
        sim.poke(name, self._encode(port, value))

    def peek(self, name: str) -> int:
        """Read port ``name`` (input or output), zero-extended to an int.

        Reading an output evaluates one pending cycle first if inputs changed
        since the last evaluation (the ABI's lazy-peek rule).
        """
        sim = self._live()
        if (
            self._in_table is not None
            and name not in self._in_table
            and name not in self._out_table
        ):
            raise SignalNotFoundError(self._no_such_signal(name))
        return sim.peek(name)

    def step(self, cycles: int = 1) -> None:
        """Advance exactly ``cycles`` unit-delay cycles (one gate level each)."""
        self._live().step(_check_cycles(cycles))

    def step_settle(self, cycles: int = 1) -> int:
        """``step(cycles)`` with fixed-point early exit; observably identical.

        Returns the number of cycles actually run (< ``cycles`` iff the gate
        state stopped changing first; oscillators always run all of them).
        """
        return self._live().step_settle(_check_cycles(cycles))

    def settle(self) -> int:
        """Advance exactly ``timing.max_depth`` cycles — just ``step(max_depth)``.

        Returns the number of cycles run (equal to ``max_depth`` when it settles).

        Only meaningful for combinational circuits: raises
        :class:`SettleRefusedError` when the circuit has feedback (a latch or
        oscillator has no guaranteed fixed point — use ``step(n)`` instead).
        """
        sim = self._live()
        info = self._info_or_raise("settle()")
        if info.timing is None:
            raise MetadataUnavailableError(
                "settle() requires timing metadata, which this circuit's Base SHDL lacks"
            )
        if info.timing.has_feedback:
            raise SettleRefusedError(
                f"settle() is refused: circuit {self._name!r} has feedback, so "
                "max_depth is not a settle count; advance it explicitly with step(n)"
            )
        sim.step(info.timing.max_depth)
        return info.timing.max_depth

    def reset(self) -> None:
        """Return to the power-on state: all-zero except the ``init`` seeds."""
        self._live().reset()

    def run_batch(
        self,
        frames: Sequence[Mapping[str, int]],
        *,
        cycles: int = 1,
        settle: bool = False,
    ) -> list[dict[str, int]]:
        """Drive many input frames through the circuit in one C call.

        Each frame maps input-port names to values; inputs a frame omits hold
        their current value. Per frame the circuit applies the pokes, advances
        ``cycles`` cycles (via the fixed-point early exit when ``settle``),
        and records every output port — observably identical to the same
        poke/step/peek loop, minus the per-call FFI overhead. Returns one
        ``{output_name: value}`` dict per frame.
        """
        sim = self._live()
        info = self._info_or_raise("run_batch()")
        n_cycles = _check_cycles(cycles)
        in_ports = info.inputs
        out_names = [p.name for p in info.outputs]
        index = {p.name: i for i, p in enumerate(in_ports)}
        current = [sim.peek(p.name) for p in in_ports]  # omitted inputs hold
        rows: list[tuple[int, ...]] = []
        for frame_no, frame in enumerate(frames):
            for key, value in frame.items():
                slot = index.get(key)
                if slot is None:
                    raise SignalNotFoundError(f"frame {frame_no}: {self._no_such_input(key)}")
                current[slot] = self._encode(in_ports[slot], value)
            rows.append(tuple(current))
        out_rows = sim.run_batch(rows, len(out_names), n_cycles, settle=settle)
        return [dict(zip(out_names, row)) for row in out_rows]

    # -- dict-style access -------------------------------------------------------

    def __getitem__(self, name: str) -> int:
        return self.peek(name)

    def __setitem__(self, name: str, value: int) -> None:
        self.poke(name, value)

    def __contains__(self, name: str) -> bool:
        self._info_or_raise("'in'")
        return name in self._in_table or name in self._out_table

    # -- introspection -------------------------------------------------------------

    @property
    def name(self) -> str:
        """The circuit's component name (the library stem for bare loads)."""
        return self._name

    @property
    def strict(self) -> bool:
        """Whether pokes are range-validated in Python (see class docstring)."""
        return self._strict

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def info(self) -> CircuitInfo:
        """Port, timing, init, and stats metadata (read-only)."""
        return self._info_or_raise("info")

    @property
    def timing(self) -> TimingInfo | None:
        """The ``timing`` metadata block, or None when the artifact lacks it."""
        return self._info_or_raise("timing").timing

    @property
    def inputs(self) -> tuple[str, ...]:
        """Input port names, in declaration order."""
        return tuple(p.name for p in self._info_or_raise("inputs").inputs)

    @property
    def outputs(self) -> tuple[str, ...]:
        """Output port names, in declaration order."""
        return tuple(p.name for p in self._info_or_raise("outputs").outputs)

    @property
    def build_dir(self) -> Path:
        """Where this instance's artifacts live (a managed temp dir unless
        ``build_dir=...`` was given; removed on close unless retained)."""
        return self._dir

    def __repr__(self) -> str:
        if self._closed:
            return f"<SHDL.Circuit {self._name!r} (closed)>"
        if self._info is None:
            return f"<SHDL.Circuit {self._name!r} (no metadata)>"

        def group(ports: tuple[PortInfo, ...]) -> str:
            return (
                ", ".join(p.name if p.width == 1 else f"{p.name}[{p.width}]" for p in ports)
                or "none"
            )

        return (
            f"<SHDL.Circuit {self._name!r} "
            f"({group(self._info.inputs)}) -> ({group(self._info.outputs)})>"
        )

    # -- lifecycle ---------------------------------------------------------------

    def close(self) -> None:
        """Release the simulation and remove owned artifacts; idempotent."""
        if self._closed:
            return
        self._closed = True
        self._sim = None
        if self._owns_dir and not self._keep:
            shutil.rmtree(self._dir, ignore_errors=True)

    def __enter__(self) -> Circuit:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()

    # -- internals ----------------------------------------------------------------

    def _live(self):
        if self._closed:
            raise ClosedCircuitError(f"circuit {self._name!r} has been closed")
        return self._sim

    def _encode(self, port: PortInfo, value: int) -> int:
        if not isinstance(value, int):
            raise TypeError(f"port {port.name!r} value must be an int, got {type(value).__name__}")
        if self._strict and not port.min_value <= value <= port.max_value:
            raise PortValueError(
                f"value {value} does not fit {port.width}-bit port {port.name!r} "
                f"(allowed {port.min_value}..{port.max_value}); "
                "use strict=False for the ABI's masking semantics"
            )
        return value & port.max_value

    def _info_or_raise(self, feature: str) -> CircuitInfo:
        if self._info is None:
            raise MetadataUnavailableError(
                f"{feature} requires Base SHDL metadata, and this circuit was "
                "loaded from a bare library; pass base=... to from_library"
            )
        return self._info

    def _no_such_input(self, name: str) -> str:
        available = ", ".join(self._in_table) or "none"
        if name in self._out_table:
            return f"{name!r} is an output port and cannot be poked; inputs: {available}"
        return f"unknown input port {name!r}; inputs: {available}"

    def _no_such_signal(self, name: str) -> str:
        return (
            f"unknown signal {name!r}; "
            f"inputs: {', '.join(self._in_table) or 'none'}; "
            f"outputs: {', '.join(self._out_table) or 'none'}"
        )
