import pytest

from shdlc import ast_nodes as A
from shdlc.diagnostics import ErrorCode, SHDLError
from shdlc.parser import parse_source
from shdlc.source import SourceFile


def parse(text: str, name: str = "m") -> A.Module:
    return parse_source(SourceFile(f"{name}.shdl", f"/{name}.shdl", text), name)


def parse_err(text: str) -> ErrorCode:
    with pytest.raises(SHDLError) as ei:
        parse(text)
    return ei.value.diagnostic.code


def the_component(text: str) -> A.Component:
    mod = parse(text)
    assert len(mod.components) == 1
    return mod.components[0]


def test_component_header():
    c = the_component(
        "top component Mux<N = 8, SEL>(A[N], Sel[SEL], En) -> (Y[N]) { connect { } }"
    )
    assert c.is_top
    assert c.name == "Mux"
    assert [(p.name, p.default) for p in c.params] == [("N", 8), ("SEL", None)]
    assert [p.name for p in c.inputs] == ["A", "Sel", "En"]
    assert c.inputs[2].width is None  # single-bit
    assert isinstance(c.inputs[0].width, A.Name)
    assert [p.name for p in c.outputs] == ["Y"]


def test_instance_and_constant_decls():
    c = the_component(
        "component C(A) -> (Y) {\n"
        "    g1: AND;\n"
        "    r: Reg<8, INIT = 3>;\n"
        "    FIVE[3] = 5;\n"
        "    ZERO = 0;\n"
        "    connect { A -> Y; }\n"
        "}"
    )
    g1, r, five, zero = c.decls
    assert isinstance(g1, A.InstanceDecl) and g1.type_name == "AND" and g1.args == ()
    assert isinstance(r, A.InstanceDecl)
    assert [(a.name, type(a.expr)) for a in r.args] == [(None, A.Num), ("INIT", A.Num)]
    assert isinstance(five, A.ConstantDecl) and five.value == 5
    assert isinstance(five.width, A.Num) and five.width.value == 3
    assert isinstance(zero, A.ConstantDecl) and zero.width is None


def test_generator_with_multi_range():
    c = the_component(
        "component C(A[16]) -> (Y[16]) { connect {\n"
        "    >i[1:4, 8, 12:]{ A[{i}] -> Y[{i}]; }\n"
        "} }"
    )
    (gen,) = c.connect_blocks[0][1]
    assert isinstance(gen, A.Generator) and gen.var == "i"
    assert [type(r) for r in gen.ranges] == [A.RangeAB, A.RangeN, A.RangeOpen]


def test_when_else():
    c = the_component(
        "component C<N>(A[N], Cin) -> (Y[N]) { connect {\n"
        "    >i[N]{\n"
        "        when {i == 1 && N > 1} { Cin -> Y[{i}]; }\n"
        "        else { A[{i-1}] -> Y[{i}]; }\n"
        "    }\n"
        "} }"
    )
    (gen,) = c.connect_blocks[0][1]
    (cond,) = gen.body
    assert isinstance(cond, A.Conditional)
    assert isinstance(cond.cond, A.BoolAnd)
    assert len(cond.then_body) == 1 and len(cond.else_body) == 1


def test_concat_replication_disambiguation():
    # `8{sign}` replicates (a number can only be a count); `fa{i}` is a
    # templated name; `N{x.O, y}` replicates with an identifier count (the
    # group's contents can only be signals). The parser's documented tie-break
    # for `N{x}` (identifier count over a single identifier, indistinguishable
    # from a template with one token of lookahead) is the name template, the
    # overwhelmingly common shape inside generators.
    c = the_component(
        "component C<N = 2>(sign, x, y) -> (Out[12]) { connect {\n"
        "    >i[1]{ {8{sign}, fa{i}.O, N{x.O, y}, b{i}} -> Out; }\n"
        "} }"
    )
    (gen,) = c.connect_blocks[0][1]
    (conn,) = gen.body
    concat = conn.src
    assert isinstance(concat, A.Concat)
    repl8, fa, repln, tmpl = concat.items
    assert isinstance(repl8, A.Replication) and repl8.count.value == 8
    assert isinstance(fa, A.Primary) and fa.port.plain == "O"
    assert not fa.base.is_plain  # fa{i}
    assert isinstance(repln, A.Replication) and repln.count.ident == "N"
    assert len(repln.items) == 2
    assert isinstance(tmpl, A.Primary) and not tmpl.base.is_plain  # b{i}


def test_bare_braced_primary_is_one_element_concat():
    c = the_component("component C(A) -> (Y) { connect { {A} -> Y; } }")
    (conn,) = c.connect_blocks[0][1]
    assert isinstance(conn.src, A.Concat) and len(conn.src.items) == 1


def test_slice_forms():
    c = the_component(
        "component C(A[8]) -> (X[4], Y[4], Z[6]) { connect {\n"
        "    A[2:5] -> X;  A[:4] -> Y;  A[3:] -> Z;\n"
        "} }"
    )
    conns = c.connect_blocks[0][1]
    s0, s1, s2 = (conn.src.index for conn in conns)
    assert s0 == A.IndexSlice(lo=s0.lo, hi=s0.hi) and s0.lo.value == 2 and s0.hi.value == 5
    assert s1.lo is None and s1.hi.value == 4
    assert s2.lo.value == 3 and s2.hi is None


def test_init_block():
    c = the_component(
        "component C(S) -> (Q) {\n"
        "    n1: NOT;\n"
        "    init { n1.O = 1; }\n"
        "    connect { S -> n1.A; n1.O -> Q; }\n"
        "}"
    )
    ((_pos, assigns),) = c.init_blocks
    (a,) = assigns
    assert a.target.base.plain == "n1" and a.target.port.plain == "O"
    assert a.value == 1


def test_syntax_error_has_code_and_position():
    with pytest.raises(SHDLError) as ei:
        parse("component C(A) -> (Y) { connect { A -> ; } }")
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0201
    assert d.pos.line == 1


def test_declaration_inside_connect_rejected():
    assert parse_err("component C(A) -> (Y) { connect { g: AND; A -> Y; } }") in (
        ErrorCode.E0604,
        ErrorCode.E0201,
    )


def test_constant_name_must_be_plain():
    assert parse_err("component C<N>(A) -> (Y) { K{N} = 1; connect { A -> Y; } }") is (
        ErrorCode.E0201
    )
