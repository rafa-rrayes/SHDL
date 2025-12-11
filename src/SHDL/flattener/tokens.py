"""
SHDL Token Definitions

Defines all token types used by the SHDL lexer.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..source_map import SourceSpan


class TokenType(Enum):
    """All token types in SHDL."""
    
    # Literals
    IDENTIFIER = auto()
    NUMBER = auto()
    
    # Keywords
    COMPONENT = auto()
    USE = auto()
    CONNECT = auto()
    
    # Operators and Delimiters
    ARROW = auto()          # ->
    DOUBLE_COLON = auto()   # ::
    COLON = auto()          # :
    SEMICOLON = auto()      # ;
    COMMA = auto()          # ,
    DOT = auto()            # .
    EQUALS = auto()         # =
    LBRACE = auto()         # {
    RBRACE = auto()         # }
    LBRACKET = auto()       # [
    RBRACKET = auto()       # ]
    LPAREN = auto()         # (
    RPAREN = auto()         # )
    GREATER = auto()        # > (generator prefix)
    
    # Arithmetic operators
    PLUS = auto()           # +
    MINUS = auto()          # -
    STAR = auto()           # *
    SLASH = auto()          # /
    
    # Special
    EOF = auto()
    NEWLINE = auto()


@dataclass(frozen=True)
class Token:
    """
    A single token from the SHDL source.
    
    Includes both start and end positions for precise error reporting.
    """
    
    type: TokenType
    value: Any
    line: int
    column: int
    end_line: int = None  # type: ignore
    end_column: int = None  # type: ignore
    file_path: str = "<string>"
    
    def __post_init__(self):
        # Handle default end positions
        if self.end_line is None:
            object.__setattr__(self, 'end_line', self.line)
        if self.end_column is None:
            # Default end column based on value length
            value_len = len(str(self.value)) if self.value is not None else 1
            object.__setattr__(self, 'end_column', self.column + value_len - 1)
    
    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"
    
    @property
    def span(self) -> "SourceSpan":
        """Get the source span for this token."""
        from ..source_map import SourceSpan
        return SourceSpan(
            file_path=self.file_path,
            start_line=self.line,
            start_col=self.column,
            end_line=self.end_line,
            end_col=self.end_column
        )
    
    def with_file_path(self, file_path: str) -> "Token":
        """Create a new token with a different file path."""
        return Token(
            type=self.type,
            value=self.value,
            line=self.line,
            column=self.column,
            end_line=self.end_line,
            end_column=self.end_column,
            file_path=file_path
        )


# Keyword mapping
KEYWORDS: dict[str, TokenType] = {
    "component": TokenType.COMPONENT,
    "use": TokenType.USE,
    "connect": TokenType.CONNECT,
}
