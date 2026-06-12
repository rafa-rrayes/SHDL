"""The PySHDL exception family.

Everything PySHDL raises deliberately derives from :class:`PySHDLError`, in
two branches mirroring a circuit's life: :class:`CompilationError` covers
turning source into a loaded library (flattening, Base SHDL validation, the
C compiler), :class:`SimulationError` covers driving the loaded circuit
(name lookup, value validation, settle refusal, lifecycle misuse).

Each compilation subclass carries the underlying tool's structured failure
verbatim — :attr:`FlattenError.diagnostic` is the flattener's positioned
diagnostic, :attr:`BuildError.stderr` the C compiler's output — so callers
never have to re-parse a message to learn what went wrong.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flattener.diagnostics import Diagnostic


class PySHDLError(Exception):
    """Base class for every error PySHDL raises."""


# -- compilation: source -> loaded library -----------------------------------


class CompilationError(PySHDLError):
    """A failure anywhere on the path from source to a loaded library."""


class FlattenError(CompilationError):
    """SHDL -> Base SHDL flattening failed.

    ``diagnostic`` is the flattener's structured diagnostic (error code,
    message, source position); ``str(error)`` is its readable rendering,
    e.g. ``adder8.shdl:14:5: error[E0307]: unknown reference 'fa9'``.
    """

    def __init__(self, diagnostic: Diagnostic):
        self.diagnostic = diagnostic
        super().__init__(str(diagnostic))


class CompileError(CompilationError):
    """Base SHDL -> C compilation failed (syntax or structural violation)."""


class BuildError(CompilationError):
    """The C compiler failed (or could not be found).

    ``argv`` is the full command line attempted (empty if discovery failed);
    ``stderr`` is the C compiler's stderr verbatim (empty if it never ran).
    """

    def __init__(self, message: str, *, argv: list[str] | None = None, stderr: str = ""):
        super().__init__(message)
        self.argv = list(argv or [])
        self.stderr = stderr


# -- simulation: driving a loaded circuit -------------------------------------


class SimulationError(PySHDLError):
    """A failure while driving a loaded circuit."""


class SignalNotFoundError(SimulationError, KeyError):
    """A port name that does not resolve; the message lists what does.

    Also a :class:`KeyError` so dict-style access misses (``circuit["typo"]``)
    behave like any mapping lookup.
    """

    # KeyError.__str__ would render the message repr-quoted; restore normal text.
    __str__ = Exception.__str__


class PortValueError(SimulationError, ValueError):
    """A poke value that does not fit its port under strict validation."""


class SettleRefusedError(SimulationError):
    """``settle()`` on a circuit with feedback.

    A feedback loop (latch, oscillator) has no guaranteed fixed point, so
    ``timing.max_depth`` is not a settle count — advance such a circuit
    explicitly with ``step(n)``.
    """


class MetadataUnavailableError(SimulationError):
    """A feature that needs Base SHDL metadata on a circuit loaded without it.

    A bare prebuilt library exports only the six ABI symbols; port names,
    widths, timing, and init seeds are unrecoverable from it. Pass
    ``base=...`` to :meth:`Circuit.from_library` to restore them.
    """


class ClosedCircuitError(SimulationError):
    """Simulation use of a circuit after ``close()``."""
