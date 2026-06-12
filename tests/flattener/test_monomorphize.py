from helpers import expect_error, flatten_fixture, flatten_source

P2 = "component P(A[2]) -> (Y[2]) { connect { A -> Y; } }"


def test_distinct_bindings_distinct_specs():
    out = flatten_fixture("pipe")
    stage_keys = [k for k in out.mono.specs if k.startswith("pipe::Stage")]
    # ID depends on the loop variable -> three distinct specializations.
    assert len(stage_keys) == 3
    assert {out.mono.specs[k].bindings["ID"] for k in stage_keys} == {1, 2, 3}
    assert all(out.mono.specs[k].bindings["W"] == 2 for k in stage_keys)


def test_identical_bindings_dedup(tmp_path):
    out = flatten_source(
        tmp_path,
        "component P<N = 2>(A[N]) -> (Y[N]) { connect { A -> Y; } }\n"
        "top component M(A[2]) -> (Y[2], Z[2]) {\n"
        "    p1: P<2>; p2: P<N = 2>;\n"
        "    connect { A -> p1.A; A -> p2.A; p1.Y -> Y; p2.Y -> Z; }\n"
        "}",
    )
    p_keys = [k for k in out.mono.specs if "::P<" in k]
    assert len(p_keys) == 1  # positional 2 and named N=2 are the same spec


def test_parameter_passthrough():
    out = flatten_fixture("alu")
    assert any("AdderN<N=4>" in k or "AdderN<N = 4>" in k for k in out.mono.specs)


def test_default_used_when_omitted(tmp_path):
    out = flatten_source(
        tmp_path,
        "component P<N = 3>(A[N]) -> (Y[N]) { connect { A -> Y; } }\n"
        "top component M(A[3]) -> (Y[3]) { p: P; connect { A -> p.A; p.Y -> Y; } }",
    )
    (key,) = [k for k in out.mono.specs if "::P<" in k]
    assert out.mono.specs[key].bindings == {"N": 3}


def test_port_width_from_param():
    out = flatten_fixture("repeater")
    spec = out.mono.specs[out.mono.top_key]
    assert spec.port_width("Out") == 6  # N * M = 2 * 3


def test_top_requires_defaults(tmp_path):
    expect_error(
        "E0902", tmp_path, "top component M<N>(A[N]) -> (Y[N]) { connect { A -> Y; } }"
    )


def test_unknown_named_argument(tmp_path):
    expect_error(
        "E0901",
        tmp_path,
        P2.replace("component P(A[2])", "component P<N = 2>(A[2])") + "\n"
        "top component M(A[2]) -> (Y[2]) { p: P<Q = 1>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    )


def test_unbound_parameter(tmp_path):
    expect_error(
        "E0902",
        tmp_path,
        "component P<N>(A[2]) -> (Y[2]) { connect { A -> Y; } }\n"
        "top component M(A[2]) -> (Y[2]) { p: P; connect { A -> p.A; p.Y -> Y; } }",
    )


def test_positional_after_named(tmp_path):
    expect_error(
        "E0903",
        tmp_path,
        "component P<M = 1, N = 1>(A[2]) -> (Y[2]) { connect { A -> Y; } }\n"
        "top component M(A[2]) -> (Y[2]) { p: P<M = 1, 2>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    )


def test_too_many_positional(tmp_path):
    expect_error(
        "E0903",
        tmp_path,
        "component P<N = 1>(A[2]) -> (Y[2]) { connect { A -> Y; } }\n"
        "top component M(A[2]) -> (Y[2]) { p: P<1, 2>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    )


def test_parameter_bound_twice(tmp_path):
    expect_error(
        "E0904",
        tmp_path,
        "component P<N = 1>(A[2]) -> (Y[2]) { connect { A -> Y; } }\n"
        "top component M(A[2]) -> (Y[2]) { p: P<1, N = 2>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    )


def test_negative_argument(tmp_path):
    expect_error(
        "E0905",
        tmp_path,
        "component P<N = 1>(A[2]) -> (Y[2]) { connect { A -> Y; } }\n"
        "top component M(A[2]) -> (Y[2]) { p: P<0 - 1>; "
        "connect { A -> p.A; p.Y -> Y; } }",
    )


def test_recursive_instantiation(tmp_path):
    expect_error(
        "E0311",
        tmp_path,
        "top component R(A) -> (Y) { r: R; connect { A -> r.A; r.Y -> Y; } }",
    )


def test_mutually_recursive_instantiation(tmp_path):
    expect_error(
        "E0311",
        tmp_path,
        "component A1(X) -> (Y) { b: B1; connect { X -> b.X; b.Y -> Y; } }\n"
        "component B1(X) -> (Y) { a: A1; connect { X -> a.X; a.Y -> Y; } }\n"
        "top component M(X) -> (Y) { a: A1; connect { X -> a.X; a.Y -> Y; } }",
    )


def test_param_width_not_positive(tmp_path):
    expect_error(
        "E0906",
        tmp_path,
        "component P<N = 1>(A[N]) -> (Y[N]) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P<0>; connect { A -> p.A; p.Y -> Y; } }",
    )


# --- MON-2: E0901 also fires for a primitive instantiated with params ------- #


def test_mon2_primitive_with_params_validate_site(tmp_path):
    # MON-2: `g: AND<1>` — a primitive cannot take parameters; the validate
    # site (_check_type_ref) catches it.
    d = expect_error(
        "E0901",
        tmp_path,
        "top component M(A, B) -> (Y) { g: AND<1>; "
        "connect { A -> g.A; B -> g.B; g.O -> Y; } }",
    )
    assert "AND" in d.message


def test_mon2_primitive_with_params_generated_name(tmp_path):
    # MON-2: validate walks templated instance decls too, so even a generated
    # `g{i}: AND<1>` is caught at validate — the monomorphize on_instance
    # E0901 site (for primitive-with-args) is unreachable through the pipeline.
    expect_error(
        "E0901",
        tmp_path,
        "top component M(A, B) -> (Y) { >i[1]{ g{i}: AND<1>; } "
        "connect { A -> g1.A; B -> g1.B; g1.O -> Y; } }",
    )


# --- MON-3: E0902 via the selection path (sole component / --top, no marker) - #


def test_mon3_sole_component_with_unbound_param(tmp_path):
    # MON-3: a sole (unmarked) component with a defaultless param becomes the
    # top by the sole-component rule; the monomorphize() driver raises E0902.
    expect_error(
        "E0902",
        tmp_path,
        "component M<N>(A[N]) -> (Y[N]) { connect { A -> Y; } }",
    )


def test_mon3_explicit_top_without_marker_unbound_param(tmp_path):
    # MON-3: `--top M` selecting an unmarked component with a defaultless
    # param — same monomorphize-path E0902 (validate's E0902 only fires for
    # `top`-marked components).
    expect_error(
        "E0902",
        tmp_path,
        "component M<N>(A[N]) -> (Y[N]) { connect { A -> Y; } }",
        top="M",
    )


# --- MON-5: dependent params in range / when expressions -------------------- #


def test_mon5_range_expression_over_param(tmp_path):
    # MON-5: a generator range bound derived from an earlier param (`>i[N]`).
    out = flatten_source(
        tmp_path,
        "top component M<N = 3>(A[N]) -> (Y[N]) {\n"
        "    >i[N]{ b{i}: OR; }\n"
        "    connect { >i[N]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; "
        "b{i}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert sorted(out.flat.netlist.gates) == ["b1", "b2", "b3"]


def test_mon5_when_condition_over_param(tmp_path):
    # MON-5: a `when` condition comparing against a param selects structure.
    # (Declaration-context `when` needs distinct names per branch — validate
    # pre-declares both branches.)
    src = (
        "top component M<W = 1>(A) -> (Y) {\n"
        "    when {W == 1} { gon: OR; } else { goff: AND; }\n"
        "    connect {\n"
        "        when {W == 1} { A -> gon.A; A -> gon.B; gon.O -> Y; }\n"
        "        else          { A -> goff.A; A -> goff.B; goff.O -> Y; }\n"
        "    }\n"
        "}"
    )
    out = flatten_source(tmp_path, src)
    (gate,) = out.flat.netlist.gates.values()
    assert gate.type_name == "OR"
    out0 = flatten_source(tmp_path, src.replace("W = 1", "W = 0"))
    (gate0,) = out0.flat.netlist.gates.values()
    assert gate0.type_name == "AND"


# --- MON-6 + AMB-22: parameter scope under range shadowing ------------------ #


def test_mon6_range_evaluates_param_shadowed_by_loop_var(tmp_path):
    # MON-6 / AMB-22: `>N[N]` — the range bound `N` evaluates in the enclosing
    # scope (the param's value, 3), while the body sees the loop variable.
    out = flatten_source(
        tmp_path,
        "top component M<N = 3>(A[N]) -> (Y[N]) {\n"
        "    >N[N]{ b{N}: OR; }\n"
        "    connect { >N[N]{ A[{N}] -> b{N}.A; A[{N}] -> b{N}.B; "
        "b{N}.O -> Y[{N}]; } }\n"
        "}",
    )
    # Loop iterates 1..3 (the param value), body uses the loop var.
    assert sorted(out.flat.netlist.gates) == ["b1", "b2", "b3"]


def test_mon6_out_of_scope_param_reference(tmp_path):
    # MON-6: a parameter of one component referenced from another -> E0603
    # (params are scoped to their declaring component; outside it the name is
    # not in any generator/parameter scope).
    expect_error(
        "E0603",
        tmp_path,
        "component C<W = 2>(A[W]) -> (Y[W]) { connect { A -> Y; } }\n"
        "top component M(A[2]) -> (Y[2]) { b1: OR; "
        "connect { A[{W}] -> b1.A; A -> Y; } }",
    )


# --- MON-7: specialization scale ------------------------------------------- #


def test_mon7_hundred_specializations(tmp_path):
    # MON-7: 100 distinct Rep<k> specializations produce the correct gate
    # count (1 + 2 + ... + 100 = 5050) without superlinear blowup.
    insts = "; ".join(f"r{k}: Rep<{k}>" for k in range(1, 101))
    conns = "; ".join(f"A -> r{k}.A" for k in range(1, 101))
    out = flatten_source(
        tmp_path,
        "component Rep<N = 1>(A) -> (Y) { >i[N]{ x{i}: OR; } "
        "connect { >i[N]{ A -> x{i}.A; A -> x{i}.B; } x1.O -> Y; } }\n"
        f"top component T(A) -> (Y) {{ {insts}; "
        f"connect {{ {conns}; r1.Y -> Y; }} }}",
    )
    rep_specs = [k for k in out.mono.specs if "::Rep<" in k]
    assert len(rep_specs) == 100
    assert len(out.flat.netlist.gates) == 5050


# --- MON-8: named-arg order canonicalization dedup -------------------------- #


def test_mon8_named_arg_order_dedup(tmp_path):
    # MON-8: `P<N=2, M=1>` and `P<M=1, N=2>` bind to the *same* tuple after
    # declaration-order normalization, so they dedup to one specialization.
    out = flatten_source(
        tmp_path,
        "component P<N = 1, M = 1>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component T(A) -> (Y1, Y2) {\n"
        "    p1: P<N = 2, M = 1>; p2: P<M = 1, N = 2>;\n"
        "    connect { A -> p1.A; p1.Y -> Y1; A -> p2.A; p2.Y -> Y2; }\n"
        "}",
    )
    p_keys = [k for k in out.mono.specs if "::P<" in k]
    assert len(p_keys) == 1
    assert out.mono.specs[p_keys[0]].bindings == {"N": 2, "M": 1}
