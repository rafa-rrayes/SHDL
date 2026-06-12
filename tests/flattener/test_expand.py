from helpers import expect_error, flatten_fixture, flatten_source


def gate_names(out):
    return list(out.flat.netlist.gates)


def test_generator_basic(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(A[3]) -> (Y[3]) {\n"
        "    >i[3]{ b{i}: OR; }\n"
        "    connect { >i[3]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; b{i}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert gate_names(out) == ["b1", "b2", "b3"]


def test_multi_range(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(A[5]) -> (Y[5]) {\n"
        "    >i[1:2, 4, 5:5]{ b{i}: OR; }\n"
        "    b3: OR;\n"
        "    connect { >i[5]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; b{i}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert sorted(gate_names(out)) == ["b1", "b2", "b3", "b4", "b5"]


def test_nested_generators_and_computed_indices():
    out = flatten_fixture("repeater")
    assert gate_names(out) == [
        "buf1_1", "buf1_2", "buf1_3", "buf2_1", "buf2_2", "buf2_3"
    ]
    # Out[(i-1)*M + j] covers all six output bits exactly once.
    assert sorted(out.flat.netlist.outputs) == sorted(f"Out_{k}_" for k in range(1, 7))


def test_open_range_resolved_by_governing_signal(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(A[4]) -> (Y[4]) {\n"
        "    >i[4]{ b{i}: OR; }\n"
        "    connect { >i[2:]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; b{i}.O -> Y[{i}]; }\n"
        "              A[1] -> b1.A; A[1] -> b1.B; b1.O -> Y[1]; }\n"
        "}",
    )
    assert len(out.flat.netlist.gates) == 4


def test_when_else_selects_structure():
    out = flatten_fixture("adderN")  # carry chain written with when/else
    # Equivalent netlist to the hand-written ripple form: 4 FullAdders.
    assert len(out.flat.netlist.gates) == 20


def test_generator_var_shadows_param(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M<i = 9>(A[2]) -> (Y[2]) {\n"
        "    >i[2]{ b{i}: OR; }\n"
        "    connect { >i[2]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; b{i}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert gate_names(out) == ["b1", "b2"]


def test_empty_range_rejected(tmp_path):
    expect_error(
        "E0601",
        tmp_path,
        "top component M(A) -> (Y) { >i[2:1]{ b{i}: OR; } connect { A -> Y; } }",
    )


def test_zero_count_range_rejected(tmp_path):
    expect_error(
        "E0601",
        tmp_path,
        "top component M(A) -> (Y) { >i[0]{ b{i}: OR; } connect { A -> Y; } }",
    )


def test_open_range_ambiguous(tmp_path):
    expect_error(
        "E0602",
        tmp_path,
        "top component M(A[2], C[3]) -> (Y) {\n"
        "    b1: OR; b2: OR; b3: OR;\n"
        "    connect { >i[1:]{ A[{i}] -> b{i}.A; C[{i}] -> b{i}.B; }\n"
        "              b1.O -> Y; }\n"
        "}",
    )


def test_open_range_in_declaration_context(tmp_path):
    expect_error(
        "E0602",
        tmp_path,
        "top component M(A) -> (Y) { >i[2:]{ b{i}: OR; } connect { A -> Y; } }",
    )


def test_unbound_loop_variable(tmp_path):
    expect_error(
        "E0603",
        tmp_path,
        "top component M(A[2]) -> (Y) { connect { A[{j}] -> Y; } }",
    )


def test_division_by_zero_in_range(tmp_path):
    expect_error(
        "E0605",
        tmp_path,
        "top component M(A) -> (Y) { >i[4/0]{ b{i}: OR; } connect { A -> Y; } }",
    )


def test_unknown_signal_reference(tmp_path):
    expect_error(
        "E0307", tmp_path, "top component M(A) -> (Y) { connect { Ghost -> Y; } }"
    )


# A minimal FullAdder used by the carry-chain generator tests (the fixtures
# import one from a sibling module; tmp_path tests define it inline).
_FULL_ADDER = (
    "component FullAdder(A, B, Cin) -> (Sum, Cout) {\n"
    "    x1: XOR; a1: AND; x2: XOR; a2: AND; o1: OR;\n"
    "    connect {\n"
    "        A -> x1.A; B -> x1.B; A -> a1.A; B -> a1.B;\n"
    "        x1.O -> x2.A; Cin -> x2.B; x1.O -> a2.A; Cin -> a2.B;\n"
    "        a1.O -> o1.A; a2.O -> o1.B; x2.O -> Sum; o1.O -> Cout;\n"
    "    }\n"
    "}\n"
)


# --- GEN-1: the [:b] RangeTo form (parser + expansion) ---------------------- #


def test_gen1_range_to_form(tmp_path):
    # GEN-1: `>i[:3]` (RangeTo) iterates 1..3 — exercised end-to-end.
    out = flatten_source(
        tmp_path,
        "top component M(A[3]) -> (Y[3]) {\n"
        "    >i[:3]{ b{i}: OR; }\n"
        "    connect { >i[3]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; "
        "b{i}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert gate_names(out) == ["b1", "b2", "b3"]


# --- GEN-3: `/` inside `{…}` substitution; §7.2 {i+1}/{2*i-1} --------------- #


def test_gen3_division_in_substitution(tmp_path):
    # GEN-3: division inside a `{…}` index substitution, end-to-end. i in
    # {2,4} -> i/2 in {1,2}, naming and wiring b1, b2 exactly once each.
    out = flatten_source(
        tmp_path,
        "top component M(A[4]) -> (Y[2]) {\n"
        "    >i[2, 4]{ b{i/2}: OR; }\n"
        "    connect { >i[2, 4]{ A[{i}] -> b{i/2}.A; A[{i}] -> b{i/2}.B; "
        "b{i/2}.O -> Y[{i/2}]; } }\n"
        "}",
    )
    assert gate_names(out) == ["b1", "b2"]


def test_gen3_i_plus_one_pattern(tmp_path):
    # GEN-3 / §7.2: `{i+1}` in an instance template selects b2,b3 for i in 1..2.
    out = flatten_source(
        tmp_path,
        "top component M(A[2]) -> (Y[2]) {\n"
        "    >i[2]{ b{i+1}: OR; }\n"
        "    connect { >i[2]{ A[{i}] -> b{i+1}.A; A[{i}] -> b{i+1}.B; "
        "b{i+1}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert gate_names(out) == ["b2", "b3"]


def test_gen3_two_i_minus_one_pattern(tmp_path):
    # GEN-3 / §7.2: `{2*i-1}` selects odd indices 1,3 for i in 1..2.
    out = flatten_source(
        tmp_path,
        "top component M(A[2]) -> (Y[2]) {\n"
        "    >i[2]{ b{2*i-1}: OR; }\n"
        "    connect { >i[2]{ A[{i}] -> b{2*i-1}.A; A[{i}] -> b{2*i-1}.B; "
        "b{2*i-1}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert gate_names(out) == ["b1", "b3"]


# --- GEN-5: ≥3-level nesting ------------------------------------------------ #


def test_gen5_three_level_nesting(tmp_path):
    # GEN-5: three nested generators with a multi-var template name.
    out = flatten_source(
        tmp_path,
        "top component M(A) -> (Y) {\n"
        "    >i[2]{ >j[2]{ >k[2]{ c{i}_{j}_{k}: OR; } } }\n"
        "    connect {\n"
        "        >i[2]{ >j[2]{ >k[2]{ A -> c{i}_{j}_{k}.A; "
        "A -> c{i}_{j}_{k}.B; } } }\n"
        "        c1_1_1.O -> Y;\n"
        "    }\n"
        "}",
    )
    assert sorted(gate_names(out)) == [
        f"c{i}_{j}_{k}" for i in (1, 2) for j in (1, 2) for k in (1, 2)
    ]


# --- GEN-7: the dual-when i==1 / i>1 carry-chain form (§7.7.1) -------------- #


def test_gen7_dual_when_i_gt_1_carry_chain(tmp_path):
    # GEN-7: the `when {i > 1}` carry-chain form elaborated to a real ripple
    # adder — 4 FullAdders worth of gates (5 each = 20).
    out = flatten_source(
        tmp_path,
        _FULL_ADDER + "top component AdderG<N = 4>(A[N], B[N], Cin) -> "
        "(Sum[N], Cout) {\n"
        "    >i[N]{ fa{i}: FullAdder; }\n"
        "    connect {\n"
        "        >i[N]{\n"
        "            A[{i}] -> fa{i}.A; B[{i}] -> fa{i}.B;\n"
        "            when {i > 1} { fa{i-1}.Cout -> fa{i}.Cin; }\n"
        "            else         { Cin          -> fa{i}.Cin; }\n"
        "            fa{i}.Sum -> Sum[{i}];\n"
        "        }\n"
        "        fa{N}.Cout -> Cout;\n"
        "    }\n"
        "}",
    )
    assert len(out.flat.netlist.gates) == 20


# --- GEN-8: each comparison/boolean operator selects structure -------------- #


def _matrix_gates(tmp_path, cond):
    """Elaborate a `when {cond}`/`else` over i in 1..3 selecting OR vs AND
    gates, and return the selected/deselected gate names."""
    src = (
        "top component M(A) -> (Y[3]) {\n"
        f"    >i[1:3]{{ when {{{cond}}} {{ s{{i}}: OR; }} else {{ d{{i}}: AND; }} }}\n"
        "    connect {\n"
        f"        >i[1:3]{{ when {{{cond}}} "
        "{ A -> s{i}.A; A -> s{i}.B; s{i}.O -> Y[{i}]; } "
        "else { A -> d{i}.A; A -> d{i}.B; d{i}.O -> Y[{i}]; } }\n"
        "    }\n"
        "}"
    )
    return sorted(flatten_source(tmp_path, src).flat.netlist.gates)


def test_gen8_operator_matrix_selects_structure(tmp_path):
    # GEN-8: every RelOp, BoolAnd, BoolOr, and a parenthesized BoolExpr is
    # proven to select (s{i}) / deselect (d{i}) hardware in an elaborated when.
    expected = {
        "i == 2": ["d1", "d3", "s2"],
        "i != 2": ["d2", "s1", "s3"],
        "i < 2": ["d2", "d3", "s1"],
        "i <= 2": ["d3", "s1", "s2"],
        "i > 2": ["d1", "d2", "s3"],
        "i >= 2": ["d1", "s2", "s3"],
        "i == 1 && i < 3": ["d2", "d3", "s1"],
        "i == 1 || i == 3": ["d2", "s1", "s3"],
        "(i == 2)": ["d1", "d3", "s2"],
    }
    for cond, want in expected.items():
        assert _matrix_gates(tmp_path, cond) == want, cond


# --- GEN-10 + AMB-4: overlapping compound ranges collide naturally ---------- #


def test_gen10_overlapping_compound_ranges_collide(tmp_path):
    # GEN-10 / AMB-4: `[1:2, 2:3]` iterates verbatim, so index 2 is emitted
    # twice — a natural duplicate-instance-name E0301.
    expect_error(
        "E0301",
        tmp_path,
        "top component M(A) -> (Y) { >i[1:2, 2:3]{ b{i}: OR; } connect { A -> Y; } }",
    )


# --- GEN-11 + AMB-5: open range with an expression bound -------------------- #


def test_gen11_open_range_expression_bound(tmp_path):
    # GEN-11 / AMB-5: `>i[N/2:]` is allowed; after the bound expression
    # evaluates, the governing-signal rule resolves the open end (here width 4,
    # so i in 2..4).
    out = flatten_source(
        tmp_path,
        "top component M<N = 4>(A[N]) -> (Y[N]) {\n"
        "    >i[N]{ b{i}: OR; }\n"
        "    connect {\n"
        "        >i[N/2:]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; b{i}.O -> Y[{i}]; }\n"
        "        A[1] -> b1.A; A[1] -> b1.B; b1.O -> Y[1];\n"
        "    }\n"
        "}",
    )
    assert sorted(gate_names(out)) == ["b1", "b2", "b3", "b4"]


# --- GEN-12: declaration-context when/else (§7.7.2) ------------------------- #


def test_gen12_declaration_context_when_selects_branch(tmp_path):
    # GEN-12: a parameter-gated `when` in declaration context creates the
    # selected branch's instance and omits the deselected one.
    src = (
        "top component M<WITH = 1>(A) -> (Y) {\n"
        "    when {WITH == 1} { con: OR; } else { coff: AND; }\n"
        "    connect {\n"
        "        when {WITH == 1} { A -> con.A; A -> con.B; con.O -> Y; }\n"
        "        else             { A -> coff.A; A -> coff.B; coff.O -> Y; }\n"
        "    }\n"
        "}"
    )
    on = flatten_source(tmp_path, src)
    assert gate_names(on) == ["con"]  # coff (deselected branch) absent
    off = flatten_source(tmp_path, src.replace("WITH = 1", "WITH = 0"))
    assert gate_names(off) == ["coff"]


def test_gen12_declaration_context_when_conditional_constant(tmp_path):
    # GEN-12: a `when`-gated constant is materialized only when selected.
    src = (
        "top component M<USE = 1>(A) -> (Y) {\n"
        "    g: OR;\n"
        "    when {USE == 1} { K = 1; }\n"
        "    connect {\n"
        "        A -> g.A;\n"
        "        when {USE == 1} { K -> g.B; } else { A -> g.B; }\n"
        "        g.O -> Y;\n"
        "    }\n"
        "}"
    )
    on = flatten_source(tmp_path, src)
    assert "K" in on.meta["constants"]
    off = flatten_source(tmp_path, src.replace("USE = 1", "USE = 0"))
    assert off.meta["constants"] == {}  # deselected constant materializes nothing


# --- GEN-13 + AMB-19: range value domain (bound 0 / negative) --------------- #


def test_gen13_lower_bound_zero_iterates(tmp_path):
    # GEN-13 / AMB-19: `[0:2]` accepts 0 and iterates from index 0.
    out = flatten_source(
        tmp_path,
        "top component M(A[3]) -> (Y[3]) {\n"
        "    >i[0:2]{ b{i}: OR; }\n"
        "    connect { >i[0:2]{ A[{i+1}] -> b{i}.A; A[{i+1}] -> b{i}.B; "
        "b{i}.O -> Y[{i+1}]; } }\n"
        "}",
    )
    assert sorted(gate_names(out)) == ["b0", "b1", "b2"]


def test_gen13_negative_lower_bound_rejected(tmp_path):
    # GEN-13 / AMB-19: a negative lower bound -> E0601.
    expect_error(
        "E0601",
        tmp_path,
        "top component M(A) -> (Y) { >i[0-1:2]{ b{i}: OR; } connect { A -> Y; } }",
    )


# --- GEN-6: the six remaining E0601 raise sites (8 total) ------------------- #


def test_gen6_all_e0601_sites(tmp_path):
    # GEN-6: each of the 8 E0601 raise sites, by a dedicated minimal case.
    cases = [
        # 1) count form [0] (already covered elsewhere, kept for completeness)
        "top component M(A) -> (Y) { >i[0]{ b{i}: OR; } connect { A -> Y; } }",
        # 2) ill-ordered RangeAB [2:1]
        "top component M(A) -> (Y) { >i[2:1]{ b{i}: OR; } connect { A -> Y; } }",
        # 3) bare-negative value in a multi-range
        "top component M(A) -> (Y) { >i[1:2, 0-1]{ b{i}: OR; } connect { A -> Y; } }",
        # 4) RangeAB negative lower bound
        "top component M(A) -> (Y) { >i[0-1:2]{ b{i}: OR; } connect { A -> Y; } }",
        # 5) RangeTo bound < 1
        "top component M(A) -> (Y) { >i[:0]{ b{i}: OR; } connect { A -> Y; } }",
        # 6) open-range negative lower bound
        "top component M(A[4]) -> (Y) { b1: OR; "
        "connect { >i[0-1:]{ A[{i}] -> b1.A; } A -> b1.B; b1.O -> Y; } }",
        # 7) open-range empty after governing-signal resolution
        "top component M(A[2]) -> (Y) { b1: OR; "
        "connect { >i[3:]{ A[{i}] -> b1.A; } A[1] -> b1.B; b1.O -> Y; } }",
        # 8) replication count < 1
        "top component M(A) -> (Y[2]) { connect { {0{A}} -> Y; } }",
    ]
    for src in cases:
        expect_error("E0601", tmp_path, src)


# --- GEN-14 + AMB-20/21: governing-signal scan semantics -------------------- #


def test_gen14_same_width_signals_dedup_to_one_bound(tmp_path):
    # GEN-14 / AMB-20: two same-width signals indexed by the loop var collapse
    # to a single governing width, so the open range resolves unambiguously.
    out = flatten_source(
        tmp_path,
        "top component M(A[3], B[3]) -> (Y) {\n"
        "    o1: OR; o2: OR; o3: OR;\n"
        "    connect {\n"
        "        >i[1:]{ A[{i}] -> o{i}.A; B[{i}] -> o{i}.B; }\n"
        "        o1.O -> Y;\n"
        "    }\n"
        "}",
    )
    assert len(out.flat.netlist.gates) == 3


def test_gen14_differing_widths_e0602(tmp_path):
    # GEN-14 / AMB-20: signals of *different* widths indexed by the loop var
    # make the open-range bound ambiguous -> E0602.
    expect_error(
        "E0602",
        tmp_path,
        "top component M(A[2], C[3]) -> (Y) {\n"
        "    b1: OR; b2: OR; b3: OR;\n"
        "    connect { >i[1:]{ A[{i}] -> b{i}.A; C[{i}] -> b{i}.B; }\n"
        "              b1.O -> Y; }\n"
        "}",
    )


def test_gen14_no_governing_signal_e0602(tmp_path):
    # GEN-14: an open range whose body indexes no loop-var-governed signal ->
    # E0602 (the no-signal site).
    expect_error(
        "E0602",
        tmp_path,
        "top component M(A) -> (Y) {\n"
        "    b1: OR;\n"
        "    connect { >i[1:]{ A -> b1.A; } A -> b1.B; b1.O -> Y; }\n"
        "}",
    )


def test_gen14_else_branch_width_forces_e0602(tmp_path):
    # GEN-14 / AMB-21: both `when`/`else` bodies are scanned before the
    # condition is evaluated, so an else-branch signal of a differing width
    # ambiguates the bound even though that branch may never be emitted.
    expect_error(
        "E0602",
        tmp_path,
        "top component M(A[2], C[3]) -> (Y) {\n"
        "    b1: OR; b2: OR; b3: OR;\n"
        "    connect {\n"
        "        >i[1:]{ when {i == 1} { A[{i}] -> b{i}.A; } "
        "else { C[{i}] -> b{i}.A; } }\n"
        "        A[1] -> b1.B; A[2] -> b2.B; C[3] -> b3.B; b1.O -> Y;\n"
        "    }\n"
        "}",
    )


def test_gen14_inner_loop_var_shadowing():
    # GEN-14: an inner generator re-binding the loop var shadows it, so its
    # body does not contribute to the *outer* open range's governing scan. The
    # scan logic is asserted directly on _governing_widths (driving the exact
    # shadow path end-to-end is brittle; the unit is the contract).
    from flattener.ast_nodes import (
        Connection, Generator, IndexBit, Name, NameTemplate, Primary, RangeOpen,
    )
    from flattener.phases.expand import _governing_widths
    from flattener.source import Pos

    p = Pos("t", 1, 1)

    def prim(base, idx):
        return Primary(NameTemplate((base,), p), None, IndexBit(Name(idx, p)), p)

    # Outer >i body: A[{i}] -> X, plus an inner >i (shadowing) over B[{i}].
    inner = Generator(
        "i", p, (RangeOpen(Name("dummy", p), p),),
        (Connection(prim("B", "i"), prim("X", "i"), p),), p,
    )
    outer = Generator(
        "i", p, (RangeOpen(Name("dummy", p), p),),
        (Connection(prim("A", "i"), prim("X", "i"), p), inner), p,
    )
    widths = _governing_widths(outer, {}, lambda b, _port: {"A": 3, "B": 5}.get(b))
    # Only A (width 3) governs the outer i; B under the shadowed inner i is skipped.
    assert widths == {3}


# --- SCL-7: instance-count cap on pathological ranges ----------------------- #


def test_scl7_range_bomb_capped(tmp_path):
    # SCL-7: a `[1:10**9]` range must produce a fast structured diagnostic, not
    # an OOM hang from materializing a billion-entry list.
    d = expect_error(
        "E0601",
        tmp_path,
        "top component M(A) -> (Y) { >i[1:1000000000]{ b{i}: OR; } "
        "connect { A -> Y; } }",
    )
    assert "cap" in d.message and "1000000000" in d.message
