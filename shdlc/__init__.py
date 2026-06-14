"""shdlc — Base SHDL to C compiler (back-end of the SHDL toolchain).

Takes a Base SHDL artifact (single-bit structural core + ``meta`` JSON,
base_shdl.md) and generates simple, correct, readable C implementing the
unit-delay simulation model (shdl.md §11) behind the release ABI
``reset``/``poke``/``peek``/``step`` (shdlc_goals.md §2).
"""

from __future__ import annotations

__version__ = "1.0.0"

from .compile import build_library, compile_text

__all__ = ["build_library", "compile_text", "__version__"]
