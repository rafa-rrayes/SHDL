from helpers import expect_error, flatten_fixture, flatten_source


def test_referenced_bits_only():
    out = flatten_fixture("constDemo")
    consts = out.meta["constants"]
    assert set(consts) == {"FIVE"}
    assert consts["FIVE"]["value"] == 5
    assert consts["FIVE"]["width"] == 3
    # Bits 1, 2 and 9 are referenced; bit 3 (set in the value!) is not.
    assert list(consts["FIVE"]["bits"]) == ["1", "2", "9"]
    gates = out.flat.netlist.gates
    assert gates["FIVE_bit1"].type_name == "__VCC__"
    assert gates["FIVE_bit2"].type_name == "__GND__"
    assert gates["FIVE_bit9"].type_name == "__GND__"  # beyond width -> 0


def test_constant_bit_pattern():
    out = flatten_fixture("add100")  # 100 = 0b1100100 -> bits 3, 6, 7 set
    gates = out.flat.netlist.gates
    for bit in range(1, 9):
        want = "__VCC__" if bit in (3, 6, 7) else "__GND__"
        assert gates[f"Hundred_bit{bit}"].type_name == want
    assert gates["ZERO_bit1"].type_name == "__GND__"


def test_unreferenced_constant_materializes_nothing(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(A) -> (Y) { GHOST[4] = 9; connect { A -> Y; } }",
    )
    assert out.meta["constants"] == {}
    assert not out.flat.netlist.gates


def test_whole_constant_reference_uses_effective_width(tmp_path):
    out = flatten_source(
        tmp_path,
        "top component M(A) -> (Y[3]) { FIVE = 5; connect { FIVE -> Y; } }",
    )
    assert list(out.meta["constants"]["FIVE"]["bits"]) == ["1", "2", "3"]
    assert out.meta["constants"]["FIVE"]["width"] == 3  # bit_length of 5


def test_collision_with_power_pin_name(tmp_path):
    expect_error(
        "E0308",
        tmp_path,
        "top component M(A) -> (Y) {\n"
        "    FIVE[3] = 5;\n"
        "    FIVE_bit1: NOT;\n"
        "    connect { A -> FIVE_bit1.A; FIVE_bit1.O -> Y; FIVE[1] -> Y; } }",
    )


def test_constant_metadata_prefixed_in_hierarchy(tmp_path):
    out = flatten_source(
        tmp_path,
        "component Inner(A) -> (Y) { ONE = 1; o1: OR; connect "
        "{ A -> o1.A; ONE -> o1.B; o1.O -> Y; } }\n"
        "top component M(A) -> (Y) { in1: Inner; connect { A -> in1.A; in1.Y -> Y; } }",
    )
    assert list(out.meta["constants"]) == ["in1_ONE"]
    assert out.meta["constants"]["in1_ONE"]["bits"] == {"1": "in1_ONE_bit1"}
    assert out.flat.netlist.gates["in1_ONE_bit1"].type_name == "__VCC__"
