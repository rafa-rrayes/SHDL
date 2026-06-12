from helpers import expect_error, flatten_fixture, flatten_source


def _const_bit_type(tmp_path, value, bit):
    """Materialize bit ``bit`` of a constant of ``value`` and return its
    power-pin type ('__VCC__' for 1, '__GND__' for 0)."""
    out = flatten_source(
        tmp_path,
        f"top component M(A) -> (Y) {{ K = {value}; connect {{ K[{bit}] -> Y; }} }}",
    )
    return out.flat.netlist.gates[f"K_bit{bit}"].type_name


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


# --- CON-2: spec §8.1 truth table verbatim (incl. far-beyond bits) ---------- #


def test_con2_spec_8_1_truth_table(tmp_path):
    # CON-2: pin the §8.1 table exactly — value × bit -> materialized bit value.
    #   Value | [1] | [7] | [8] | [64]
    #     1   |  1  |  0  |  0  |  0
    #     6   |  0  |  0  |  0  |  0
    #    100  |  0  |  1  |  0  |  0
    #    255  |  1  |  1  |  1  |  0
    VCC, GND = "__VCC__", "__GND__"
    table = {
        1: {1: VCC, 7: GND, 8: GND, 64: GND},
        6: {1: GND, 7: GND, 8: GND, 64: GND},
        100: {1: GND, 7: VCC, 8: GND, 64: GND},
        255: {1: VCC, 7: VCC, 8: VCC, 64: GND},
    }
    for value, bits in table.items():
        for bit, want in bits.items():
            assert _const_bit_type(tmp_path, value, bit) == want, (value, bit)


# --- CON-4 + AMB-12: ZERO = 0 infers width 1 (a single GND bit) ------------- #


def test_con4_zero_infers_width_one(tmp_path):
    # CON-4 / AMB-12: a constant of value 0 infers width 1 (max(1, bit_length)),
    # materializing exactly one __GND__ bit — direct unit assert.
    from flattener.phases.expand import ConstInfo
    from flattener.source import Pos

    info = ConstInfo("ZERO", None, 0, Pos("t", 1, 1))
    assert info.effective_width == 1

    out = flatten_source(
        tmp_path,
        "top component M(A) -> (Y) { ZERO = 0; connect { ZERO -> Y; } }",
    )
    assert out.meta["constants"]["ZERO"]["width"] == 1
    assert list(out.meta["constants"]["ZERO"]["bits"]) == ["1"]
    assert out.flat.netlist.gates["ZERO_bit1"].type_name == "__GND__"


# --- CON-7: param-derived constant widths re-checked post-mono -------------- #


def test_con7_param_width_nonpositive_expand_e0403(tmp_path):
    # CON-7: `K[N] = v` with N bound to 0 — the non-positive width is caught at
    # the expand-phase site (validate only pre-checks *literal* widths).
    expect_error(
        "E0403",
        tmp_path,
        "component P<N = 0>(A) -> (Y) { K[N] = 1; connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P; connect { A -> p.A; p.Y -> Y; } }",
    )


def test_con7_param_width_overflow_expand_e0801(tmp_path):
    # CON-7: `K[N] = v` with v overflowing the param-derived width -> E0801 at
    # the expand-phase site.
    d = expect_error(
        "E0801",
        tmp_path,
        "component P<N = 1>(A) -> (Y) { K[N] = 3; connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P; connect { A -> p.A; p.Y -> Y; } }",
    )
    assert "3" in d.message


# --- CON-8: constant referenced via slice, incl. past significant bits ------ #


def test_con8_constant_slice_with_gnd_fill(tmp_path):
    # CON-8: a slice of a constant lowers per-bit like any sliced source; bits
    # past the significant bits fill with __GND__. FIVE = 5 = 0b101, so
    # FIVE[2:4] is bit2=0 (GND), bit3=1 (VCC), bit4=0 (GND, beyond width 3).
    out = flatten_source(
        tmp_path,
        "top component M(A) -> (Y[3]) { FIVE = 5; connect { FIVE[2:4] -> Y; } }",
    )
    g = out.flat.netlist.gates
    assert g["FIVE_bit2"].type_name == "__GND__"
    assert g["FIVE_bit3"].type_name == "__VCC__"
    assert g["FIVE_bit4"].type_name == "__GND__"  # past significant bits -> 0
    # Width is the inferred 3; the slice reaching bit 4 does not widen it.
    assert out.meta["constants"]["FIVE"]["width"] == 3
