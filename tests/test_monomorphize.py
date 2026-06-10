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
