from helpers import expect_error, flatten_fixture, flatten_source

from flattener.phases.flatten import node_str


def conn_strs(out):
    return [f"{node_str(s)} -> {node_str(d)}" for s, d, _ in out.flat.netlist.connections]


def test_hierarchy_prefixing_deep():
    out = flatten_fixture("alu")  # ALU -> AdderN -> FullAdder
    gates = out.flat.netlist.gates
    assert "add_fa1_x1" in gates
    assert "add_fa4_o1" in gates
    assert "z" in gates  # direct top-level power pin


def test_pass_through_resolves_to_input_wire():
    out = flatten_fixture("passthru")
    conns = conn_strs(out)
    # B[1] is driven through Wire2 -> Wire1 pure aliases back to A_1_.
    assert "A_1_ -> B_1_" in conns
    assert "A_2_ -> B_2_" in conns
    # The XOR's pins resolve through the same alias chains.
    assert "A_1_ -> x1.A" in conns
    assert "A_2_ -> x1.B" in conns
    assert list(out.flat.netlist.gates) == ["x1"]


def test_one_connection_per_sink():
    out = flatten_fixture("add2")
    sinks = [d for _, d, _ in out.flat.netlist.connections]
    assert len(sinks) == len(set(sinks))
    # Every gate input pin and every output wire appears exactly once.
    expected = {("pin", g, p) for g in out.flat.netlist.gates for p in ("A", "B")}
    expected |= {("out", w) for w in out.flat.netlist.outputs}
    assert set(sinks) == expected


def test_children_inlined_at_declaration_point():
    out = flatten_fixture("add2")
    conns = conn_strs(out)
    # All of fa1's 10 connections precede all of fa2's; the top's own
    # output connections come last.
    fa1 = [i for i, c in enumerate(conns) if "fa1_" in c.split(" -> ")[1]]
    fa2 = [i for i, c in enumerate(conns) if "fa2_" in c.split(" -> ")[1]]
    outs = [i for i, c in enumerate(conns) if c.endswith(("Sum_1_", "Sum_2_", "Cout"))]
    assert max(fa1) < min(fa2) < min(outs)


def test_hierarchy_ports_canonical_wires():
    out = flatten_fixture("add2")
    inst = out.meta["hierarchy"]["Add2"]["instances"]
    assert inst["fa1"]["ports"] == {
        "A": "A_1_", "B": "B_1_", "Cin": "Cin", "Sum": "Sum_1_", "Cout": "fa1_o1.O"
    }
    assert inst["fa2"]["ports"]["Cin"] == "fa1_o1.O"


def test_multibit_instance_ports_are_lists():
    out = flatten_fixture("alu")
    add = out.meta["hierarchy"]["ALU"]["instances"]["add"]
    assert add["params"] == {"N": 4}
    assert add["ports"]["A"] == ["A_1_", "A_2_", "A_3_", "A_4_"]
    assert add["ports"]["Cout"] == "Cout"
    # Nested level keeps its own instances map.
    assert add["instances"]["fa1"]["type"] == "FullAdder"


def test_init_seeds_canonical_keys():
    out = flatten_fixture("srlatch")
    assert out.meta["init"] == {"Q": 0, "Qn": 1}


def test_init_through_hierarchy(tmp_path):
    out = flatten_source(
        tmp_path,
        "component Cell(S) -> (Q) { n1: NOT; init { n1.O = 1; } "
        "connect { S -> n1.A; n1.O -> Q; } }\n"
        "top component M(S) -> (Q1, Q2) { c1: Cell; c2: Cell; connect "
        "{ S -> c1.S; S -> c2.S; c1.Q -> Q1; c2.Q -> Q2; } }",
    )
    assert out.meta["init"] == {"Q1": 1, "Q2": 1}


def test_init_multibit_lsb_first(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(A[3]) -> (Y[3]) {\n"
        "    >i[3]{ b{i}: OR; }\n"
        "    init { Y = 5; }\n"
        "    connect { >i[3]{ A[{i}] -> b{i}.A; A[{i}] -> b{i}.B; b{i}.O -> Y[{i}]; } }\n"
        "}",
    )
    assert out.meta["init"] == {"Y_1_": 1, "Y_2_": 0, "Y_3_": 1}


def test_pure_alias_cycle_rejected(tmp_path):
    expect_error(
        "E0506",
        tmp_path,
        "component W(In) -> (Out) { connect { In -> Out; } }\n"
        "top component M(X) -> (Y) {\n"
        "    w1: W; w2: W;\n"
        "    connect { w1.Out -> w2.In; w2.Out -> w1.In; w1.Out -> Y; }\n"
        "}",
    )


def test_flattened_name_collision(tmp_path):
    expect_error(
        "E0308",
        tmp_path,
        "component FA(A) -> (Y) { x1: NOT; connect { A -> x1.A; x1.O -> Y; } }\n"
        "top component M(A) -> (Y, Z) {\n"
        "    fa: FA;\n"
        "    fa_x1: NOT;\n"
        "    connect { A -> fa.A; fa.Y -> Y; A -> fa_x1.A; fa_x1.O -> Z; }\n"
        "}",
    )


def test_init_target_input_rejected(tmp_path):
    expect_error(
        "E0A01",
        tmp_path,
        "top component M(A) -> (Y) { init { A = 1; } connect { A -> Y; } }",
    )


def test_init_double_seed_rejected(tmp_path):
    expect_error(
        "E0A02",
        tmp_path,
        "top component M(A) -> (Y) { n: NOT; init { n.O = 1; Y = 0; } "
        "connect { A -> n.A; n.O -> Y; } }",
    )


def test_init_value_overflow(tmp_path):
    expect_error(
        "E0A03",
        tmp_path,
        "top component M(A) -> (Y) { n: NOT; init { n.O = 2; } "
        "connect { A -> n.A; n.O -> Y; } }",
    )
