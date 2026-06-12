from helpers import expect_error, flatten_source


def conn_strs(out):
    from flattener.phases.flatten import node_str

    return [f"{node_str(s)} -> {node_str(d)}" for s, d, _ in out.flat.netlist.connections]


def test_concat_lowering_order_matches_spec_6_5_2(tmp_path):
    # {hi, lo} -> Byte with 2-bit halves must emit, in order:
    # hi[2]->Byte[4]; hi[1]->Byte[3]; lo[2]->Byte[2]; lo[1]->Byte[1].
    out = flatten_source(
        tmp_path,
        "top component M(hi[2], lo[2]) -> (Byte[4]) { connect { {hi, lo} -> Byte; } }",
    )
    assert conn_strs(out) == [
        "hi_2_ -> Byte_4_",
        "hi_1_ -> Byte_3_",
        "lo_2_ -> Byte_2_",
        "lo_1_ -> Byte_1_",
    ]


def test_whole_vector_connection_msb_to_lsb(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(A[3]) -> (Y[3]) { connect { A -> Y; } }",
    )
    assert conn_strs(out) == ["A_3_ -> Y_3_", "A_2_ -> Y_2_", "A_1_ -> Y_1_"]


def test_replication_expands_copies(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(s) -> (Y[3]) { connect { {3{s}} -> Y; } }",
    )
    assert conn_strs(out) == ["s -> Y_3_", "s -> Y_2_", "s -> Y_1_"]


def test_slice_pairs_lowest_to_lowest(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(In[8]) -> (High[4]) { connect { In[5:8] -> High; } }",
    )
    assert conn_strs(out) == [
        "In_8_ -> High_4_",
        "In_7_ -> High_3_",
        "In_6_ -> High_2_",
        "In_5_ -> High_1_",
    ]


def test_width_mismatch(tmp_path):
    expect_error(
        "E0401",
        tmp_path,
        "top component M(A[2]) -> (Y[3]) { connect { A -> Y; } }",
    )


def test_bit_index_out_of_range(tmp_path):
    expect_error(
        "E0402",
        tmp_path,
        "top component M(A[2]) -> (Y) { connect { A[5] -> Y; } }",
    )


def test_slice_out_of_range(tmp_path):
    expect_error(
        "E0402",
        tmp_path,
        "top component M(A[4]) -> (Y[3]) { connect { A[3:5] -> Y; } }",
    )


def test_invalid_slice_order(tmp_path):
    expect_error(
        "E0404",
        tmp_path,
        "top component M(A[4]) -> (Y[2]) { connect { A[3:2] -> Y; } }",
    )


def test_zero_base_slice_invalid(tmp_path):
    expect_error(
        "E0404",
        tmp_path,
        "top component M(A[4]) -> (Y[2]) { connect { A[0:1] -> Y; } }",
    )


def test_input_cannot_be_destination(tmp_path):
    expect_error(
        "E0505",
        tmp_path,
        "top component M(A, B) -> (Y) { connect { A -> B; A -> Y; } }",
    )


def test_output_cannot_be_source(tmp_path):
    expect_error(
        "E0505",
        tmp_path,
        "top component M(A) -> (Y, Z) { connect { A -> Y; Y -> Z; } }",
    )


def test_instance_input_cannot_be_source(tmp_path):
    expect_error(
        "E0505",
        tmp_path,
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.A; n.A -> Y; } }",
    )


def test_instance_output_cannot_be_destination(tmp_path):
    expect_error(
        "E0505",
        tmp_path,
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.O; n.O -> Y; } }",
    )


def test_constant_cannot_be_destination(tmp_path):
    expect_error(
        "E0505",
        tmp_path,
        "top component M(A) -> (Y) { K = 1; connect { A -> K; K -> Y; } }",
    )


def test_replication_cannot_be_destination(tmp_path):
    expect_error(
        "E0505",
        tmp_path,
        "top component M(A[2]) -> (Y) { connect { A -> {2{Y}}; } }",
    )


def test_multiple_drivers(tmp_path):
    d = expect_error(
        "E0501",
        tmp_path,
        "top component M(A, B) -> (Y) { connect { A -> Y; B -> Y; } }",
    )
    assert "first driver" in d.message


def test_floating_instance_input(tmp_path):
    d = expect_error(
        "E0502",
        tmp_path,
        "top component M(A) -> (Y) { g: AND; connect { A -> g.A; g.O -> Y; } }",
    )
    assert "B" in d.message


def test_floating_output(tmp_path):
    expect_error(
        "E0503",
        tmp_path,
        "top component M(A) -> (Y, Z) { connect { A -> Y; } }",
    )


def test_floating_output_bit_of_vector(tmp_path):
    d = expect_error(
        "E0503",
        tmp_path,
        "top component M(A) -> (Y[2]) { connect { A -> Y[1]; } }",
    )
    assert "Y[2]" in d.message


# --- EXP-5: degenerate one-bit slice [k:k] is accepted ---------------------- #


def test_exp5_degenerate_slice_accepted(tmp_path):
    # EXP-5: a slice whose bounds are equal selects exactly one bit.
    out = flatten_source(
        tmp_path,
        "top component M(A[3]) -> (Y) { connect { A[2:2] -> Y; } }",
    )
    assert conn_strs(out) == ["A_2_ -> Y"]


# --- EXP-6 + AMB-6: replication count 0/negative -> E0601 ------------------- #


def test_exp6_replication_count_zero(tmp_path):
    # EXP-6 / AMB-6: a replication count of 0 is rejected (count must be >= 1).
    # The same `n < 1` guard would catch a negative count, but a negative
    # replication count is structurally unreachable: the parser only accepts a
    # non-negative NUMBER literal or an IDENT count resolving to a param/loop
    # var (both non-negative — params are E0905-checked). So 0 is the boundary.
    d = expect_error(
        "E0601",
        tmp_path,
        "top component M(A) -> (Y[2]) { connect { {0{A}} -> Y; } }",
    )
    assert "replication count must be >= 1" in d.message


# --- EXP-8: flatten-path E0501 is unreachable; message names the wire ------- #


def test_exp8_e0501_message_names_the_wire(tmp_path):
    # EXP-8: the multiple-drivers diagnostic names the offending sink, not just
    # "first driver". (The flatten.py-path E0501 is unreachable: every flat
    # sink belongs to exactly one lowered component, whose drivers are already
    # checked per-component — so this expander-path site is the live contract.)
    d = expect_error(
        "E0501",
        tmp_path,
        "top component M(A, B) -> (Y) { connect { A -> Y; B -> Y; } }",
    )
    assert "Y" in d.message and "first driver" in d.message


# --- EXP-9: self-connection E0504 policy (pinned in notes) ------------------ #
# E0504 is structurally unreachable through the public pipeline (the role
# checks in _check_role partition sources from destinations before bit
# pairing); its guard is proven via monkeypatch in the diagnostics matrix.
# Here we pin the *observable contract*: a connection of a signal to itself is
# rejected by the role rules first (E0505), so users never see a raw E0504.


def test_exp9_self_connection_rejected_by_role_first(tmp_path):
    # EXP-9: `Y -> Y` (output as source) is caught by the role check (E0505)
    # before any bit-level self-connection check could fire.
    expect_error(
        "E0505",
        tmp_path,
        "top component M(A) -> (Y, Z) { connect { A -> Y; Y -> Y; } }",
    )


# --- EXP-10: concatenation on both sides of one connection ------------------ #


def test_exp10_concat_both_sides(tmp_path):
    # EXP-10: {a,b} -> {x,y} pairs each MSB-first group bit-positionally.
    out = flatten_source(
        tmp_path,
        "top component M(a[2], b[2]) -> (x[2], y[2]) { connect { {a, b} -> {x, y}; } }",
    )
    assert conn_strs(out) == [
        "a_2_ -> x_2_",
        "a_1_ -> x_1_",
        "b_2_ -> y_2_",
        "b_1_ -> y_1_",
    ]


# --- EXP-11: multi-item replication group N{a,b} ---------------------------- #


def test_exp11_multi_item_replication_order(tmp_path):
    # EXP-11: `{2{a, b}}` emits two MSB-first copies of the group {a,b}; the
    # exact per-bit destination order is pinned end-to-end (a,b,a,b -> Y4..Y1).
    out = flatten_source(
        tmp_path,
        "top component M(a, b) -> (Y[4]) { connect { {2{a, b}} -> Y; } }",
    )
    assert conn_strs(out) == [
        "a -> Y_4_",
        "b -> Y_3_",
        "a -> Y_2_",
        "b -> Y_1_",
    ]


# --- EXP-12: open-ended slice [a:] in a connection (hi=None resolution) ------ #


def test_exp12_open_ended_slice_in_connection(tmp_path):
    # EXP-12: `In[2:]` resolves its upper bound from In's width (4) at resolve
    # time — exercising the hi=None branch end-to-end.
    out = flatten_source(
        tmp_path,
        "top component M(In[4]) -> (Hi[3]) { connect { In[2:] -> Hi; } }",
    )
    assert conn_strs(out) == [
        "In_4_ -> Hi_3_",
        "In_3_ -> Hi_2_",
        "In_2_ -> Hi_1_",
    ]


# --- EXP-13: slice/index pairing on instance ports + E0402/E0404 ------------ #


def test_exp13_instance_port_slice_pairing(tmp_path):
    # EXP-13: a slice of an instance output port pairs lowest-to-lowest. The
    # child C is a pure pass-through, so c.O[1:2] resolves through the alias
    # chain back to In[1:2]; the slice still pairs bit-for-bit with Y.
    out = flatten_source(
        tmp_path,
        "component C(A[4]) -> (O[4]) { connect { A -> O; } }\n"
        "top component M(In[4]) -> (Y[2]) { c: C; "
        "connect { In -> c.A; c.O[1:2] -> Y; } }",
    )
    assert conn_strs(out) == ["In_2_ -> Y_2_", "In_1_ -> Y_1_"]
    # And the instance-port→wire pairing is recorded in the hierarchy metadata.
    assert out.meta["hierarchy"]["M"]["instances"]["c"]["ports"]["O"] == [
        "In_1_", "In_2_", "In_3_", "In_4_"
    ]


def test_exp13_instance_port_bit_index_out_of_range(tmp_path):
    # EXP-13: E0402 indexing past an instance port's width.
    d = expect_error(
        "E0402",
        tmp_path,
        "component C(A) -> (O[2]) { connect { A -> O[1]; A -> O[2]; } }\n"
        "top component M(In) -> (Y) { c: C; connect { In -> c.A; c.O[5] -> Y; } }",
    )
    assert "c.O" in d.message


def test_exp13_instance_port_ill_ordered_slice(tmp_path):
    # EXP-13: E0404 on an ill-ordered slice of an instance port.
    d = expect_error(
        "E0404",
        tmp_path,
        "component C(A) -> (O[2]) { connect { A -> O[1]; A -> O[2]; } }\n"
        "top component M(In) -> (Y) { c: C; connect { In -> c.A; c.O[2:1] -> Y; } }",
    )
    assert "c.O" in d.message
