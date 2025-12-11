"""
SHDL Semantic Analysis Module

Provides comprehensive semantic checking for SHDL programs including:
- Component resolution and name checking
- Port validation and width checking
- Connection completeness and correctness
- Generator validation
- Warning detection
"""

from .analyzer import SemanticAnalyzer, analyze, analyze_file
from .resolver import ComponentResolver, SymbolTable
from .type_check import TypeChecker, WidthInfo
from .connection import ConnectionChecker
from .warnings import WarningChecker

__all__ = [
    "SemanticAnalyzer",
    "analyze",
    "analyze_file",
    "ComponentResolver",
    "SymbolTable",
    "TypeChecker",
    "WidthInfo",
    "ConnectionChecker",
    "WarningChecker",
]
