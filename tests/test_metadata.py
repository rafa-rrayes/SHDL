from helpers import TS, flatten_fixture

SPEC_BLOCK_ORDER = [
    "version", "ports", "hierarchy", "source_map", "constants",
    "timing", "monitors", "stats", "doc", "init",
]


def find_file_key(mapping: dict, suffix: str) -> str:
    matches = [k for k in mapping if k.endswith(suffix)]
    assert len(matches) == 1, (suffix, list(mapping))
    return matches[0]


def test_blocks_in_spec_order():
    out = flatten_fixture("add2")
    assert list(out.meta) == SPEC_BLOCK_ORDER
    assert out.meta["version"] == "2.0"
    assert out.meta["monitors"] == {}


def test_ports_grouping_matches_spec_4_3():
    out = flatten_fixture("add2")
    assert out.meta["ports"] == {
        "inputs": {
            "A": ["A_1_", "A_2_"],
            "B": ["B_1_", "B_2_"],
            "Cin": ["Cin"],
        },
        "outputs": {
            "Sum": ["Sum_1_", "Sum_2_"],
            "Cout": ["Cout"],
        },
    }


def test_hierarchy_params_recorded_per_specialization():
    out = flatten_fixture("pipe")
    stages = out.meta["hierarchy"]["Pipe"]["instances"]
    for i in (1, 2, 3):
        entry = stages[f"stage{i}"]
        assert entry["type"] == "Stage"
        assert entry["params"] == {"W": 2, "ID": i}
        assert entry["prefix"] == f"stage{i}_"


def test_source_map_gates_have_positions():
    out = flatten_fixture("add2")
    sm = out.meta["source_map"]
    fa_file = find_file_key(sm["lines"], "fullAdder.shdl")
    entry = sm["gates"]["fa1_x1"]
    assert entry["file"] == fa_file
    assert entry["line"] == 2
    assert entry["column"] >= 1
    # lines is the inverse of gates: every gate appears on its decl line.
    for gate, where in sm["gates"].items():
        assert gate in sm["lines"][where["file"]][str(where["line"])]


def test_source_map_includes_instantiation_sites():
    out = flatten_fixture("add2")
    sm = out.meta["source_map"]
    main_file = find_file_key(sm["lines"], "add2.shdl")
    fa_file = find_file_key(sm["lines"], "fullAdder.shdl")
    # fa1 is instantiated on add2.shdl line 5, fa2 on line 6: all gates that
    # the instantiation produced are attributed to that line too.
    assert sm["lines"][main_file]["5"] == [
        "fa1_x1", "fa1_a1", "fa1_x2", "fa1_a2", "fa1_o1"
    ]
    assert sm["lines"][main_file]["6"] == [
        "fa2_x1", "fa2_a1", "fa2_x2", "fa2_a2", "fa2_o1"
    ]
    # Declaration lines inside FullAdder collect the copies from both sites.
    assert sm["lines"][fa_file]["2"] == ["fa1_x1", "fa1_a1", "fa2_x1", "fa2_a1"]
    # line keys are sorted numerically
    for lines in sm["lines"].values():
        nums = [int(k) for k in lines]
        assert nums == sorted(nums)


def test_doc_block():
    out = flatten_fixture("add2")
    doc = out.meta["doc"]
    assert doc["description"] == "2-bit ripple-carry adder"
    assert doc["source"].endswith("add2.shdl")
    assert doc["flattened_at"] == TS
    assert list(doc) == ["description", "source", "flattened_at"]


def test_doc_omits_description_without_doc_comment():
    out = flatten_fixture("adder8")
    assert "description" not in out.meta["doc"]


def test_stats_block():
    out = flatten_fixture("add2")
    assert out.meta["stats"] == {
        "total_gates": 10,
        "total_connections": 23,
        "total_ports": 8,
        "by_type": {"XOR": 4, "AND": 4, "OR": 2},
    }
    # by_type keys appear in first-gate-appearance order.
    assert list(out.meta["stats"]["by_type"]) == ["XOR", "AND", "OR"]
