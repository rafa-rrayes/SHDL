"""Multi-bit poke/peek via ``ports`` metadata, dict-style access, and value
validation (V.2, plus this brief's strict/non-strict and negative-int policy)."""

from __future__ import annotations

import pytest

from SHDL import PortValueError, SignalNotFoundError

# -- multi-bit access (V.2) -----------------------------------------------------


def test_multibit_poke_peek(examples):
    with examples.fresh("adder8") as c:
        c.poke("A", 200)
        c.poke("B", 54)
        c.poke("Cin", 1)
        c.settle()
        assert c.peek("Sum") == 255
        assert c.peek("Cout") == 0


def test_multibit_carry_out(examples):
    with examples.fresh("adder8") as c:
        c.poke("A", 200)
        c.poke("B", 100)
        c.settle()
        assert c.peek("Sum") == (200 + 100) % 256
        assert c.peek("Cout") == 1


def test_dict_access_is_poke_peek(examples):
    with examples.fresh("adder8") as c:
        c["A"] = 17
        c["B"] = 25
        c.settle()
        assert c["Sum"] == c.peek("Sum") == 42
        assert c.peek("A") == 17  # __setitem__ really poked


def test_peek_of_input_returns_stored_value(examples):
    with examples.fresh("adder8") as c:
        c.poke("A", 37)
        assert c.peek("A") == 37  # no step needed; inputs read back directly


def test_contains(examples):
    with examples.fresh("adder8") as c:
        assert "A" in c
        assert "Sum" in c
        assert "nope" not in c


# -- name validation (in Python, before C) ----------------------------------------


def test_unknown_poke_lists_inputs(examples):
    with examples.fresh("adder8") as c:
        with pytest.raises(SignalNotFoundError, match=r"A, B, Cin"):
            c.poke("Q", 1)


def test_poking_an_output_is_rejected(examples):
    with examples.fresh("adder8") as c:
        with pytest.raises(SignalNotFoundError, match="output port"):
            c["Sum"] = 1


def test_unknown_peek_lists_both_directions(examples):
    with examples.fresh("adder8") as c:
        with pytest.raises(SignalNotFoundError, match=r"inputs: A, B, Cin; outputs: Sum, Cout"):
            c.peek("sum")  # case-sensitive, exactly like the language


# -- value validation: strict (default) ----------------------------------------------


def test_strict_rejects_values_that_do_not_fit(examples):
    with examples.fresh("adder8") as c:
        with pytest.raises(PortValueError, match="256 does not fit 8-bit port 'A'"):
            c.poke("A", 256)
        with pytest.raises(PortValueError):
            c.poke("A", -129)
        with pytest.raises(PortValueError):
            c.poke("Cin", 2)


def test_strict_accepts_the_full_unsigned_and_twos_complement_range(examples):
    with examples.fresh("adder8") as c:
        c.poke("A", 255)
        assert c.peek("A") == 255
        c.poke("A", 0)
        assert c.peek("A") == 0
        c.poke("A", -1)  # two's-complement convenience
        assert c.peek("A") == 255
        c.poke("A", -128)
        assert c.peek("A") == 128
        c.poke("Cin", -1)
        assert c.peek("Cin") == 1


def test_nonstrict_masks_modulo_width(examples):
    with examples.fresh("adder8", strict=False) as c:
        c.poke("A", 256)
        assert c.peek("A") == 0
        c.poke("A", 257)
        assert c.peek("A") == 1
        c.poke("A", (1 << 70) + 5)
        assert c.peek("A") == 5
        c.poke("A", -1)
        assert c.peek("A") == 255


def test_peek_is_zero_extended(examples):
    # Symmetric with poke masking: bits at or above the width are always 0.
    with examples.fresh("adder8", strict=False) as c:
        c.poke("A", 0xFFFF)
        assert c.peek("A") == 0xFF


def test_bools_are_ints(examples):
    with examples.fresh("adder8") as c:
        c.poke("Cin", True)
        assert c.peek("Cin") == 1


def test_non_int_values_are_type_errors(examples):
    with examples.fresh("adder8") as c:
        with pytest.raises(TypeError):
            c.poke("A", 1.5)
        with pytest.raises(TypeError):
            c["A"] = "1"


def test_cycle_count_validation(examples):
    with examples.fresh("adder8") as c:
        c.step(0)  # explicitly legal: does nothing
        with pytest.raises(ValueError):
            c.step(-1)
        with pytest.raises(TypeError):
            c.step(1.5)
        with pytest.raises(ValueError):
            c.step_settle(-2)


# -- the info layer ---------------------------------------------------------------------


def test_port_info(examples):
    with examples.fresh("adder8") as c:
        a = c.info.port("A")
        assert (a.direction, a.width, a.max_value, a.min_value) == ("input", 8, 255, -128)
        assert len(a.wires) == 8
        cout = c.info.port("Cout")
        assert (cout.direction, cout.width, cout.max_value) == ("output", 1, 1)
        with pytest.raises(SignalNotFoundError):
            c.info.port("nope")


def test_circuit_info(examples):
    with examples.fresh("adder8") as c:
        info = c.info
        assert info.name == "Adder8"
        assert tuple(p.name for p in info.inputs) == ("A", "B", "Cin")
        assert tuple(p.name for p in info.outputs) == ("Sum", "Cout")
        assert info.timing is not None and not info.timing.has_feedback
        assert not info.has_init
        assert info.stats["total_gates"] > 0
        assert "adder" in (info.description or "").lower()


def test_info_mappings_are_read_only(examples):
    with examples.fresh("adder8") as c:
        with pytest.raises(TypeError):
            c.info.stats["total_gates"] = 0
        with pytest.raises(TypeError):
            c.info.init["x"] = 1


def test_strict_flag_is_exposed(examples):
    with examples.fresh("adder8") as c:
        assert c.strict
    with examples.fresh("adder8", strict=False) as c:
        assert not c.strict
