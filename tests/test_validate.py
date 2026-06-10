from helpers import expect_error

OK_BODY = "connect { A -> Y; }"


def test_reserved_dunder_name(tmp_path):
    expect_error("E0303", tmp_path, f"component C(__a) -> (Y) {{ {OK_BODY} }}")


def test_reserved_bus_pattern_name(tmp_path):
    expect_error("E0304", tmp_path, f"component C(Sum_2_) -> (Y) {{ {OK_BODY} }}")


def test_primitive_shadow(tmp_path):
    expect_error("E0305", tmp_path, "component AND(A, B) -> (O) { connect { A -> O; } }")


def test_unknown_component_type(tmp_path):
    expect_error(
        "E0306", tmp_path, "component C(A) -> (Y) { g: Ghost; connect { A -> Y; } }"
    )


def test_missing_connect_block(tmp_path):
    expect_error("E0309", tmp_path, "component C(A) -> (Y) { g1: NOT; }")


def test_two_connect_blocks(tmp_path):
    expect_error(
        "E0309", tmp_path, "component C(A) -> (Y) { connect { A -> Y; } connect { } }"
    )


def test_two_init_blocks(tmp_path):
    expect_error(
        "E0309",
        tmp_path,
        "component C(A) -> (Y) { n: NOT; init { n.O = 1; } init { n.O = 0; }\n"
        "connect { A -> n.A; n.O -> Y; } }",
    )


def test_two_top_components(tmp_path):
    expect_error(
        "E0310",
        tmp_path,
        f"top component C(A) -> (Y) {{ {OK_BODY} }}\n"
        f"top component D(A) -> (Y) {{ {OK_BODY} }}",
    )


def test_duplicate_component_names(tmp_path):
    expect_error(
        "E0301",
        tmp_path,
        f"component C(A) -> (Y) {{ {OK_BODY} }}\ncomponent C(A) -> (Y) {{ {OK_BODY} }}",
    )


def test_duplicate_port_names(tmp_path):
    expect_error("E0301", tmp_path, f"component C(A, A) -> (Y) {{ {OK_BODY} }}")


def test_port_instance_collision(tmp_path):
    expect_error(
        "E0301", tmp_path, "component C(A) -> (Y) { A: NOT; connect { A -> Y; } }"
    )


def test_duplicate_instance_inside_generator_body(tmp_path):
    expect_error(
        "E0301",
        tmp_path,
        "component C(A) -> (Y) { g: AND; >i[2]{ g: AND; } connect { A -> Y; } }",
    )


def test_constant_overflow_literal_width(tmp_path):
    d = expect_error(
        "E0801", tmp_path, "component C(A) -> (Y) { K[2] = 7; connect { A -> Y; } }"
    )
    assert "7" in d.message


def test_zero_literal_width(tmp_path):
    expect_error("E0403", tmp_path, f"component C(A[0]) -> (Y) {{ {OK_BODY} }}")
