"""
SHDL Lexer

Tokenizes SHDL source code into a stream of tokens.
"""

from dataclasses import dataclass, field
from typing import Iterator, Optional

from .tokens import Token, TokenType, KEYWORDS
from ..errors import LexerError, ErrorCode, ErrorCode


@dataclass
class Lexer:
    """
    Tokenizes SHDL source code.
    
    Tracks precise source positions for error reporting.
    """
    
    source: str
    file_path: str = "<string>"
    
    def __post_init__(self) -> None:
        self._pos: int = 0
        self._line: int = 1
        self._column: int = 1
        self._tokens: list[Token] = []
    
    @property
    def _current(self) -> str:
        """Get the current character, or empty string if at end."""
        if self._pos >= len(self.source):
            return ""
        return self.source[self._pos]
    
    @property
    def _peek(self) -> str:
        """Peek at the next character."""
        if self._pos + 1 >= len(self.source):
            return ""
        return self.source[self._pos + 1]
    
    def _advance(self) -> str:
        """Advance to the next character and return the current one."""
        char = self._current
        self._pos += 1
        if char == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return char
    
    def _make_token(
        self,
        token_type: TokenType,
        value: any,
        start_line: int,
        start_col: int,
        end_line: int = None,
        end_col: int = None
    ) -> Token:
        """Create a token with full position information."""
        return Token(
            type=token_type,
            value=value,
            line=start_line,
            column=start_col,
            end_line=end_line if end_line is not None else self._line,
            end_column=end_col if end_col is not None else self._column - 1,
            file_path=self.file_path
        )
    
    def _add_token(self, token_type: TokenType, value: any = None) -> None:
        """Add a token to the list (for backward compatibility)."""
        self._tokens.append(Token(
            type=token_type,
            value=value,
            line=self._line,
            column=self._column,
            file_path=self.file_path
        ))
    
    def _skip_whitespace(self) -> None:
        """Skip whitespace characters (except newlines which may be significant)."""
        while self._current and self._current in " \t\r\n":
            self._advance()
    
    def _skip_line_comment(self) -> None:
        """Skip a # comment to end of line."""
        self._advance()  # Skip the #
        while self._current and self._current != "\n":
            self._advance()
    
    def _skip_string_comment(self) -> None:
        """Skip a string comment (single or triple quoted)."""
        start_line, start_col = self._line, self._column
        
        # Check for triple quotes
        if self._peek == '"':
            self._advance()  # first "
            if self._peek == '"':
                self._advance()  # second "
                self._advance()  # third "
                # Triple quoted - find closing """
                while self._current:
                    if self._current == '"' and self._peek == '"':
                        self._advance()  # first closing "
                        if self._peek == '"':
                            self._advance()  # second closing "
                            self._advance()  # third closing "
                            return
                    else:
                        self._advance()
                raise LexerError(
                    "Unterminated triple-quoted comment",
                    line=start_line,
                    column=start_col,
                    file_path=self.file_path,
                    code=ErrorCode.E0104
                )
            else:
                # Was just "" - empty string, we already consumed both quotes
                self._advance()  # consume second "
                return
        
        # Single quoted string comment
        self._advance()  # opening "
        while self._current and self._current != '"' and self._current != "\n":
            self._advance()
        if self._current == '"':
            self._advance()  # closing "
        # If we hit newline, that's fine - single line comment ends
    
    def _read_identifier(self) -> str:
        """Read an identifier or keyword."""
        start = self._pos
        while self._current and (self._current.isalnum() or self._current == "_"):
            self._advance()
        return self.source[start:self._pos]
    
    def _read_number(self) -> int:
        """Read a number literal (decimal, hex, or binary)."""
        start_line, start_col = self._line, self._column
        
        if self._current == "0" and self._peek in "xXbB":
            # Hex or binary
            self._advance()  # 0
            prefix = self._advance().lower()  # x or b
            
            if prefix == "x":
                # Hexadecimal
                start = self._pos
                while self._current and self._current in "0123456789abcdefABCDEF":
                    self._advance()
                if self._pos == start:
                    raise LexerError(
                        "Invalid hexadecimal number: expected hex digits after '0x'",
                        line=start_line,
                        column=start_col,
                        file_path=self.file_path,
                        code=ErrorCode.E0105
                    )
                return int(self.source[start:self._pos], 16)
            else:
                # Binary
                start = self._pos
                while self._current in "01":
                    self._advance()
                if self._pos == start:
                    raise LexerError(
                        "Invalid binary number: expected binary digits (0 or 1) after '0b'",
                        line=start_line,
                        column=start_col,
                        file_path=self.file_path,
                        code=ErrorCode.E0106
                    )
                return int(self.source[start:self._pos], 2)
        else:
            # Decimal
            start = self._pos
            while self._current.isdigit():
                self._advance()
            return int(self.source[start:self._pos])
    
    def tokenize(self) -> list[Token]:
        """Tokenize the entire source and return a list of tokens."""
        self._pos = 0
        self._line = 1
        self._column = 1
        self._tokens = []
        
        while self._current:
            self._skip_whitespace()
            
            if not self._current:
                break
            
            start_line, start_col = self._line, self._column
            char = self._current
            
            # Comments
            if char == "#":
                self._skip_line_comment()
                continue
            
            if char == '"':
                self._skip_string_comment()
                continue
            
            # Two-character operators
            if char == "-" and self._peek == ">":
                self._advance()
                self._advance()
                self._tokens.append(self._make_token(
                    TokenType.ARROW, "->", start_line, start_col,
                    self._line, self._column - 1
                ))
                continue
            
            # Minus sign (standalone, not part of arrow)
            if char == "-":
                self._advance()
                self._tokens.append(self._make_token(
                    TokenType.MINUS, "-", start_line, start_col
                ))
                continue
            
            if char == ":" and self._peek == ":":
                self._advance()
                self._advance()
                self._tokens.append(self._make_token(
                    TokenType.DOUBLE_COLON, "::", start_line, start_col,
                    self._line, self._column - 1
                ))
                continue
            
            # Single-character operators
            single_char_tokens = {
                ":": TokenType.COLON,
                ";": TokenType.SEMICOLON,
                ",": TokenType.COMMA,
                ".": TokenType.DOT,
                "=": TokenType.EQUALS,
                "{": TokenType.LBRACE,
                "}": TokenType.RBRACE,
                "[": TokenType.LBRACKET,
                "]": TokenType.RBRACKET,
                "(": TokenType.LPAREN,
                ")": TokenType.RPAREN,
                ">": TokenType.GREATER,
                "+": TokenType.PLUS,
                "*": TokenType.STAR,
                "/": TokenType.SLASH,
            }
            
            if char in single_char_tokens:
                self._advance()
                self._tokens.append(self._make_token(
                    single_char_tokens[char], char, start_line, start_col
                ))
                continue
            
            # Identifiers and keywords
            if char.isalpha() or char == "_":
                ident = self._read_identifier()
                token_type = KEYWORDS.get(ident, TokenType.IDENTIFIER)
                self._tokens.append(self._make_token(
                    token_type, ident, start_line, start_col,
                    self._line, self._column - 1
                ))
                continue
            
            # Numbers
            if char.isdigit():
                number = self._read_number()
                self._tokens.append(self._make_token(
                    TokenType.NUMBER, number, start_line, start_col,
                    self._line, self._column - 1
                ))
                continue
            
            raise LexerError(
                f"Unexpected character: {char!r}",
                line=start_line,
                column=start_col,
                file_path=self.file_path,
                code=ErrorCode.E0101
            )
        
        self._tokens.append(self._make_token(
            TokenType.EOF, None, self._line, self._column
        ))
        return self._tokens
    
    def __iter__(self) -> Iterator[Token]:
        """Iterate over tokens."""
        return iter(self.tokenize())
