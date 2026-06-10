from helpers import expect_error, flatten_source


def conn_strs(out):
    from shdlc.phases.flatten import node_str

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
