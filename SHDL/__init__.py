"""Backward-compatibility shim for the pre-1.0 ``SHDL`` import package.

Historically the driver was imported as ``from SHDL import Circuit``. The 1.0
rewrite moved the user-facing API to the :mod:`pyshdl` package; this shim
re-exports that public surface so existing code keeps working. Prefer importing
from ``pyshdl`` directly.

Only the documented user-facing API (``Circuit`` plus the public error and info
types) is re-exported. The old internal modules (lexer/parser/flattener/compiler
helpers) are not reproduced — that architecture was replaced by the standalone
``flattener`` and ``shdlc`` packages.
"""

from __future__ import annotations

import warnings

from pyshdl import (
    BuildError,
    Circuit,
    CircuitInfo,
    ClosedCircuitError,
    CompilationError,
    CompileError,
    FlattenError,
    MetadataUnavailableError,
    PortInfo,
    PortValueError,
    PySHDLError,
    SettleRefusedError,
    SignalNotFoundError,
    SimulationError,
    TimingInfo,
    __version__,
)

warnings.warn(
    "Importing from `SHDL` is deprecated; import from `pyshdl` instead "
    "(e.g. `from pyshdl import Circuit`). The `SHDL` shim will be removed in a "
    "future release.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "BuildError",
    "Circuit",
    "CircuitInfo",
    "ClosedCircuitError",
    "CompilationError",
    "CompileError",
    "FlattenError",
    "MetadataUnavailableError",
    "PortInfo",
    "PortValueError",
    "PySHDLError",
    "SettleRefusedError",
    "SignalNotFoundError",
    "SimulationError",
    "TimingInfo",
    "__version__",
]
