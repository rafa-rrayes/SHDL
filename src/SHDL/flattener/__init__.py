"""
SHDL Flattener Package

Parses Expanded SHDL and flattens it to Base SHDL.
"""

from .tokens import Token, TokenType, KEYWORDS
from .lexer import Lexer
from .ast import (
    Module, Component, Port, Instance, Constant, Connection,
    Signal, IndexExpr, ArithmeticExpr, NumberLiteral, VariableRef, BinaryOp,
    Generator, RangeSpec, SimpleRange, StartEndRange, MultiRange,
    Import, ConnectBlock, Node
)
from .parser import Parser, parse, parse_file
from .flattener import Flattener, flatten_file, format_base_shdl

__all__ = [
    # Tokens
    "Token",
    "TokenType",
    "KEYWORDS",
    
    # Lexer
    "Lexer",
    
    # AST Nodes
    "Module",
    "Component", 
    "Port",
    "Instance",
    "Constant",
    "Connection",
    "Signal",
    "IndexExpr",
    "ArithmeticExpr",
    "NumberLiteral",
    "VariableRef",
    "BinaryOp",
    "Generator",
    "RangeSpec",
    "SimpleRange",
    "StartEndRange",
    "MultiRange",
    "Import",
    "ConnectBlock",
    "Node",
    
    # Parser
    "Parser",
    "parse",
    "parse_file",
    
    # Flattener
    "Flattener",
    "flatten_file",
    "format_base_shdl",
]
