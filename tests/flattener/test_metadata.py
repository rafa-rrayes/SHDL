import copy
import os
from pathlib import Path

import pytest

from helpers import FIXTURES, TS, flatten_fixture

from flattener.metadata import MetaValidationError, validate_meta, verify_meta

SPEC_BLOCK_ORDER = [
    "version", "ports", "hierarchy", "source_map", "constants",
    "timing", "monitors", "stats", "doc", "init",
]

# Every fixture top (stdgates carries multiple components — flatten one each).
ALL_TOPS = sorted(p.stem for p in FIXTURES.glob("*.shdl") if p.stem != "stdgates")


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


# ── MET-4: source_map gate→loc / lines-inverse mutual consistency ──────────
# A property test over ALL fixtures, not the add2 spot check in
# test_source_map_gates_have_positions. The two halves of source_map encode the
# same gate→site relation from opposite directions, and both directions must
# agree for every fixture: a column-attribution or inverse-index bug would
# otherwise pass a suite that only spot-checks one fixture.

@pytest.mark.parametrize("name", ALL_TOPS)
def test_source_map_gate_loc_and_lines_inverse_consistent(name):
    # MET-4
    out = flatten_fixture(name)
    sm = out.meta["source_map"]
    gates, lines = sm["gates"], sm["lines"]

    # Forward: every gate's declaration site (file, line) is listed under
    # lines[file][line], and the column is a real 1-based position.
    for gate, loc in gates.items():
        f, ln = loc["file"], str(loc["line"])
        assert loc["column"] >= 1, (name, gate, loc)
        assert f in lines, (name, gate, f, list(lines))
        assert ln in lines[f], (name, gate, ln, list(lines[f]))
        assert gate in lines[f][ln], (name, gate, loc, lines[f][ln])

    # Inverse: every gate named in any lines bucket is a real gate with a loc.
    for f, per_line in lines.items():
        for ln, bucket in per_line.items():
            for gate in bucket:
                assert gate in gates, (name, f, ln, gate)


# ── MET-7 / ROB-3: public metadata validator with structured errors ────────
# The 9 cross-consistency invariants that were bare asserts are now a public
# validator raising MetaValidationError. The pipeline still runs them
# (verify_meta delegates), so a healthy flatten must pass and each invariant
# must fire on a targeted corruption — proving the guards are live, not dead.

def test_validate_meta_accepts_healthy_metadata():
    # MET-7
    out = flatten_fixture("add2")
    assert validate_meta(out.meta, out.flat.netlist) is None
    assert verify_meta(out.meta, out.flat.netlist) is None  # pipeline hook


@pytest.mark.parametrize("name", ALL_TOPS)
def test_pipeline_metadata_passes_validator_for_every_fixture(name):
    # MET-7: the validation the pipeline ran already held; assert it directly.
    out = flatten_fixture(name)
    validate_meta(out.meta, out.flat.netlist)  # must not raise


def _corrupt(meta: dict) -> dict:
    return copy.deepcopy(meta)


def test_validate_meta_catches_port_wire_mismatch():
    # MET-7 / ROB-3: invariant 'ports'
    out = flatten_fixture("add2")
    m = _corrupt(out.meta)
    m["ports"]["inputs"]["A"] = ["A_1_", "GHOST"]
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "ports"


def test_validate_meta_catches_hierarchy_gate():
    # MET-7 / ROB-3: invariant 'hierarchy.gate'
    out = flatten_fixture("add2")
    m = _corrupt(out.meta)

    def first_leaf(instances: dict):
        for entry in instances.values():
            if "gate" in entry:
                return entry
            leaf = first_leaf(entry["instances"])
            if leaf is not None:
                return leaf
        return None

    leaf = None
    for top in m["hierarchy"].values():
        leaf = first_leaf(top["instances"])
        if leaf is not None:
            break
    assert leaf is not None, "add2 hierarchy must contain a leaf gate"
    leaf["gate"] = "GHOST_GATE"
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "hierarchy.gate"


def test_validate_meta_catches_source_map_gate_mismatch():
    # MET-7 / ROB-3: invariant 'source_map.gates'
    out = flatten_fixture("add2")
    m = _corrupt(out.meta)
    m["source_map"]["gates"]["GHOST"] = {"file": "x", "line": 1, "column": 1}
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "source_map.gates"
    assert "GHOST" in ei.value.detail


def test_validate_meta_catches_source_map_lines_alien_gate():
    # MET-7 / ROB-3: invariant 'source_map.lines'
    out = flatten_fixture("add2")
    m = _corrupt(out.meta)
    f = next(iter(m["source_map"]["lines"]))
    ln = next(iter(m["source_map"]["lines"][f]))
    m["source_map"]["lines"][f][ln] = [*m["source_map"]["lines"][f][ln], "GHOST"]
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "source_map.lines"


def test_validate_meta_catches_constant_bit_gate():
    # MET-7 / ROB-3: invariant 'constants.bits'
    out = flatten_fixture("constDemo")
    m = _corrupt(out.meta)
    const = next(iter(m["constants"].values()))
    bit = next(iter(const["bits"]))
    const["bits"][bit] = "GHOST_PIN"
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "constants.bits"


def test_validate_meta_catches_timing_output_depths():
    # MET-7 / ROB-3: invariant 'timing.output_depths'
    out = flatten_fixture("add2")
    m = _corrupt(out.meta)
    m["timing"]["output_depths"]["GHOST_OUT"] = 3
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "timing.output_depths"


def test_validate_meta_catches_critical_path_alien_node():
    # MET-7 / ROB-3: invariant 'timing.critical_path'
    out = flatten_fixture("add2")
    m = _corrupt(out.meta)
    m["timing"]["critical_path"][1] = "GHOST_GATE"
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "timing.critical_path"


def test_validate_meta_catches_init_alien_wire():
    # MET-7 / ROB-3: invariant 'init'
    out = flatten_fixture("srlatch")
    m = _corrupt(out.meta)
    m["init"] = {**m["init"], "GHOST_WIRE": 1}
    with pytest.raises(MetaValidationError) as ei:
        validate_meta(m, out.flat.netlist)
    assert ei.value.invariant == "init"


def test_meta_validation_error_survives_optimized_mode():
    # ROB-3: structured error, not a bare assert — carries invariant + detail.
    err = MetaValidationError("ports", ("inputs", ["X"]))
    assert err.invariant == "ports"
    assert err.detail == ("inputs", ["X"])
    assert "ports" in str(err)


# ── MET-8 (producer half): the emitter writes a version key ─────────────────

@pytest.mark.parametrize("name", ALL_TOPS)
def test_meta_version_emitted_and_first_block(name):
    # MET-8: producer always writes version; it leads the block order (§4.2).
    out = flatten_fixture(name)
    assert out.meta["version"] == "2.0"
    assert list(out.meta)[0] == "version"


# ── MET-9: monitors block emitted as {} (AMB-30 pin) ────────────────────────

@pytest.mark.parametrize("name", ALL_TOPS)
def test_monitors_block_emitted_empty(name):
    # MET-9 / AMB-30: V1 pins monitors to an (always-present) empty object;
    # the schema {group: [gate_or_wire,…]} is reserved by the spec package.
    out = flatten_fixture(name)
    assert "monitors" in out.meta
    assert out.meta["monitors"] == {}


# ── MET-10: source_map column exactness vs hand-counted columns ─────────────
# Lines are pinned exactly elsewhere; columns were only checked `>= 1`. Pin a
# directly-declared gate and an instantiation-reached gate to hand-counted
# columns so a column-attribution regression cannot pass the whole suite.

def test_source_map_columns_hand_counted_directly_declared():
    # MET-10: gates declared directly in the top component.
    # constDemo.shdl line 3: "    a1: AND;  a2: AND;  a3: AND;"
    # cols (1-based):          1234 5         15        25
    out = flatten_fixture("constDemo")
    g = out.meta["source_map"]["gates"]
    assert g["a1"] == {"file": "constDemo.shdl", "line": 3, "column": 5}
    assert g["a2"] == {"file": "constDemo.shdl", "line": 3, "column": 15}
    assert g["a3"] == {"file": "constDemo.shdl", "line": 3, "column": 25}
    # The constant materializes at its declaration column.
    # constDemo.shdl line 2: "    FIVE[3] = 5;" -> FIVE at column 5.
    assert g["FIVE_bit1"] == {"file": "constDemo.shdl", "line": 2, "column": 5}


def test_source_map_columns_hand_counted_via_instantiation():
    # MET-10: gates reached through an instantiation point at their own
    # declaration site inside the instantiated component.
    # fullAdder.shdl line 2: "    x1: XOR;  a1: AND;"
    # cols (1-based):         1234 5         15
    out = flatten_fixture("add2")
    g = out.meta["source_map"]["gates"]
    assert g["fa1_x1"] == {"file": "fullAdder.shdl", "line": 2, "column": 5}
    assert g["fa1_a1"] == {"file": "fullAdder.shdl", "line": 2, "column": 15}
    # The second instantiation reuses the same declaration column.
    assert g["fa2_x1"] == {"file": "fullAdder.shdl", "line": 2, "column": 5}


# ── MET-11: no absolute paths in emitted bytes ──────────────────────────────
# doc.source and source_map file keys must be basenames so output is
# checkout-location independent. The fixtures are always loaded from an
# absolute path, so the test that the absolute directory never appears in the
# emitted bytes is a real leak detector, not a tautology.

@pytest.mark.parametrize("name", ALL_TOPS)
def test_no_absolute_paths_in_emitted_metadata(name):
    # MET-11
    out = flatten_fixture(name)
    sep = os.sep

    # doc.source is a bare basename.
    src = out.meta["doc"]["source"]
    assert sep not in src, src
    assert src == os.path.basename(src)

    # Every source_map file reference (gate locs + line keys) is a basename.
    for loc in out.meta["source_map"]["gates"].values():
        assert sep not in loc["file"], loc
    for f in out.meta["source_map"]["lines"]:
        assert sep not in f, f

    # The absolute directory the file was loaded from never leaks into bytes.
    abs_dir = str(Path(FIXTURES).resolve())
    assert abs_dir not in out.text, name
    assert abs_dir not in str(out.meta), name
