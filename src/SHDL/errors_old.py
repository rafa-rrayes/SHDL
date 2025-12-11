"""
SHDL Exceptions

All exception types used by the SHDL library.
"""


class SHDLError(Exception):
    """Base exception for all SHDL errors."""
    pass


class LexerError(SHDLError):
    """Raised when the lexer encounters an invalid token."""
    
    def __init__(self, message: str, line: int, column: int):
        self.line = line
        self.column = column
        super().__init__(f"Lexer error at {line}:{column}: {message}")


class ParseError(SHDLError):
    """Raised when the parser encounters invalid syntax."""
    
    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.line = line
        self.column = column
        super().__init__(f"Parse error at {line}:{column}: {message}")


class FlattenerError(SHDLError):
    """Raised when flattening encounters an error."""
    pass


class ValidationError(SHDLError):
    """Raised when validation fails."""
    pass
