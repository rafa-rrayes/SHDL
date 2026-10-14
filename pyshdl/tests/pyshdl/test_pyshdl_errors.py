"""Error surfaces: structured flatten diagnostics, C-compiler stderr, Base
SHDL rejection, the bare-library degradation matrix, and the exception
hierarchy itself."""

from __future__ import annotations

import pytest

from flattener.diagnostics import Diagnostic, ErrorCode
from SHDL import (
    BuildError,
    Circuit,
    CompilationError,
    CompileError,
    FlattenError,
    MetadataUnavailableError,
    PortValueError,
    PySHDLError,
    SignalNotFoundError,
    SimulationError,
)

# -- flattening -------------------------------------------------------------------


def test_flatten_error_carries_the_structured_diagnostic():
    bad = "top component Bad(A) -> (O) { connect { A -> nope.X; } }"
    with pytest.raises(FlattenError) as exc:
        Circuit.from_source(bad)
    diag = exc.value.diagnostic
    assert isinstance(diag, Diagnostic)
    assert diag.code is ErrorCode.E0307
    # The message is the diagnostic's readable rendering: file:line:col + code.
    assert str(exc.value) == str(diag)
    assert "circuit.shdl:1:" in str(exc.value)
    assert "error[E0307]" in str(exc.value)


def test_flatten_error_on_unresolvable_import():
    with pytest.raises(FlattenError, match=r"module 'noSuchModule' not found"):
        Circuit.from_source(
            "use noSuchModule::{X};\ntop component T(A) -> (O) { x: X; "
            "connect { A -> x.A; x.O -> O; } }"
        )


# -- Base SHDL compilation -----------------------------------------------------------


def test_compile_error_on_base_syntax():
    with pytest.raises(CompileError, match="invalid Base SHDL"):
        Circuit.from_base("component Broken(")


def test_compile_error_on_structural_violation():
    with pytest.raises(CompileError, match="invalid circuit"):
        Circuit.from_base("component Bad(A) -> (O) { connect { } }")


# -- the C compiler ---------------------------------------------------------------------


def test_build_error_when_no_compiler_is_found(examples):
    with pytest.raises(BuildError, match="not-a-real-compiler"):
        Circuit.from_base(examples.base_text("inverter"), cc="not-a-real-compiler")


def test_build_error_carries_argv_and_stderr(examples):
    flags = ("-shared", "-fPIC", "--pyshdl-bogus-flag")
    with pytest.raises(BuildError) as exc:
        Circuit.from_base(examples.base_text("inverter"), cflags=flags)
    assert "--pyshdl-bogus-flag" in exc.value.argv
    assert exc.value.stderr  # the compiler's own words, verbatim
    assert exc.value.stderr in str(exc.value)


# -- typed dispatch ------------------------------------------------------------------------


def test_from_base_rejects_other_types():
    with pytest.raises(TypeError, match="str.*PathLike|PathLike"):
        Circuit.from_base(b"component X() -> () {}")
    with pytest.raises(TypeError):
        Circuit.from_base(123)


# -- bare-library degradation (documented, explicit) ------------------------------------------


def test_bare_library_degradation_matrix(examples):
    lib, _ = examples.artifacts("adder8")
    with Circuit.from_library(lib) as bare:
        for feature in (
            lambda: bare.inputs,
            lambda: bare.outputs,
            lambda: bare.info,
            lambda: bare.timing,
            lambda: bare.settle(),
            lambda: bare.run_batch([{}]),
            lambda: "A" in bare,
        ):
            with pytest.raises(MetadataUnavailableError):
                feature()


def test_bare_library_poke_peek_pass_through(examples):
    lib, _ = examples.artifacts("adder8")
    with Circuit.from_library(lib) as bare:
        bare.poke("A", 5)
        bare.poke("B", 6)
        bare.step(40)
        assert bare.peek("Sum") == 11
        # The documented C unknown-name path: error-and-do-nothing, peek = 0.
        assert bare.peek("definitely-not-a-port") == 0
        assert bare.name == lib.stem
        assert not bare.strict


def test_bare_library_strict_is_rejected(examples):
    lib, _ = examples.artifacts("adder8")
    with pytest.raises(MetadataUnavailableError, match="strict"):
        Circuit.from_library(lib, strict=True)


def test_library_with_base_restores_everything(examples):
    lib, base = examples.artifacts("adder8")
    with Circuit.from_library(lib, base=base) as c:
        assert c.inputs == ("A", "B", "Cin")
        assert c.timing is not None
        assert c.strict  # defaults to strict once metadata is available
        with pytest.raises(PortValueError):
            c.poke("A", 1 << 20)


# -- hierarchy ------------------------------------------------------------------------------------


def test_exception_hierarchy():
    assert issubclass(CompilationError, PySHDLError)
    assert issubclass(FlattenError, CompilationError)
    assert issubclass(CompileError, CompilationError)
    assert issubclass(BuildError, CompilationError)
    assert issubclass(SimulationError, PySHDLError)
    assert issubclass(SignalNotFoundError, SimulationError)
    assert issubclass(SignalNotFoundError, KeyError)
    assert issubclass(PortValueError, SimulationError)
    assert issubclass(PortValueError, ValueError)


def test_signal_not_found_str_is_readable(examples):
    # KeyError's repr-style rendering is overridden: the message reads as text.
    with examples.fresh("adder8") as c:
        with pytest.raises(SignalNotFoundError) as exc:
            c.peek("nope")
        assert str(exc.value).startswith("unknown signal 'nope'")
