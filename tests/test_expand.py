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
