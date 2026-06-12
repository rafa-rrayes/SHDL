from helpers import expect_error, flatten_source

OK_BODY = "connect { A -> Y; }"


def test_reserved_dunder_name(tmp_path):
    expect_error("E0303", tmp_path, f"component C(__a) -> (Y) {{ {OK_BODY} }}")


def test_reserved_bus_pattern_name(tmp_path):
    expect_error("E0304", tmp_path, f"component C(Sum_2_) -> (Y) {{ {OK_BODY} }}")


def test_primitive_shadow(tmp_path):
    expect_error("E0305", tmp_path, "component AND(A, B) -> (O) { connect { A -> O; } }")


def test_unknown_component_type(tmp_path):
    expect_error("E0306", tmp_path, "component C(A) -> (Y) { g: Ghost; connect { A -> Y; } }")


def test_missing_connect_block(tmp_path):
    expect_error("E0309", tmp_path, "component C(A) -> (Y) { g1: NOT; }")


def test_two_connect_blocks(tmp_path):
    expect_error("E0309", tmp_path, "component C(A) -> (Y) { connect { A -> Y; } connect { } }")


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
        f"top component C(A) -> (Y) {{ {OK_BODY} }}\ntop component D(A) -> (Y) {{ {OK_BODY} }}",
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
    expect_error("E0301", tmp_path, "component C(A) -> (Y) { A: NOT; connect { A -> Y; } }")


def test_duplicate_instance_inside_generator_body(tmp_path):
    expect_error(
        "E0301",
        tmp_path,
        "component C(A) -> (Y) { g: AND; >i[2]{ g: AND; } connect { A -> Y; } }",
    )


def test_constant_overflow_literal_width(tmp_path):
    d = expect_error("E0801", tmp_path, "component C(A) -> (Y) { K[2] = 7; connect { A -> Y; } }")
    assert "7" in d.message


def test_zero_literal_width(tmp_path):
    expect_error("E0403", tmp_path, f"component C(A[0]) -> (Y) {{ {OK_BODY} }}")


# --- VAL-1: accept-side boundaries of the reserved-name patterns ------------ #
# `X_<digits>_` is the reserved bus pattern (E0304); `__` is the reserved
# prefix (E0303). Names that merely *resemble* these must be accepted.


def test_val1_accepts_underscore_digit_without_trailing_underscore(tmp_path):
    # VAL-1: `X_2` lacks the trailing `_`, so it is NOT the bus pattern.
    out = flatten_source(tmp_path, "top component C(X_2) -> (Y) { connect { X_2 -> Y; } }")
    assert out.meta["ports"]["inputs"] == {"X_2": ["X_2"]}


def test_val1_accepts_two_digit_groups(tmp_path):
    # VAL-1: `X_2_3` does not match `..._<digits>_$` (ends in a digit).
    out = flatten_source(tmp_path, "top component C(X_2_3) -> (Y) { connect { X_2_3 -> Y; } }")
    assert out.meta["ports"]["inputs"] == {"X_2_3": ["X_2_3"]}


def test_val1_accepts_single_leading_underscore(tmp_path):
    # VAL-1: one leading `_` is not the reserved `__` prefix.
    out = flatten_source(tmp_path, "top component C(_x) -> (Y) { connect { _x -> Y; } }")
    assert out.meta["ports"]["inputs"] == {"_x": ["_x"]}


# --- VAL-2 + AMB-23: primitive shadowing, all six, with precedence ---------- #


def test_val2_shadow_each_primitive(tmp_path):
    # VAL-2: redefining any of the six primitives -> E0305.
    for prim in ("AND", "OR", "NOT", "XOR"):
        expect_error(
            "E0305",
            tmp_path,
            f"component {prim}(A, B) -> (O) {{ connect {{ A -> O; }} }}",
        )


def test_val2_amb23_vcc_precedence_e0305_over_e0303(tmp_path):
    # AMB-23: `component __VCC__` violates both E0305 (primitive) and E0303
    # (reserved `__`); the more specific E0305 must win.
    d = expect_error("E0305", tmp_path, "component __VCC__(A) -> (Y) { connect { A -> Y; } }")
    assert "primitive" in d.message


def test_val2_amb23_gnd_precedence_e0305_over_e0303(tmp_path):
    # AMB-23: same precedence for `__GND__`.
    d = expect_error("E0305", tmp_path, "component __GND__(A) -> (Y) { connect { A -> Y; } }")
    assert "primitive" in d.message


# --- VAL-5: case sensitivity (spec §2.2) ------------------------------------ #


def test_val5_case_sensitive_names_coexist(tmp_path):
    # VAL-5: `MyGate` and `mygate` are distinct components that coexist.
    out = flatten_source(
        tmp_path,
        "component MyGate(A) -> (Y) { connect { A -> Y; } }\n"
        "top component mygate(A) -> (Y) { g: MyGate; "
        "connect { A -> g.A; g.Y -> Y; } }",
    )
    assert out.flat.netlist.name == "mygate"
    # The instance resolved to the distinct upper-case component.
    assert out.meta["hierarchy"]["mygate"]["instances"]["g"]["type"] == "MyGate"


# --- VAL-8: reserved-name checks at the remaining declare sites ------------- #


def test_val8_generator_var_reserved_dunder(tmp_path):
    # VAL-8: a generator variable using the `__` prefix -> E0303.
    expect_error(
        "E0303",
        tmp_path,
        "top component M(A) -> (Y) { >__i[2]{ b{__i}: OR; } connect { A -> Y; } }",
    )


def test_val8_generator_var_reserved_bus_pattern(tmp_path):
    # VAL-8: a generator variable matching the bus pattern -> E0304.
    expect_error(
        "E0304",
        tmp_path,
        "top component M(A) -> (Y) { >i_1_[2]{ b{i_1_}: OR; } connect { A -> Y; } }",
    )


def test_val8_constant_name_reserved_dunder(tmp_path):
    # VAL-8: a constant named with the `__` prefix -> E0303.
    expect_error(
        "E0303",
        tmp_path,
        "top component M(A) -> (Y) { __K = 1; connect { A -> Y; } }",
    )


# --- VAL-9: expansion-time name checks on *generated* names ----------------- #


def test_val9_generated_template_duplicate(tmp_path):
    # VAL-9: a template expanding to the same name twice -> E0301.
    expect_error(
        "E0301",
        tmp_path,
        "top component M(A) -> (Y) { >i[1:2, 1:2]{ b{i}: OR; } connect { A -> Y; } }",
    )


def test_val9_generated_name_collides_with_port(tmp_path):
    # VAL-9: a generated instance name colliding with a port -> E0301.
    expect_error(
        "E0301",
        tmp_path,
        "top component M(A, b1) -> (Y) { >i[1]{ b{i}: OR; } connect { A -> Y; b1 -> Y; } }",
    )


def test_val9_generated_name_matches_reserved_pattern(tmp_path):
    # VAL-9: a generated name matching the reserved bus pattern -> E0304.
    d = expect_error(
        "E0304",
        tmp_path,
        "top component M(A) -> (Y) { >i[2]{ x_{i}_: OR; } connect { A -> Y; } }",
    )
    assert "x_1_" in d.message


# --- VAL-6: E0306 unreachable monomorphize site; all 8 E0307 sites ---------- #


def test_val6_e0306_validate_site(tmp_path):
    # VAL-6: unknown component type, caught at the validate site.
    expect_error(
        "E0306",
        tmp_path,
        "top component M(A) -> (Y) { g: Ghost; connect { A -> Y; } }",
    )


def test_val6_e0306_in_unused_component(tmp_path):
    # VAL-6: validate validates *every* component, including unused ones, so
    # the monomorphize-discovery E0306 site is unreachable: the unknown type
    # is caught at validate before specialization begins.
    expect_error(
        "E0306",
        tmp_path,
        "component Unused(A) -> (Y) { g: Ghost; connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { connect { A -> Y; } }",
    )


def test_val6_e0307_all_eight_sites(tmp_path):
    # VAL-6: each of the 8 E0307 raise sites in expand.py, by a dedicated case.
    cases = [
        # signal_width: unknown whole signal (no port)
        "top component M(A) -> (Y) { connect { Ghost -> Y; } }",
        # signal_width: instance used as a whole signal
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.A; n -> Y; } }",
        # signal_width: unknown instance (with a port)
        "top component M(A) -> (Y) { connect { A -> Y; ghost.O -> Y; } }",
        # signal_width: primitive has no such port
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.A; n.Z -> Y; } }",
        # signal_width: component has no such port
        "component C(A) -> (O) { connect { A -> O; } }\n"
        "top component M(A) -> (Y) { c: C; connect { A -> c.A; c.Z -> Y; } }",
        # instance_port_dir: unknown instance (as a destination)
        "top component M(A) -> (Y) { connect { A -> ghost.A; A -> Y; } }",
        # instance_port_dir: primitive has no such port (as a destination)
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.Z; n.O -> Y; } }",
        # instance_port_dir: component has no such port (as a destination)
        "component C(A) -> (O) { connect { A -> O; } }\n"
        "top component M(A) -> (Y) { c: C; connect { A -> c.Z; c.O -> Y; } }",
    ]
    for src in cases:
        expect_error("E0307", tmp_path, src)


# --- VAL-7: negative widths + both constant-width sites + AMB-31 ------------- #


def test_val7_negative_port_width(tmp_path):
    # VAL-7: a negative port width literal -> E0403 (non-param component).
    d = expect_error("E0403", tmp_path, "component C(A[0-1]) -> (Y) { connect { A -> Y; } }")
    assert "-1" in d.message


def test_val7_constant_zero_width_validate_site(tmp_path):
    # VAL-7: zero-width constant literal, validate site -> E0403.
    expect_error("E0403", tmp_path, "top component M(A) -> (Y) { K[0] = 1; connect { A -> Y; } }")


def test_val7_constant_negative_width_validate_site(tmp_path):
    # VAL-7: negative-width constant literal, validate site -> E0403.
    d = expect_error(
        "E0403",
        tmp_path,
        "top component M(A) -> (Y) { K[0-1] = 1; connect { A -> Y; } }",
    )
    assert "-1" in d.message


def test_val7_amb31_e0906_inside_specialization(tmp_path):
    # VAL-7 / AMB-31: a literal `A[0]` *inside a parameterized component* is
    # attributed to E0906 (derived-from-params width), not E0403 — even though
    # the width is a literal — because port widths are resolved per spec.
    d = expect_error(
        "E0906",
        tmp_path,
        "component P<N = 1>(A[0]) -> (Y[N]) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P; connect { A -> Y; } }",
    )
    assert "P<N=1>" in d.message


def test_val7_amb31_e0403_outside_specialization(tmp_path):
    # VAL-7 / AMB-31: the identical `A[0]` in a non-parameterized component is
    # E0403 (the other branch of the shared monomorphize port-width site).
    d = expect_error("E0403", tmp_path, "component C(A[0]) -> (Y) { connect { A -> Y; } }")
    assert "main::C" in d.message
