"""Lexer for SHDL (shdl.md §2).

Produces a flat token stream; whitespace is insignificant except as a
separator. All three comment forms (hash, double-quoted, triple-quoted) are
stripped here. If the first thing in the file (before any token) is a
triple-quoted comment, its text is kept aside as the module's doc comment so
the flattener can surface it as ``meta.doc.description``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .diagnostics import ErrorCode, err
from .source import Pos, SourceFile

KEYWORDS = frozenset({"component", "use", "connect", "init", "when", "else", "top"})


class T(Enum):
    IDENT = "identifier"
    KEYWORD = "keyword"
    NUMBER = "number"
    ARROW = "'->'"
    SCOPE = "'::'"
    DOT = "'.'"
    EQ = "'='"
    EQEQ = "'=='"
    NE = "'!='"
    LT = "'<'"
    LE = "'<='"
    GT = "'>'"
    GE = "'>='"
    ANDAND = "'&&'"
    OROR = "'||'"
    COLON = "':'"
    SEMI = "';'"
    COMMA = "','"
    LBRACE = "'{'"
    RBRACE = "'}'"
    LBRACKET = "'['"
    RBRACKET = "']'"
    LPAREN = "'('"
    RPAREN = "')'"
    PLUS = "'+'"
    MINUS = "'-'"
    STAR = "'*'"
    SLASH = "'/'"
    EOF = "end of file"


@dataclass(frozen=True, slots=True)
class Token:
    kind: T
    text: str
    value: int | None  # numeric value for NUMBER tokens
    pos: Pos

    def __str__(self) -> str:
        if self.kind in (T.IDENT, T.KEYWORD, T.NUMBER):
            return f"'{self.text}'"
        return self.kind.value


_TWO_CHAR = {
    "->": T.ARROW,
    "::": T.SCOPE,
    "==": T.EQEQ,
    "!=": T.NE,
    "<=": T.LE,
    ">=": T.GE,
    "&&": T.ANDAND,
    "||": T.OROR,
}

_ONE_CHAR = {
    ".": T.DOT,
    "=": T.EQ,
    "<": T.LT,
    ">": T.GT,
    ":": T.COLON,
    ";": T.SEMI,
    ",": T.COMMA,
    "{": T.LBRACE,
    "}": T.RBRACE,
    "[": T.LBRACKET,
    "]": T.RBRACKET,
    "(": T.LPAREN,
    ")": T.RPAREN,
    "+": T.PLUS,
    "-": T.MINUS,
    "*": T.STAR,
    "/": T.SLASH,
}


def _is_ascii_digit(c: str) -> bool:
    return "0" <= c <= "9"


def _is_ident_start(c: str) -> bool:
    # ASCII-only by policy (AMB-14): the spec leaves LETTER/DIGIT undefined,
    # and Python's Unicode .isalpha()/.isalnum()/.isdigit() would let `é`
    # lex as an identifier and `²` reach int() with a raw ValueError. Pin
    # [A-Za-z_]; everything else is an unexpected character (E0101).
    return ("a" <= c <= "z") or ("A" <= c <= "Z") or c == "_"


def _is_ident_char(c: str) -> bool:
    return _is_ident_start(c) or _is_ascii_digit(c)


class LexResult:
    def __init__(self, tokens: list[Token], doc_comment: str | None):
        self.tokens = tokens
        self.doc_comment = doc_comment


def lex(src: SourceFile) -> LexResult:
    text = src.text
    n = len(text)
    i = 0
    line = 1
    col = 1
    tokens: list[Token] = []
    doc_comment: str | None = None
    seen_token = False

    def pos() -> Pos:
        return Pos(src.name, line, col)

    def advance(count: int) -> None:
        nonlocal i, line, col
        for _ in range(count):
            if text[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        c = text[i]
        if c in " \t\r\n":
            advance(1)
            continue
        if c == "#":
            while i < n and text[i] != "\n":
                advance(1)
            continue
        if c == '"':
            start = pos()
            if text.startswith('"""', i):
                advance(3)
                body_start = i
                end = text.find('"""', i)
                if end == -1:
                    raise err(ErrorCode.E0101, "unterminated triple-quoted comment", start)
                body = text[body_start:end]
                advance(end - i + 3)
                if not seen_token and doc_comment is None:
                    doc_comment = body.strip()
            else:
                advance(1)
                while i < n and text[i] not in '"\n':
                    advance(1)
                if i >= n or text[i] != '"':
                    raise err(ErrorCode.E0101, "unterminated string comment", start)
                advance(1)
            continue

        seen_token = True
        start = pos()

        if _is_ascii_digit(c):
            j = i
            value: int
            if text.startswith(("0x", "0X"), i):
                j = i + 2
                while j < n and (_is_ascii_digit(text[j]) or text[j] in "abcdefABCDEF"):
                    j += 1
                digits = text[i + 2 : j]
                if not digits:
                    raise err(ErrorCode.E0101, "hexadecimal literal has no digits", start)
                value = int(digits, 16)
            elif text.startswith(("0b", "0B"), i):
                j = i + 2
                while j < n and text[j] in "01":
                    j += 1
                digits = text[i + 2 : j]
                if not digits:
                    raise err(ErrorCode.E0101, "binary literal has no digits", start)
                value = int(digits, 2)
            else:
                while j < n and _is_ascii_digit(text[j]):
                    j += 1
                value = int(text[i:j])
            if j < n and _is_ident_char(text[j]):
                raise err(
                    ErrorCode.E0101,
                    f"invalid character {text[j]!r} in numeric literal",
                    start,
                )
            word = text[i:j]
            advance(j - i)
            tokens.append(Token(T.NUMBER, word, value, start))
            continue

        if _is_ident_start(c):
            j = i
            while j < n and _is_ident_char(text[j]):
                j += 1
            word = text[i:j]
            advance(j - i)
            kind = T.KEYWORD if word in KEYWORDS else T.IDENT
            tokens.append(Token(kind, word, None, start))
            continue

        two = text[i : i + 2]
        if two in _TWO_CHAR:
            advance(2)
            tokens.append(Token(_TWO_CHAR[two], two, None, start))
            continue
        if c in _ONE_CHAR:
            advance(1)
            tokens.append(Token(_ONE_CHAR[c], c, None, start))
            continue

        raise err(ErrorCode.E0101, f"unexpected character {c!r}", start)

    tokens.append(Token(T.EOF, "", None, pos()))
    return LexResult(tokens, doc_comment)
