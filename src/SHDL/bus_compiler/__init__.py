"""
Signal-Width-Aware Code Generator for SHDL

Packs gates that process corresponding bits of the same bus together,
enabling word-level C operations instead of individual bit extractions.
"""

from .compiler import BusCompiler

__all__ = ["BusCompiler"]
