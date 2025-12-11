"""
Base SHDL Lexer

Tokenizes Base SHDL source code. This is simpler than the Expanded SHDL lexer
since Base SHDL doesn't have generators, imports, or variable references.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


class TokenType(Enum):
    """Token types for Base SHDL."""
    # Keywords
    COMPONENT = auto()
    CONNECT = auto()
    
    # Primitive types
    AND = auto()
    OR = auto()
    NOT = auto()
    XOR = auto()
    VCC = auto()
    GND = auto()
    
    # Operators and delimiters
    ARROW = auto()       # ->
    COLON = auto()       # :
    SEMICOLON = auto()   # ;
    COMMA = auto()       # ,
    DOT = auto()         # .
    LBRACE = auto()      # {
    RBRACE = auto()      # }
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    LPAREN = auto()      # (
    RPAREN = auto()      # )
    
    # Literals
    IDENTIFIER = auto()
    NUMBER = auto()
    
    # Special
    EOF = auto()
    NEWLINE = auto()


# Keywords mapping
KEYWORDS = {
    "component": TokenType.COMPONENT,
    "connect": TokenType.CONNECT,
    "AND": TokenType.AND,
    "OR": TokenType.OR,
    "NOT": TokenType.NOT,
    "XOR": TokenType.XOR,
    "__VCC__": TokenType.VCC,
    "__GND__": TokenType.GND,
}


@dataclass
class Token:
    """A lexical token."""
    type: TokenType
    value: str | int
    line: int
    column: int
    
    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"


class LexerError(Exception):
    """Error during lexical analysis."""
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Line {line}, column {column}: {message}")


class BaseSHDLLexer:
    """
    Lexer for Base SHDL.
    
    Base SHDL has a simpler grammar than Expanded SHDL:
    - No generators (>i[8]{...})
    - No imports (use ...)
    - No constants (NAME = value)
    - No template strings ({i+1})
    - Only primitive gates (AND, OR, NOT, XOR, __VCC__, __GND__)
    """
    
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []
        
    def current_char(self) -> str | None:
        """Get the current character or None if at end."""
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]
    
    def peek_char(self, offset: int = 1) -> str | None:
        """Look ahead without consuming."""
        pos = self.pos + offset
        if pos >= len(self.source):
            return None
        return self.source[pos]
    
    def advance(self) -> str | None:
        """Consume and return the current character."""
        char = self.current_char()
        if char is not None:
            self.pos += 1
            if char == '\n':
                self.line += 1
                self.column = 1
            else:
                self.column += 1
        return char
    
    def skip_whitespace_and_comments(self) -> None:
        """Skip whitespace and comments (# and "...")."""
        while True:
            char = self.current_char()
            
            if char is None:
                break
            
            # Whitespace
            if char in ' \t\r\n':
                self.advance()
                continue
            
            # Line comment
            if char == '#':
                while self.current_char() is not None and self.current_char() != '\n':
                    self.advance()
                continue
            
            # String comment (used as documentation)
            if char == '"':
                self.advance()  # Opening "
                while self.current_char() is not None and self.current_char() != '"':
                    self.advance()
                if self.current_char() == '"':
                    self.advance()  # Closing "
                continue
            
            break
    
    def read_identifier(self) -> Token:
        """Read an identifier or keyword."""
        start_line = self.line
        start_col = self.column
        chars = []
        
        while True:
            char = self.current_char()
            if char is None:
                break
            if char.isalnum() or char == '_':
                chars.append(char)
                self.advance()
            else:
                break
        
        value = ''.join(chars)
        
        # Check for keywords
        if value in KEYWORDS:
            return Token(KEYWORDS[value], value, start_line, start_col)
        
        return Token(TokenType.IDENTIFIER, value, start_line, start_col)
    
    def read_number(self) -> Token:
        """Read a numeric literal (decimal, hex, or binary)."""
        start_line = self.line
        start_col = self.column
        chars = []
        
        # Check for hex or binary prefix
        if self.current_char() == '0':
            chars.append(self.advance())
            if self.current_char() in ('x', 'X'):
                chars.append(self.advance())
                while self.current_char() and self.current_char() in '0123456789abcdefABCDEF':
                    chars.append(self.advance())
                value = int(''.join(chars), 16)
                return Token(TokenType.NUMBER, value, start_line, start_col)
            elif self.current_char() in ('b', 'B'):
                chars.append(self.advance())
                while self.current_char() and self.current_char() in '01':
                    chars.append(self.advance())
                value = int(''.join(chars[2:]), 2)  # Skip "0b"
                return Token(TokenType.NUMBER, value, start_line, start_col)
        
        # Decimal
        while self.current_char() and self.current_char().isdigit():
            chars.append(self.advance())
        
        value = int(''.join(chars))
        return Token(TokenType.NUMBER, value, start_line, start_col)
    
    def tokenize(self) -> list[Token]:
        """Tokenize the entire source and return a list of tokens."""
        self.tokens = []
        
        while True:
            self.skip_whitespace_and_comments()
            
            if self.current_char() is None:
                break
            
            start_line = self.line
            start_col = self.column
            char = self.current_char()
            
            # Identifier or keyword
            if char.isalpha() or char == '_':
                self.tokens.append(self.read_identifier())
                continue
            
            # Number
            if char.isdigit():
                self.tokens.append(self.read_number())
                continue
            
            # Two-character operators
            if char == '-' and self.peek_char() == '>':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.ARROW, "->", start_line, start_col))
                continue
            
            # Single-character operators
            single_chars = {
                ':': TokenType.COLON,
                ';': TokenType.SEMICOLON,
                ',': TokenType.COMMA,
                '.': TokenType.DOT,
                '{': TokenType.LBRACE,
                '}': TokenType.RBRACE,
                '[': TokenType.LBRACKET,
                ']': TokenType.RBRACKET,
                '(': TokenType.LPAREN,
                ')': TokenType.RPAREN,
            }
            
            if char in single_chars:
                self.advance()
                self.tokens.append(Token(single_chars[char], char, start_line, start_col))
                continue
            
            # Unknown character
            raise LexerError(f"Unexpected character: {char!r}", start_line, start_col)
        
        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        
        return self.tokens
    
    def __iter__(self) -> Iterator[Token]:
        """Iterate over tokens (tokenize if not done)."""
        if not self.tokens:
            self.tokenize()
        return iter(self.tokens)
