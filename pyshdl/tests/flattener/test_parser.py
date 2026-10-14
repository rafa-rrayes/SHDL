import pytest

from flattener import ast_nodes as A
from flattener.diagnostics import ErrorCode, SHDLError
from flattener.parser import parse_source
from flattener.source import SourceFile


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
    c = the_component("top component Mux<N = 8, SEL>(A[N], Sel[SEL], En) -> (Y[N]) { connect { } }")
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
        "component C(A[16]) -> (Y[16]) { connect {\n    >i[1:4, 8, 12:]{ A[{i}] -> Y[{i}]; }\n} }"
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


# --- PAR-1 holes: productions never positively parsed before -----------------


def test_empty_output_list():
    # PAR-1: `-> ()` — a component with no outputs (a pure sink) parses.
    c = the_component("component Sink(A) -> () { connect { } }")
    assert c.outputs == ()
    assert [p.name for p in c.inputs] == ["A"]


def test_declaration_context_when():
    # PAR-1 + GEN-12 (parse only): a `when` block directly in a component body
    # (declaration context) parses as a Conditional holding declarations.
    c = the_component(
        "component C<W>(A) -> (Y) {\n    when {W == 1} { g: AND; }\n    connect { A -> Y; }\n}"
    )
    (cond,) = c.decls
    assert isinstance(cond, A.Conditional)
    assert isinstance(cond.then_body[0], A.InstanceDecl)


def test_parenthesized_bool_expr():
    # PAR-1: `( BoolExpr )` — parentheses group a boolean sub-expression.
    c = the_component(
        "component C<N>(A) -> (Y) { connect {\n"
        "    >i[N]{ when {(i == 1 && N > 1) || i == 2} { A -> Y; } }\n"
        "} }"
    )
    cond = c.connect_blocks[0][1][0].body[0].cond
    assert isinstance(cond, A.BoolOr)
    assert isinstance(cond.items[0], A.BoolAnd)  # the parenthesized group
    assert isinstance(cond.items[1], A.Cmp)


def test_all_relops_and_oror_parse():
    # PAR-1: `!= < <= >=` and `||` are positively parsed (only `== > &&` were
    # exercised before).
    c = the_component(
        "component C<N>(A) -> (Y) { connect {\n"
        "    >i[N]{ when {i != 1 || i < 2 || i <= 3 || i >= 4} { A -> Y; } }\n"
        "} }"
    )
    cond = c.connect_blocks[0][1][0].body[0].cond
    assert isinstance(cond, A.BoolOr)
    assert [it.op for it in cond.items] == ["!=", "<", "<=", ">="]


# --- PAR-4: nested replication 2{2{s}} ---------------------------------------


def test_nested_replication():
    # PAR-4: a Replication may contain a Replication.
    c = the_component("component C(s) -> (O[4]) { connect { {2{2{s}}} -> O; } }")
    (conn,) = c.connect_blocks[0][1]
    (outer,) = conn.src.items
    assert isinstance(outer, A.Replication) and outer.count.value == 2
    (inner,) = outer.items
    assert isinstance(inner, A.Replication) and inner.count.value == 2
    assert isinstance(inner.items[0], A.Primary) and inner.items[0].base.plain == "s"


# --- PAR-7: context legality (corrected) -------------------------------------


def test_par7_constant_token_as_connection_source_is_e0604():
    # PAR-7: a non-IDENT/non-LBRACE token where a connection is expected fires
    # the connection-context E0604 site.
    code = parse_err("component M(A) -> (Y) { connect { 5 -> Y; } }")
    assert code is ErrorCode.E0604


def test_par7_declaration_inside_connect_is_e0201():
    # PAR-7 (corrected): `g: AND;` inside connect parses as a connection named
    # `g`, then dies at the `->` expect with E0201 — not E0604.
    with pytest.raises(SHDLError) as ei:
        parse("component M(A) -> (Y) { connect { g: AND; A -> Y; } }")
    assert ei.value.diagnostic.code is ErrorCode.E0201


def test_par7_connection_inside_declaration_context_is_e0201():
    # PAR-7 (the untested direction): a connection in declaration context
    # parses as a declaration name, then dies expecting `:`/`[`/`=` — E0201.
    with pytest.raises(SHDLError) as ei:
        parse("component M(A) -> (Y) { A -> Y; connect { } }")
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0201
    assert d.pos.line == 1


# --- PAR-9: adversarial `<` / `>` mixes --------------------------------------


def test_par9_angle_brackets_in_three_roles():
    # PAR-9: `<>` as a param list, a generator intro `>`, and relational
    # `< >` inside a `when` — all in one component, disambiguated by context.
    c = the_component(
        "component C<N>(A[N]) -> (Y[N]) {\n"
        "    g: C<N>;\n"  # arg list <N>
        "    connect {\n"
        "        >i[N]{ when {i < N && i > 0} { A[{i}] -> Y[{i}]; } }\n"  # gen + relops
        "    }\n"
        "}"
    )
    assert c.decls[0].args[0].expr.ident == "N"
    cond = c.connect_blocks[0][1][0].body[0].cond
    assert isinstance(cond, A.BoolAnd)
    assert [it.op for it in cond.items] == ["<", ">"]


# --- PAR-10: premature EOF inside each body kind -----------------------------


def test_par10_eof_in_component_body():
    # PAR-10: an unclosed connection inside the component body → E0604 "…end
    # of file" via the gen-item fallthrough (never a crash or a hang).
    with pytest.raises(SHDLError) as ei:
        parse("component C(A) -> (Y) { connect { A -> Y;")
    assert ei.value.diagnostic.code is ErrorCode.E0604


def test_par10_eof_in_connect_body():
    # PAR-10
    with pytest.raises(SHDLError) as ei:
        parse("component C(A) -> (Y) { connect {")
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0604
    assert "end of file" in d.message


def test_par10_eof_in_generator_body():
    # PAR-10
    with pytest.raises(SHDLError) as ei:
        parse("component C(A[2]) -> (Y[2]) { connect { >i[2]{")
    assert ei.value.diagnostic.code is ErrorCode.E0604


def test_par10_eof_in_init_body():
    # PAR-10: the init body expects a primary; EOF → E0201.
    with pytest.raises(SHDLError) as ei:
        parse("component C(A) -> (Y) { n: NOT; init {")
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0201
    assert "end of file" in d.message


# --- PAR-11: body-order laxity (AMB-16) --------------------------------------


def test_par11_connect_before_declaration():
    # PAR-11: declarations may follow the connect block (any order accepted).
    c = the_component("component C(A) -> (Y) { connect { A -> g.A; g.O -> Y; } g: NOT; }")
    assert isinstance(c.decls[0], A.InstanceDecl)
    assert len(c.connect_blocks) == 1


def test_par11_init_before_declaration_and_connect():
    # PAR-11: init may precede the declaration it seeds and the connect block.
    c = the_component(
        "component C(A) -> (Y) {\n"
        "    init { g.O = 1; }\n"
        "    g: NOT;\n"
        "    connect { A -> g.A; g.O -> Y; }\n"
        "}"
    )
    assert len(c.init_blocks) == 1
    assert len(c.connect_blocks) == 1
    assert isinstance(c.decls[0], A.InstanceDecl)


# --- PAR-12: reserved keyword in identifier position -------------------------


@pytest.mark.parametrize(
    "src",
    [
        "component when(A) -> (Y) { connect { A -> Y; } }",  # component name
        "component M(A) -> (Y) { connect: AND; connect { A -> Y; } }",  # instance
        "component M(connect) -> (Y) { connect { A -> Y; } }",  # port name
        "component M<when>(A) -> (Y) { connect { A -> Y; } }",  # param name
    ],
)
def test_par12_reserved_keyword_as_identifier(src):
    # PAR-12: a keyword where an identifier is required → E0201 with position.
    with pytest.raises(SHDLError) as ei:
        parse(src)
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0201
    assert d.pos.line >= 1 and d.pos.col >= 1


# --- PAR-8: deeply nested input → structured diagnostic, never RecursionError -


def test_par8_deep_brace_nesting_at_and_beyond_cap():
    # PAR-8 (live crash): 400-deep `{…}` substitution used to raise a raw
    # RecursionError; now it is a documented depth-cap diagnostic (E0201).
    from flattener.parser import MAX_NESTING_DEPTH

    for depth in (MAX_NESTING_DEPTH + 1, 400, 1000):
        expr = "{" * depth + "1" + "}" * depth
        src = f"top component M(A[2]) -> (Y) {{ connect {{ A[{expr}] -> Y; }} }}"
        with pytest.raises(SHDLError) as ei:
            parse(src)
        assert ei.value.diagnostic.code is ErrorCode.E0201, depth
        assert "limit" in ei.value.diagnostic.message


def test_par8_deep_paren_nesting_in_when_condition():
    # PAR-8: deep `(…)` in a boolean condition is likewise capped, not crashed.
    depth = 1000
    cond = "(" * depth + "1 == 1" + ")" * depth
    src = (
        "top component M<N>(A) -> (Y) { connect {\n"
        f"    >i[1]{{ when {{{cond}}} {{ A -> Y; }} }}\n"
        "} }"
    )
    with pytest.raises(SHDLError) as ei:
        parse(src)
    assert ei.value.diagnostic.code is ErrorCode.E0201


def test_par8_nesting_just_below_cap_is_accepted():
    # PAR-8: the cap is a ceiling, not a regression on ordinary depth — a
    # group nested to MAX-1 parses cleanly.
    from flattener.parser import MAX_NESTING_DEPTH

    depth = MAX_NESTING_DEPTH - 1
    expr = "{" * depth + "1" + "}" * depth
    c = the_component(f"component M(A[2]) -> (Y) {{ connect {{ A[{expr}] -> Y; }} }}")
    assert len(c.connect_blocks) == 1


# --- AMB-29: trailing `meta { … }` block is accepted and ignored -------------


def test_amb29_trailing_meta_block_is_ignored():
    # AMB-29: emitted Base SHDL ends with a `meta { … }` block; the parser
    # accepts and discards it so re-flattening is possible (DET-4).
    mod = parse(
        "component C(A) -> (Y) { connect { A -> Y; } }\n"
        'meta {\n  "doc": {},\n  "stats": { "n": 3 }\n}\n'
    )
    assert len(mod.components) == 1
    assert mod.components[0].name == "C"


def test_amb29_meta_must_be_balanced():
    # AMB-29: an unterminated meta block is a syntax error, not a hang.
    with pytest.raises(SHDLError) as ei:
        parse("component C(A) -> (Y) { connect { A -> Y; } }\nmeta {")
    assert ei.value.diagnostic.code is ErrorCode.E0201


def test_amb29_meta_ends_the_module():
    # AMB-29: the meta block terminates the module — a component after it is
    # rejected (it is the trailing block, matching what the emitter produces).
    with pytest.raises(SHDLError) as ei:
        parse("meta { }\ncomponent C(A) -> (Y) { connect { A -> Y; } }")
    d = ei.value.diagnostic
    assert d.code is ErrorCode.E0201
    assert "after the 'meta' block" in d.message
