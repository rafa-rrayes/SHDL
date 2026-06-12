import pytest

from flattener.diagnostics import ErrorCode, SHDLError
from flattener.lexer import T, lex
from flattener.source import SourceFile


def toks(text: str):
    return lex(SourceFile("t.shdl", "/t.shdl", text)).tokens


def kinds(text: str):
    return [t.kind for t in toks(text)][:-1]  # drop EOF


def test_identifiers_and_keywords():
    ts = toks("component Foo top connect use init when else")
    assert [t.kind for t in ts[:-1]] == [T.KEYWORD, T.IDENT] + [T.KEYWORD] * 6
    assert ts[0].text == "component"
    assert ts[1].text == "Foo"


def test_number_literals():
    ts = toks("42 0x2A 0b101010 0")
    assert all(t.kind is T.NUMBER for t in ts[:-1])
    assert [t.value for t in ts[:-1]] == [42, 42, 42, 0]


def test_all_operators():
    text = "-> :: == != <= >= && || < > = : ; , { } [ ] ( ) + - * / ."
    assert kinds(text) == [
        T.ARROW, T.SCOPE, T.EQEQ, T.NE, T.LE, T.GE, T.ANDAND, T.OROR,
        T.LT, T.GT, T.EQ, T.COLON, T.SEMI, T.COMMA, T.LBRACE, T.RBRACE,
        T.LBRACKET, T.RBRACKET, T.LPAREN, T.RPAREN, T.PLUS, T.MINUS,
        T.STAR, T.SLASH, T.DOT,
    ]


def test_all_three_comment_forms_stripped():
    text = 'a # line comment\nb " quoted comment " c """ block\nspanning """ d'
    assert kinds(text) == [T.IDENT] * 4


def test_leading_doc_comment_captured():
    res = lex(SourceFile("t.shdl", "/t.shdl", '"""2-bit adder"""\ncomponent'))
    assert res.doc_comment == "2-bit adder"


def test_non_leading_triple_comment_is_not_doc():
    res = lex(SourceFile("t.shdl", "/t.shdl", 'component """not doc"""'))
    assert res.doc_comment is None


def test_positions_are_one_based():
    ts = toks("a\n  bc")
    assert (ts[0].pos.line, ts[0].pos.col) == (1, 1)
    assert (ts[1].pos.line, ts[1].pos.col) == (2, 3)
    assert ts[0].pos.file == "t.shdl"


def test_bad_character_is_lexical_error():
    with pytest.raises(SHDLError) as ei:
        toks("a @ b")
    assert ei.value.diagnostic.code is ErrorCode.E0101


def test_unterminated_block_comment():
    with pytest.raises(SHDLError) as ei:
        toks('a """ never closed')
    assert ei.value.diagnostic.code is ErrorCode.E0101


# --- LEX-3: uppercase 0X / 0B prefixes (spec §2.3) -------------------------


def test_uppercase_hex_and_binary_prefixes():
    # LEX-3
    ts = toks("0X2A 0XFF 0B101010 0b101010 0xff")
    assert all(t.kind is T.NUMBER for t in ts[:-1])
    assert [t.value for t in ts[:-1]] == [42, 255, 42, 42, 255]


# --- LEX-6: every E0101 raise site in the lexer ----------------------------


def lex_err(text: str) -> SHDLError:
    with pytest.raises(SHDLError) as ei:
        toks(text)
    assert ei.value.diagnostic.code is ErrorCode.E0101
    return ei.value


def test_e0101_unterminated_single_quote_comment():
    # LEX-6 (single-quote string comment never closed)
    e = lex_err('a " never closed by a newline\n')
    assert "unterminated string comment" in e.diagnostic.message
    assert (e.diagnostic.pos.line, e.diagnostic.pos.col) == (1, 3)


def test_e0101_hex_with_no_digits():
    # LEX-6
    e = lex_err("0x ")
    assert "hexadecimal" in e.diagnostic.message


def test_e0101_binary_with_no_digits():
    # LEX-6
    e = lex_err("0b ")
    assert "binary" in e.diagnostic.message


def test_e0101_ident_char_trailing_a_decimal_literal():
    # LEX-6 (`12ab` — a letter immediately after the digits)
    e = lex_err("12ab")
    assert "numeric literal" in e.diagnostic.message
    assert e.diagnostic.pos.col == 1  # reported at the literal start


def test_e0101_ident_char_trailing_a_hex_literal():
    # LEX-6 (`0xFG` — G is not a hex digit, lexes as a trailing ident char)
    e = lex_err("0xFG")
    assert "numeric literal" in e.diagnostic.message


def test_e0101_unterminated_triple_quote_at_eof():
    # LEX-6 (already covered by test_unterminated_block_comment; pin the message)
    e = lex_err('"""never closed')
    assert "unterminated triple-quoted comment" in e.diagnostic.message


def test_e0101_unexpected_character():
    # LEX-6 (the catch-all site)
    e = lex_err("a @ b")
    assert "unexpected character" in e.diagnostic.message
    assert e.diagnostic.pos.col == 3


# --- LEX-7: boundary inputs (behavior pinned for each) ---------------------


def test_empty_file_is_just_eof():
    # LEX-7
    assert kinds("") == []
    assert toks("")[0].kind is T.EOF


def test_comment_only_file_is_just_eof():
    # LEX-7 (each of the three comment forms, alone)
    assert kinds("# only a line comment") == []
    assert kinds('" only a string comment "') == []
    assert kinds('""" only a block comment """') == []


def test_literal_at_eof():
    # LEX-7
    ts = toks("42")
    assert ts[0].kind is T.NUMBER and ts[0].value == 42
    assert ts[1].kind is T.EOF


def test_tabs_are_whitespace_separators():
    # LEX-7
    ts = toks("a\tb\t42")
    assert [t.kind for t in ts[:-1]] == [T.IDENT, T.IDENT, T.NUMBER]


def test_crlf_line_endings_advance_lines_at_lf():
    # LEX-7: \r is whitespace, the line break is counted at \n.
    ts = toks("a\r\nb")
    assert (ts[0].pos.line, ts[0].pos.col) == (1, 1)
    assert (ts[1].pos.line, ts[1].pos.col) == (2, 1)


def test_bom_is_a_lexical_error():
    # LEX-7 + LEX-9/AMB-14: a UTF-8 BOM (U+FEFF) is a non-ASCII character, so
    # under the ASCII-only policy it is E0101 at column 1 (the loader reads
    # UTF-8, not utf-8-sig, so the BOM reaches the lexer).
    e = lex_err("﻿component")
    assert e.diagnostic.pos.col == 1


# --- LEX-8: huge literals lexed as exact ints ------------------------------


def test_huge_decimal_literal_is_exact_int():
    # LEX-8 (10**100, far beyond any fixed-width integer)
    ts = toks("1" + "0" * 100)
    assert ts[0].kind is T.NUMBER
    assert ts[0].value == 10**100


def test_huge_hex_literal_is_exact_int():
    # LEX-8
    ts = toks("0x" + "f" * 40)
    assert ts[0].value == int("f" * 40, 16)


# --- LEX-9 + AMB-14: ASCII-only identifier / digit policy ------------------


def test_superscript_two_is_a_lexical_error_not_a_crash():
    # LEX-9 (regression): the live crash was `int('²')` raising a raw
    # ValueError because '²'.isdigit() is True; ASCII-only lexing turns it
    # into a positioned E0101.
    for text in ("²", "a ²", "x²y"):
        with pytest.raises(SHDLError) as ei:
            toks(text)
        assert ei.value.diagnostic.code is ErrorCode.E0101


def test_unicode_letter_is_a_lexical_error():
    # LEX-9 + AMB-14: `é` no longer lexes as an identifier.
    e = lex_err("é")
    assert e.diagnostic.code is ErrorCode.E0101


def test_unicode_digit_is_a_lexical_error():
    # LEX-9 + AMB-14: `٣` (Arabic-Indic 3) no longer lexes as NUMBER 3.
    e = lex_err("٣")
    assert e.diagnostic.code is ErrorCode.E0101


def test_ascii_underscore_and_alnum_still_lex():
    # LEX-9: the ASCII identifier set is unchanged.
    ts = toks("_x A1 z9_ Foo_Bar")
    assert all(t.kind is T.IDENT for t in ts[:-1])
    assert [t.text for t in ts[:-1]] == ["_x", "A1", "z9_", "Foo_Bar"]


# --- LEX-11: doc-comment capture edge rules --------------------------------


def doc(text: str) -> str | None:
    return lex(SourceFile("t.shdl", "/t.shdl", text)).doc_comment


def test_first_leading_triple_comment_is_doc():
    # LEX-11
    assert doc('"""the doc"""\ncomponent') == "the doc"


def test_leading_hash_comment_does_not_disqualify_doc():
    # LEX-11: a preceding `#` comment is not a token, so the docstring still
    # counts as leading.
    assert doc('# license header\n"""the doc"""\ncomponent') == "the doc"


def test_leading_string_comment_does_not_disqualify_doc():
    # LEX-11: a preceding `"…"` comment is not a token either.
    assert doc('" banner "\n"""the doc"""\ncomponent') == "the doc"


def test_second_leading_docstring_is_ignored():
    # LEX-11: only the first leading triple-quoted comment becomes the doc.
    assert doc('"""first"""\n"""second"""\ncomponent') == "first"


def test_docstring_after_a_token_is_not_doc():
    # LEX-11
    assert doc('component """not doc"""') is None
