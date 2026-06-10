import pytest

from shdlc.diagnostics import ErrorCode, SHDLError
from shdlc.lexer import T, lex
from shdlc.source import SourceFile


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
