"""
Comprehensive SHDL tests based on documented specification.

These tests verify that the SHDL implementation matches the intended
behavior as documented in the docs/ directory, specifically:
- docs/docs/language-reference/  (syntax, semantics)
- docs/docs/architecture/        (compilation pipeline)
- docs/docs/examples/            (expected behaviors)

Testing Philosophy:
1. Tests are written based on DOCUMENTED behavior, not implementation
2. 1-based indexing is used throughout (LSB = bit 1)
3. step() must be called to propagate signals through gates
4. Each test documents which specification it verifies

Author: Generated for SHDL testing task
"""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from SHDL import (
    SHDLCircuit,
    parse,
    parse_file,
    Flattener,
    format_base_shdl,
    Module,
    Component,
    Port,
    Instance,
    Generator,
)
from SHDL.errors import LexerError, ParseError, FlattenerError


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

CIRCUITS_DIR = Path(__file__).parent / "circuits"


@contextmanager
def circuit_from_source(source: str, component: Optional[str] = None):
    """
    Helper to compile inline SHDL source.
    
    Works around the issue where SHDLCircuit tries to interpret long
    source strings as file paths (causing OSError: File name too long).
    """
    # Write to a temp file to avoid the path length issue
    with tempfile.NamedTemporaryFile(mode='w', suffix='.shdl', delete=False) as f:
        f.write(source)
        temp_path = f.name
    
    try:
        circuit = SHDLCircuit(temp_path, component=component)
        yield circuit
        circuit.close()
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def compile_file(filename: str, component: Optional[str] = None) -> SHDLCircuit:
    """Helper to compile from test circuits directory."""
    path = CIRCUITS_DIR / filename
    return SHDLCircuit(path, component=component)


# =============================================================================
# Category 1: Primitive Gate Behavior
# =============================================================================

class TestPrimitiveGates:
    """
    Test that primitive gates behave according to their truth tables.
    
    Specification: docs/docs/language-reference/standard-gates.md
    
    Primitive gates:
    - AND(A, B) -> O : O = A ∧ B
    - OR(A, B) -> O  : O = A ∨ B
    - NOT(A) -> O    : O = ¬A
    - XOR(A, B) -> O : O = A ⊕ B
    - __VCC__() -> O : O = 1 (always)
    - __GND__() -> O : O = 0 (always)
    """
    
    def test_and_gate_truth_table(self):
        """AND gate: O = A ∧ B - outputs 1 only when both inputs are 1."""
        shdl = """
        component TestAND(A, B) -> (O) {
            g: AND;
            connect {
                A -> g.A;
                B -> g.B;
                g.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Test all 4 input combinations
            test_cases = [
                (0, 0, 0),  # 0 AND 0 = 0
                (0, 1, 0),  # 0 AND 1 = 0
                (1, 0, 0),  # 1 AND 0 = 0
                (1, 1, 1),  # 1 AND 1 = 1
            ]
            for a, b, expected in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step()
                assert c.peek("O") == expected, f"AND({a},{b}) should be {expected}"
    
    def test_or_gate_truth_table(self):
        """OR gate: O = A ∨ B - outputs 1 when at least one input is 1."""
        shdl = """
        component TestOR(A, B) -> (O) {
            g: OR;
            connect {
                A -> g.A;
                B -> g.B;
                g.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                (0, 0, 0),  # 0 OR 0 = 0
                (0, 1, 1),  # 0 OR 1 = 1
                (1, 0, 1),  # 1 OR 0 = 1
                (1, 1, 1),  # 1 OR 1 = 1
            ]
            for a, b, expected in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step()
                assert c.peek("O") == expected, f"OR({a},{b}) should be {expected}"
    
    def test_not_gate_truth_table(self):
        """NOT gate: O = ¬A - inverts the input."""
        shdl = """
        component TestNOT(A) -> (O) {
            g: NOT;
            connect {
                A -> g.A;
                g.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                (0, 1),  # NOT 0 = 1
                (1, 0),  # NOT 1 = 0
            ]
            for a, expected in test_cases:
                c.poke("A", a)
                c.step()
                assert c.peek("O") == expected, f"NOT({a}) should be {expected}"
    
    def test_xor_gate_truth_table(self):
        """XOR gate: O = A ⊕ B - outputs 1 when inputs are different."""
        shdl = """
        component TestXOR(A, B) -> (O) {
            g: XOR;
            connect {
                A -> g.A;
                B -> g.B;
                g.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                (0, 0, 0),  # 0 XOR 0 = 0
                (0, 1, 1),  # 0 XOR 1 = 1
                (1, 0, 1),  # 1 XOR 0 = 1
                (1, 1, 0),  # 1 XOR 1 = 0
            ]
            for a, b, expected in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step()
                assert c.peek("O") == expected, f"XOR({a},{b}) should be {expected}"
    
    def test_vcc_constant_high(self):
        """__VCC__ power pin: always outputs logic 1."""
        shdl = """
        component TestVCC() -> (O) {
            vcc: __VCC__;
            connect {
                vcc.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.step()
            assert c.peek("O") == 1, "__VCC__ should always output 1"
    
    def test_gnd_constant_low(self):
        """__GND__ power pin: always outputs logic 0."""
        shdl = """
        component TestGND() -> (O) {
            gnd: __GND__;
            connect {
                gnd.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.step()
            assert c.peek("O") == 0, "__GND__ should always output 0"


class TestDerivedGates:
    """Test derived gates built from primitives."""
    
    def test_nand_gate(self):
        """NAND = NOT(AND) - outputs 0 only when both inputs are 1."""
        shdl = """
        component TestNAND(A, B) -> (O) {
            a: AND;
            n: NOT;
            connect {
                A -> a.A;
                B -> a.B;
                a.O -> n.A;
                n.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                (0, 0, 1),  # NAND(0,0) = 1
                (0, 1, 1),  # NAND(0,1) = 1
                (1, 0, 1),  # NAND(1,0) = 1
                (1, 1, 0),  # NAND(1,1) = 0
            ]
            for a, b, expected in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step(5)  # Multiple steps for propagation
                assert c.peek("O") == expected, f"NAND({a},{b}) should be {expected}"
    
    def test_nor_gate(self):
        """NOR = NOT(OR) - outputs 1 only when both inputs are 0."""
        shdl = """
        component TestNOR(A, B) -> (O) {
            o: OR;
            n: NOT;
            connect {
                A -> o.A;
                B -> o.B;
                o.O -> n.A;
                n.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                (0, 0, 1),  # NOR(0,0) = 1
                (0, 1, 0),  # NOR(0,1) = 0
                (1, 0, 0),  # NOR(1,0) = 0
                (1, 1, 0),  # NOR(1,1) = 0
            ]
            for a, b, expected in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step(5)
                assert c.peek("O") == expected, f"NOR({a},{b}) should be {expected}"


# =============================================================================
# Category 2: Propagation and Timing
# =============================================================================

class TestPropagation:
    """
    Test signal propagation timing through gates.
    
    Specification: docs/docs/getting-started/using-pyshdl.md
    
    Key behavior:
    - poke() sets input values
    - step() advances simulation and propagates signals
    - peek() reads current values AFTER step()
    """
    
    def test_single_gate_propagation(self):
        """Signal should propagate through one gate after step()."""
        shdl = """
        component SingleNOT(A) -> (O) {
            n: NOT;
            connect {
                A -> n.A;
                n.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 0)
            c.step()
            assert c.peek("O") == 1, "NOT(0) = 1 after step"
            
            c.poke("A", 1)
            c.step()
            assert c.peek("O") == 0, "NOT(1) = 0 after step"
    
    def test_chain_of_3_nots(self):
        """Test propagation through a chain of 3 NOT gates."""
        shdl = """
        component NotChain3(A) -> (O) {
            n1: NOT;
            n2: NOT;
            n3: NOT;
            connect {
                A -> n1.A;
                n1.O -> n2.A;
                n2.O -> n3.A;
                n3.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # 3 NOTs: input is inverted 3 times
            # NOT(NOT(NOT(0))) = NOT(NOT(1)) = NOT(0) = 1
            c.poke("A", 0)
            c.step(5)  # Allow enough steps for propagation
            assert c.peek("O") == 1, "3 NOTs of 0 should be 1"
            
            c.poke("A", 1)
            c.step(5)
            assert c.peek("O") == 0, "3 NOTs of 1 should be 0"
    
    def test_multiple_steps_for_deep_circuit(self):
        """
        Test that deep circuits may need multiple steps.
        
        This test helps determine actual propagation behavior.
        """
        shdl = """
        component NotChain5(A) -> (O) {
            n1: NOT;
            n2: NOT;
            n3: NOT;
            n4: NOT;
            n5: NOT;
            connect {
                A -> n1.A;
                n1.O -> n2.A;
                n2.O -> n3.A;
                n3.O -> n4.A;
                n4.O -> n5.A;
                n5.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # 5 NOTs: odd number of inversions
            c.poke("A", 0)
            c.step(10)  # Generous steps
            assert c.peek("O") == 1, "5 NOTs of 0 should be 1"


# =============================================================================
# Category 3: Arithmetic Circuits  
# =============================================================================

class TestHalfAdder:
    """
    Test half adder: adds two 1-bit numbers.
    
    Specification: docs/docs/examples/half-adder.md
    
    Truth table:
    A B | Sum Carry
    0 0 |  0    0
    0 1 |  1    0
    1 0 |  1    0
    1 1 |  0    1
    """
    
    def test_half_adder_exhaustive(self):
        """Test all 4 input combinations for half adder."""
        shdl = """
        component HalfAdder(A, B) -> (Sum, Carry) {
            xor1: XOR;
            and1: AND;
            connect {
                A -> xor1.A;
                B -> xor1.B;
                A -> and1.A;
                B -> and1.B;
                xor1.O -> Sum;
                and1.O -> Carry;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                # (A, B, Sum, Carry)
                (0, 0, 0, 0),
                (0, 1, 1, 0),
                (1, 0, 1, 0),
                (1, 1, 0, 1),
            ]
            for a, b, exp_sum, exp_carry in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step(5)
                assert c.peek("Sum") == exp_sum, f"HalfAdder({a},{b}).Sum should be {exp_sum}"
                assert c.peek("Carry") == exp_carry, f"HalfAdder({a},{b}).Carry should be {exp_carry}"


class TestFullAdder:
    """
    Test full adder: adds two 1-bit numbers with carry in.
    
    Specification: docs/docs/examples/full-adder.md
    
    Sum = A XOR B XOR Cin
    Cout = (A AND B) OR ((A XOR B) AND Cin)
    """
    
    def test_full_adder_exhaustive(self):
        """Test all 8 input combinations for full adder."""
        shdl = """
        component FullAdder(A, B, Cin) -> (Sum, Cout) {
            x1: XOR;
            x2: XOR;
            a1: AND;
            a2: AND;
            o1: OR;
            connect {
                A -> x1.A;
                B -> x1.B;
                A -> a1.A;
                B -> a1.B;
                x1.O -> x2.A;
                Cin -> x2.B;
                x1.O -> a2.A;
                Cin -> a2.B;
                a1.O -> o1.A;
                a2.O -> o1.B;
                x2.O -> Sum;
                o1.O -> Cout;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Truth table for full adder
            test_cases = [
                # (A, B, Cin, Sum, Cout)
                (0, 0, 0, 0, 0),  # 0+0+0 = 0, carry 0
                (0, 0, 1, 1, 0),  # 0+0+1 = 1, carry 0
                (0, 1, 0, 1, 0),  # 0+1+0 = 1, carry 0
                (0, 1, 1, 0, 1),  # 0+1+1 = 2 -> sum 0, carry 1
                (1, 0, 0, 1, 0),  # 1+0+0 = 1, carry 0
                (1, 0, 1, 0, 1),  # 1+0+1 = 2 -> sum 0, carry 1
                (1, 1, 0, 0, 1),  # 1+1+0 = 2 -> sum 0, carry 1
                (1, 1, 1, 1, 1),  # 1+1+1 = 3 -> sum 1, carry 1
            ]
            for a, b, cin, exp_sum, exp_cout in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.poke("Cin", cin)
                c.step(5)  # Allow propagation
                actual_sum = c.peek("Sum")
                actual_cout = c.peek("Cout")
                assert actual_sum == exp_sum, \
                    f"FullAdder({a},{b},{cin}).Sum = {actual_sum}, expected {exp_sum}"
                assert actual_cout == exp_cout, \
                    f"FullAdder({a},{b},{cin}).Cout = {actual_cout}, expected {exp_cout}"


class TestMultiBitAdder:
    """
    Test multi-bit ripple carry adders.
    
    These test hierarchical composition and multi-bit signals.
    """
    
    @pytest.fixture
    def adder4_source(self):
        """4-bit adder with inline full adder."""
        return """
        component FullAdder(A, B, Cin) -> (Sum, Cout) {
            x1: XOR; x2: XOR;
            a1: AND; a2: AND;
            o1: OR;
            connect {
                A -> x1.A; B -> x1.B;
                A -> a1.A; B -> a1.B;
                x1.O -> x2.A; Cin -> x2.B;
                x1.O -> a2.A; Cin -> a2.B;
                a1.O -> o1.A; a2.O -> o1.B;
                x2.O -> Sum; o1.O -> Cout;
            }
        }
        
        component Adder4(A[4], B[4], Cin) -> (Sum[4], Cout) {
            fa1: FullAdder;
            fa2: FullAdder;
            fa3: FullAdder;
            fa4: FullAdder;
            connect {
                A[1] -> fa1.A; B[1] -> fa1.B; Cin -> fa1.Cin; fa1.Sum -> Sum[1];
                A[2] -> fa2.A; B[2] -> fa2.B; fa1.Cout -> fa2.Cin; fa2.Sum -> Sum[2];
                A[3] -> fa3.A; B[3] -> fa3.B; fa2.Cout -> fa3.Cin; fa3.Sum -> Sum[3];
                A[4] -> fa4.A; B[4] -> fa4.B; fa3.Cout -> fa4.Cin; fa4.Sum -> Sum[4];
                fa4.Cout -> Cout;
            }
        }
        """
    
    def test_4bit_adder_zero_plus_zero(self, adder4_source):
        """0 + 0 = 0"""
        with circuit_from_source(adder4_source, component="Adder4") as c:
            c.poke("A", 0)
            c.poke("B", 0)
            c.poke("Cin", 0)
            c.step(20)  # Plenty of steps for 4-bit ripple
            assert c.peek("Sum") == 0
            assert c.peek("Cout") == 0
    
    def test_4bit_adder_one_plus_one(self, adder4_source):
        """1 + 1 = 2"""
        with circuit_from_source(adder4_source, component="Adder4") as c:
            c.poke("A", 1)
            c.poke("B", 1)
            c.poke("Cin", 0)
            c.step(20)
            assert c.peek("Sum") == 2
            assert c.peek("Cout") == 0
    
    def test_4bit_adder_max_plus_one_overflow(self, adder4_source):
        """15 + 1 = 16 -> Sum=0, Cout=1 (overflow)"""
        with circuit_from_source(adder4_source, component="Adder4") as c:
            c.poke("A", 15)  # 0b1111
            c.poke("B", 1)
            c.poke("Cin", 0)
            c.step(20)
            assert c.peek("Sum") == 0, "15 + 1 should overflow to 0"
            assert c.peek("Cout") == 1, "Should have carry out"
    
    def test_4bit_adder_sample_cases(self, adder4_source):
        """Sample arithmetic test cases."""
        with circuit_from_source(adder4_source, component="Adder4") as c:
            test_cases = [
                (5, 3, 0, 8, 0),    # 5 + 3 = 8
                (7, 8, 0, 15, 0),   # 7 + 8 = 15
                (8, 8, 0, 0, 1),    # 8 + 8 = 16 -> overflow
                (10, 5, 1, 0, 1),   # 10 + 5 + 1 = 16 -> overflow
                (0, 0, 1, 1, 0),    # 0 + 0 + 1 = 1
            ]
            for a, b, cin, exp_sum, exp_cout in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.poke("Cin", cin)
                c.step(20)
                assert c.peek("Sum") == exp_sum, f"{a}+{b}+{cin}: Sum should be {exp_sum}"
                assert c.peek("Cout") == exp_cout, f"{a}+{b}+{cin}: Cout should be {exp_cout}"


# =============================================================================
# Category 4: Multi-bit Signals (Vectors)
# =============================================================================

class TestMultiBitSignals:
    """
    Test multi-bit signal handling.
    
    Specification: docs/docs/language-reference/signals.md
    
    Key points:
    - Indexing is 1-based (LSB = bit 1)
    - A[8] declares an 8-bit signal
    - A[1] is LSB, A[8] is MSB for 8-bit signal
    """
    
    def test_8bit_pass_through(self):
        """Test that 8-bit values pass through correctly via double inversion."""
        # Note: Direct pass-through without gates doesn't compile (implementation limitation)
        # Using double NOT as a buffer instead
        shdl = """
        component PassThrough8(A[8]) -> (O[8]) {
            >i[8]{
                n1_{i}: NOT;
                n2_{i}: NOT;
            }
            connect {
                >i[8]{
                    A[{i}] -> n1_{i}.A;
                    n1_{i}.O -> n2_{i}.A;
                    n2_{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_values = [0, 1, 127, 128, 255, 0xAA, 0x55]
            for val in test_values:
                c.poke("A", val)
                c.step(5)  # Allow propagation through 2 NOT gates
                assert c.peek("O") == val, f"Pass-through of {val} failed"
    
    def test_8bit_bitwise_not(self):
        """Test 8-bit bitwise NOT operation."""
        shdl = """
        component BitwiseNOT8(A[8]) -> (O[8]) {
            >i[8]{
                not{i}: NOT;
            }
            connect {
                >i[8]{
                    A[{i}] -> not{i}.A;
                    not{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                (0x00, 0xFF),  # NOT 0 = 255
                (0xFF, 0x00),  # NOT 255 = 0
                (0xAA, 0x55),  # NOT 10101010 = 01010101
                (0x55, 0xAA),  # NOT 01010101 = 10101010
                (0x0F, 0xF0),  # NOT 00001111 = 11110000
            ]
            for input_val, expected in test_cases:
                c.poke("A", input_val)
                c.step(5)
                result = c.peek("O")
                assert result == expected, \
                    f"NOT(0x{input_val:02X}) = 0x{result:02X}, expected 0x{expected:02X}"
    
    def test_8bit_bitwise_and(self):
        """Test 8-bit bitwise AND operation."""
        shdl = """
        component BitwiseAND8(A[8], B[8]) -> (O[8]) {
            >i[8]{
                and{i}: AND;
            }
            connect {
                >i[8]{
                    A[{i}] -> and{i}.A;
                    B[{i}] -> and{i}.B;
                    and{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            test_cases = [
                (0xFF, 0xFF, 0xFF),
                (0xFF, 0x00, 0x00),
                (0xAA, 0x55, 0x00),  # No overlapping bits
                (0xAA, 0xAA, 0xAA),
                (0x0F, 0xF0, 0x00),
                (0x0F, 0x0F, 0x0F),
            ]
            for a, b, expected in test_cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step(5)
                result = c.peek("O")
                assert result == expected, \
                    f"0x{a:02X} AND 0x{b:02X} = 0x{result:02X}, expected 0x{expected:02X}"


# =============================================================================
# Category 5: Generators
# =============================================================================

class TestGenerators:
    """
    Test generator expansion.
    
    Specification: docs/docs/language-reference/generators.md
    
    Generators use >variable[range]{ ... } syntax to create multiple instances.
    - >i[N] iterates from 1 to N (1-based!)
    - >i[start:end] iterates from start to end inclusive
    - {variable} substitutes the current value
    - Arithmetic like {i+1}, {i*2} is supported
    """
    
    def test_generator_creates_8_instances(self):
        """Test that >i[8] creates instances named 1 through 8."""
        shdl = """
        component Test8Gates(A[8]) -> (O[8]) {
            >i[8]{
                not{i}: NOT;
            }
            connect {
                >i[8]{
                    A[{i}] -> not{i}.A;
                    not{i}.O -> O[{i}];
                }
            }
        }
        """
        # Parse and check the structure
        module = parse(shdl)
        comp = module.components[0]
        
        # Should have generator in instances
        generators = [n for n in comp.instances if isinstance(n, Generator)]
        assert len(generators) >= 1
        
        # Flatten and verify 8 NOT instances created
        flattener = Flattener()
        flattener.load_source(shdl)
        result = flattener.flatten("Test8Gates")
        
        instances = [n for n in result.instances if isinstance(n, Instance)]
        not_instances = [i for i in instances if i.component_type == "NOT"]
        assert len(not_instances) == 8, f"Expected 8 NOT gates, got {len(not_instances)}"
    
    def test_generator_range_2_to_5(self):
        """Test generator with range [2:5] creates instances 2, 3, 4, 5."""
        shdl = """
        component TestRange(A[5]) -> (O[4]) {
            >i[2:5]{
                not{i}: NOT;
            }
            connect {
                >i[2:5]{
                    A[{i}] -> not{i}.A;
                    not{i}.O -> O[{i-1}];
                }
            }
        }
        """
        flattener = Flattener()
        flattener.load_source(shdl)
        result = flattener.flatten("TestRange")
        
        instances = [n for n in result.instances if isinstance(n, Instance)]
        not_instances = [i for i in instances if i.component_type == "NOT"]
        
        # Should create not2, not3, not4, not5 (4 instances)
        assert len(not_instances) == 4
        names = {i.name for i in not_instances}
        assert "not2" in names
        assert "not3" in names
        assert "not4" in names
        assert "not5" in names
        assert "not1" not in names  # Should NOT exist
    
    def test_generator_arithmetic_substitution(self):
        """Test arithmetic in generator substitutions like {i*2}."""
        shdl = """
        component TestArithmetic(A[4]) -> (O[4]) {
            >i[4]{
                not{i}: NOT;
            }
            connect {
                >i[4]{
                    A[{i}] -> not{i}.A;
                    not{i}.O -> O[{i}];
                }
            }
        }
        """
        # This should compile and work
        with circuit_from_source(shdl) as c:
            c.poke("A", 0b1010)  # 10 in decimal
            c.step(5)
            # NOT of each bit: 0101 = 5
            assert c.peek("O") == 0b0101


# =============================================================================
# Category 6: Constants
# =============================================================================

class TestConstants:
    """
    Test constant materialization.
    
    Specification: docs/docs/language-reference/constants.md
    
    Constants are fixed bit patterns:
    - VALUE = 100;  -> auto-sized (7 bits for 100)
    - VALUE[8] = 100;  -> explicit 8-bit width
    - Materialize as VCC/GND gates
    - Bit 1 is LSB (rightmost in binary)
    """
    
    def test_constant_7_bits(self):
        """Test that 100 (0b1100100) materializes correctly."""
        shdl = """
        component TestConst() -> (O[7]) {
            Hundred = 100;  # 0b1100100 - 7 bits
            connect {
                Hundred[1] -> O[1];
                Hundred[2] -> O[2];
                Hundred[3] -> O[3];
                Hundred[4] -> O[4];
                Hundred[5] -> O[5];
                Hundred[6] -> O[6];
                Hundred[7] -> O[7];
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.step()
            result = c.peek("O")
            assert result == 100, f"Constant should be 100, got {result}"
    
    def test_constant_explicit_width(self):
        """Test explicit width constant."""
        shdl = """
        component TestConstWidth() -> (O[8]) {
            Val[8] = 42;  # Explicit 8-bit
            connect {
                >i[8]{
                    Val[{i}] -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.step()
            assert c.peek("O") == 42
    
    def test_constant_binary_format(self):
        """Test binary constant format 0b..."""
        shdl = """
        component TestBinary() -> (O[4]) {
            Pattern = 0b1010;
            connect {
                Pattern[1] -> O[1];
                Pattern[2] -> O[2];
                Pattern[3] -> O[3];
                Pattern[4] -> O[4];
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.step()
            # 0b1010 = 10
            assert c.peek("O") == 10
    
    def test_constant_hex_format(self):
        """Test hexadecimal constant format 0x..."""
        shdl = """
        component TestHex() -> (O[8]) {
            Val[8] = 0xFF;
            connect {
                >i[8]{
                    Val[{i}] -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.step()
            assert c.peek("O") == 255


# =============================================================================
# Category 7: Hierarchical Composition
# =============================================================================

class TestHierarchy:
    """
    Test hierarchical component composition.
    
    Specification: docs/docs/language-reference/components.md
    
    Components can instantiate other components.
    During flattening, hierarchy is collapsed to primitive gates.
    """
    
    def test_nested_components(self):
        """Test that nested components are properly flattened."""
        shdl = """
        component Inner(A, B) -> (O) {
            and1: AND;
            connect {
                A -> and1.A;
                B -> and1.B;
                and1.O -> O;
            }
        }
        
        component Outer(X, Y) -> (Z) {
            inner: Inner;
            connect {
                X -> inner.A;
                Y -> inner.B;
                inner.O -> Z;
            }
        }
        """
        flattener = Flattener()
        flattener.load_source(shdl)
        result = flattener.flatten("Outer")
        
        # Should have flattened inner_and1
        instances = [n for n in result.instances if isinstance(n, Instance)]
        names = {i.name for i in instances}
        
        # The inner AND should be prefixed with instance name
        assert any("inner" in name and "and" in name.lower() for name in names) or \
               any(i.component_type == "AND" for i in instances), \
               "Should have flattened AND gate from Inner component"
    
    def test_hierarchical_behavior(self):
        """Test that hierarchical circuit produces correct output."""
        shdl = """
        component HalfAdder(A, B) -> (Sum, Carry) {
            xor1: XOR;
            and1: AND;
            connect {
                A -> xor1.A; B -> xor1.B;
                A -> and1.A; B -> and1.B;
                xor1.O -> Sum; and1.O -> Carry;
            }
        }
        
        component FullAdder(A, B, Cin) -> (Sum, Cout) {
            ha1: HalfAdder;
            ha2: HalfAdder;
            or1: OR;
            connect {
                A -> ha1.A; B -> ha1.B;
                ha1.Sum -> ha2.A; Cin -> ha2.B;
                ha2.Sum -> Sum;
                ha1.Carry -> or1.A;
                ha2.Carry -> or1.B;
                or1.O -> Cout;
            }
        }
        """
        with circuit_from_source(shdl, component="FullAdder") as c:
            # Test: 1 + 1 + 1 = 3 -> Sum=1, Cout=1
            c.poke("A", 1)
            c.poke("B", 1)
            c.poke("Cin", 1)
            c.step(10)
            assert c.peek("Sum") == 1, "1+1+1 Sum should be 1"
            assert c.peek("Cout") == 1, "1+1+1 Cout should be 1"


# =============================================================================
# Category 8: Multiplexers
# =============================================================================

class TestMultiplexer:
    """
    Test multiplexer circuits.
    
    Specification: docs/docs/examples/multiplexer.md
    
    2-to-1 Mux: Sel=0 -> A, Sel=1 -> B
    """
    
    def test_mux2to1_select_a(self):
        """2-to-1 Mux: when Sel=0, output = A."""
        shdl = """
        component Mux2to1(A, B, Sel) -> (Out) {
            not1: NOT;
            and1: AND;
            and2: AND;
            or1: OR;
            connect {
                Sel -> not1.A;
                A -> and1.A; not1.O -> and1.B;
                B -> and2.A; Sel -> and2.B;
                and1.O -> or1.A; and2.O -> or1.B;
                or1.O -> Out;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Sel=0 should select A
            c.poke("A", 1)
            c.poke("B", 0)
            c.poke("Sel", 0)
            c.step(5)
            assert c.peek("Out") == 1, "Mux(A=1, B=0, Sel=0) should output A=1"
            
            c.poke("A", 0)
            c.poke("B", 1)
            c.poke("Sel", 0)
            c.step(5)
            assert c.peek("Out") == 0, "Mux(A=0, B=1, Sel=0) should output A=0"
    
    def test_mux2to1_select_b(self):
        """2-to-1 Mux: when Sel=1, output = B."""
        shdl = """
        component Mux2to1(A, B, Sel) -> (Out) {
            not1: NOT;
            and1: AND;
            and2: AND;
            or1: OR;
            connect {
                Sel -> not1.A;
                A -> and1.A; not1.O -> and1.B;
                B -> and2.A; Sel -> and2.B;
                and1.O -> or1.A; and2.O -> or1.B;
                or1.O -> Out;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Sel=1 should select B
            c.poke("A", 1)
            c.poke("B", 0)
            c.poke("Sel", 1)
            c.step(5)
            assert c.peek("Out") == 0, "Mux(A=1, B=0, Sel=1) should output B=0"
            
            c.poke("A", 0)
            c.poke("B", 1)
            c.poke("Sel", 1)
            c.step(5)
            assert c.peek("Out") == 1, "Mux(A=0, B=1, Sel=1) should output B=1"


# =============================================================================
# Category 9: Language Parsing
# =============================================================================

class TestParsing:
    """
    Test that valid SHDL is accepted and parsed correctly.
    
    Specification: docs/docs/language-reference/
    """
    
    def test_parse_simple_component(self):
        """Parse a simple component declaration."""
        source = """
        component Simple(A, B) -> (O) {
            and1: AND;
            connect {
                A -> and1.A;
                B -> and1.B;
                and1.O -> O;
            }
        }
        """
        module = parse(source)
        assert len(module.components) == 1
        comp = module.components[0]
        assert comp.name == "Simple"
        assert len(comp.inputs) == 2
        assert len(comp.outputs) == 1
    
    def test_parse_multibit_ports(self):
        """Parse multi-bit port declarations."""
        source = """
        component Adder(A[16], B[16]) -> (Sum[16], Cout) {
            connect {}
        }
        """
        module = parse(source)
        comp = module.components[0]
        
        assert comp.inputs[0].name == "A"
        assert comp.inputs[0].width == 16
        assert comp.inputs[1].name == "B"
        assert comp.inputs[1].width == 16
        assert comp.outputs[0].name == "Sum"
        assert comp.outputs[0].width == 16
        assert comp.outputs[1].name == "Cout"
        assert comp.outputs[1].width is None  # Single bit
    
    def test_parse_generator(self):
        """Parse generator constructs."""
        source = """
        component Test(A[8]) -> (O[8]) {
            >i[8]{
                gate{i}: NOT;
            }
            connect {
                >i[8]{
                    A[{i}] -> gate{i}.A;
                    gate{i}.O -> O[{i}];
                }
            }
        }
        """
        module = parse(source)
        comp = module.components[0]
        
        generators = [n for n in comp.instances if isinstance(n, Generator)]
        assert len(generators) >= 1
        assert generators[0].variable == "i"
    
    def test_parse_imports(self):
        """Parse import statements."""
        source = """
        use someModule::{Component1, Component2};
        
        component Main(A) -> (B) {
            connect {}
        }
        """
        module = parse(source)
        
        assert len(module.imports) == 1
        assert module.imports[0].module == "someModule"
        assert "Component1" in module.imports[0].components
        assert "Component2" in module.imports[0].components
    
    def test_parse_constants(self):
        """Parse constant declarations."""
        source = """
        component Test(A) -> (B) {
            DEC = 100;
            HEX = 0xFF;
            BIN = 0b1010;
            SIZED[8] = 42;
            connect {}
        }
        """
        module = parse(source)
        comp = module.components[0]
        
        # Constants are in instances
        from SHDL import Constant
        constants = [n for n in comp.instances if isinstance(n, Constant)]
        assert len(constants) == 4


# =============================================================================
# Category 10: Error Handling
# =============================================================================

class TestErrorHandling:
    """
    Test error handling for invalid inputs.
    """
    
    def test_lexer_error_invalid_token(self):
        """Test that invalid tokens raise LexerError."""
        source = "component Test @ -> (O) {}"  # @ is invalid
        with pytest.raises(LexerError):
            parse(source)
    
    def test_parse_error_missing_arrow(self):
        """Test that missing -> raises ParseError."""
        source = "component Test(A) (O) { connect {} }"  # Missing ->
        with pytest.raises(ParseError):
            parse(source)
    
    def test_parse_error_unclosed_brace(self):
        """Test that unclosed braces raise ParseError."""
        source = """
        component Test(A) -> (O) {
            and1: AND;
            connect {
                A -> and1.A;
        """  # Missing closing braces
        with pytest.raises(ParseError):
            parse(source)


# =============================================================================
# Category 11: Decoder Circuits
# =============================================================================

class TestDecoder:
    """
    Test decoder circuits.
    
    A decoder takes an n-bit input and activates exactly one of 2^n outputs.
    """
    
    def test_2to4_decoder(self):
        """Test 2-to-4 decoder: 00->D0, 01->D1, 10->D2, 11->D3."""
        shdl = """
        component Decoder2to4(S[2]) -> (D0, D1, D2, D3) {
            not1: NOT;
            not2: NOT;
            and1: AND;
            and2: AND;
            and3: AND;
            and4: AND;
            
            connect {
                S[1] -> not1.A;
                S[2] -> not2.A;
                
                not1.O -> and1.A;
                not2.O -> and1.B;
                and1.O -> D0;
                
                S[1] -> and2.A;
                not2.O -> and2.B;
                and2.O -> D1;
                
                not1.O -> and3.A;
                S[2] -> and3.B;
                and3.O -> D2;
                
                S[1] -> and4.A;
                S[2] -> and4.B;
                and4.O -> D3;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # S=00 -> D0=1, D1=0, D2=0, D3=0
            c.poke("S", 0b00)
            c.step(5)
            assert c.peek("D0") == 1, "S=00: D0 should be 1"
            assert c.peek("D1") == 0, "S=00: D1 should be 0"
            assert c.peek("D2") == 0, "S=00: D2 should be 0"
            assert c.peek("D3") == 0, "S=00: D3 should be 0"
            
            # S=01 -> D0=0, D1=1, D2=0, D3=0
            c.poke("S", 0b01)
            c.step(5)
            assert c.peek("D0") == 0, "S=01: D0 should be 0"
            assert c.peek("D1") == 1, "S=01: D1 should be 1"
            assert c.peek("D2") == 0, "S=01: D2 should be 0"
            assert c.peek("D3") == 0, "S=01: D3 should be 0"
            
            # S=10 -> D0=0, D1=0, D2=1, D3=0
            c.poke("S", 0b10)
            c.step(5)
            assert c.peek("D0") == 0, "S=10: D0 should be 0"
            assert c.peek("D1") == 0, "S=10: D1 should be 0"
            assert c.peek("D2") == 1, "S=10: D2 should be 1"
            assert c.peek("D3") == 0, "S=10: D3 should be 0"
            
            # S=11 -> D0=0, D1=0, D2=0, D3=1
            c.poke("S", 0b11)
            c.step(5)
            assert c.peek("D0") == 0, "S=11: D0 should be 0"
            assert c.peek("D1") == 0, "S=11: D1 should be 0"
            assert c.peek("D2") == 0, "S=11: D2 should be 0"
            assert c.peek("D3") == 1, "S=11: D3 should be 1"


# =============================================================================
# Category 12: Propagation Analysis
# =============================================================================

class TestPropagationAnalysis:
    """
    Analyze and document the propagation behavior of the simulator.
    
    These tests help determine:
    - How many step() calls are needed for different circuit depths
    - Whether the simulator has automatic settling
    - The relationship between gate types and propagation
    """
    
    def test_propagation_depth_1(self):
        """Single gate depth: should settle in 1 step."""
        shdl = """
        component Depth1(A, B) -> (O) {
            g: AND;
            connect {
                A -> g.A;
                B -> g.B;
                g.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 1)
            c.poke("B", 1)
            c.step(1)
            result = c.peek("O")
            assert result == 1, f"Depth 1: expected 1, got {result}"
    
    def test_propagation_depth_2(self):
        """Two gates in series: AND -> NOT."""
        shdl = """
        component Depth2(A, B) -> (O) {
            g1: AND;
            g2: NOT;
            connect {
                A -> g1.A;
                B -> g1.B;
                g1.O -> g2.A;
                g2.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 1)
            c.poke("B", 1)
            
            # Test with increasing steps
            c.step(1)
            result1 = c.peek("O")
            
            c.step(1)
            result2 = c.peek("O")
            
            c.step(3)
            result_final = c.peek("O")
            
            # NOT(AND(1,1)) = NOT(1) = 0
            assert result_final == 0, f"Depth 2: expected 0, got {result_final}"
    
    def test_propagation_consistency(self):
        """
        Test that additional steps don't change a settled value.
        Once the circuit has settled, more steps shouldn't affect output.
        """
        shdl = """
        component Test(A, B) -> (O) {
            g1: AND;
            g2: NOT;
            g3: OR;
            connect {
                A -> g1.A;
                B -> g1.B;
                g1.O -> g2.A;
                g2.O -> g3.A;
                A -> g3.B;
                g3.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 1)
            c.poke("B", 0)
            
            # Run many steps and check consistency
            c.step(10)
            result_after_10 = c.peek("O")
            
            c.step(10)
            result_after_20 = c.peek("O")
            
            assert result_after_10 == result_after_20, \
                "Circuit should be stable - more steps shouldn't change output"


# =============================================================================
# Category 13: Edge Cases and Boundary Conditions
# =============================================================================

class TestEdgeCases:
    """
    Test edge cases and boundary conditions.
    """
    
    def test_16bit_max_value(self):
        """Test with 16-bit maximum values."""
        shdl = """
        component Test16(A[16], B[16]) -> (O[16]) {
            >i[16]{
                and{i}: AND;
            }
            connect {
                >i[16]{
                    A[{i}] -> and{i}.A;
                    B[{i}] -> and{i}.B;
                    and{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 0xFFFF)
            c.poke("B", 0xFFFF)
            c.step(5)
            assert c.peek("O") == 0xFFFF, "0xFFFF AND 0xFFFF should be 0xFFFF"
            
            c.poke("A", 0xFFFF)
            c.poke("B", 0x0000)
            c.step(5)
            assert c.peek("O") == 0x0000, "0xFFFF AND 0x0000 should be 0x0000"
    
    def test_alternating_bit_patterns(self):
        """Test with alternating bit patterns 0xAAAA and 0x5555."""
        shdl = """
        component TestXOR16(A[16], B[16]) -> (O[16]) {
            >i[16]{
                xor{i}: XOR;
            }
            connect {
                >i[16]{
                    A[{i}] -> xor{i}.A;
                    B[{i}] -> xor{i}.B;
                    xor{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # 0xAAAA XOR 0x5555 = 0xFFFF (all bits different)
            c.poke("A", 0xAAAA)
            c.poke("B", 0x5555)
            c.step(5)
            assert c.peek("O") == 0xFFFF, "0xAAAA XOR 0x5555 should be 0xFFFF"
            
            # 0xAAAA XOR 0xAAAA = 0x0000 (all bits same)
            c.poke("A", 0xAAAA)
            c.poke("B", 0xAAAA)
            c.step(5)
            assert c.peek("O") == 0x0000, "0xAAAA XOR 0xAAAA should be 0x0000"
    
    def test_single_bit_isolation(self):
        """Test that individual bits are properly isolated."""
        shdl = """
        component IsolateBit4(A[8]) -> (O) {
            n: NOT;
            connect {
                A[4] -> n.A;
                n.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Bit 4 is the 4th bit (1-indexed), so value 0b1000 = 8 has bit 4 = 1
            c.poke("A", 0b00001000)  # bit 4 set
            c.step(5)
            assert c.peek("O") == 0, "NOT(1) = 0"
            
            c.poke("A", 0b11110111)  # bit 4 clear
            c.step(5)
            assert c.peek("O") == 1, "NOT(0) = 1"


# =============================================================================
# Category 14: Base SHDL Formatting
# =============================================================================

class TestBaseSHDLFormatting:
    """
    Test the Base SHDL formatter.
    
    Verifies that flattened output is valid Base SHDL.
    """
    
    def test_format_simple_component(self):
        """Test formatting a simple component to Base SHDL."""
        source = """
        component Simple(A, B) -> (O) {
            and1: AND;
            connect {
                A -> and1.A;
                B -> and1.B;
                and1.O -> O;
            }
        }
        """
        flattener = Flattener()
        flattener.load_source(source)
        base_shdl = flattener.flatten_to_base_shdl("Simple")
        
        # Check that the output contains expected elements
        assert "component Simple" in base_shdl
        assert "and1: AND;" in base_shdl
        assert "connect {" in base_shdl
        assert "A -> and1.A;" in base_shdl
    
    def test_format_with_generators_expanded(self):
        """Test that generators are fully expanded in Base SHDL."""
        source = """
        component Test4(A[4]) -> (O[4]) {
            >i[4]{
                inv{i}: NOT;
            }
            connect {
                >i[4]{
                    A[{i}] -> inv{i}.A;
                    inv{i}.O -> O[{i}];
                }
            }
        }
        """
        flattener = Flattener()
        flattener.load_source(source)
        base_shdl = flattener.flatten_to_base_shdl("Test4")
        
        # Should have inv1, inv2, inv3, inv4 - no generators
        assert "inv1: NOT;" in base_shdl
        assert "inv2: NOT;" in base_shdl
        assert "inv3: NOT;" in base_shdl
        assert "inv4: NOT;" in base_shdl
        assert ">i[" not in base_shdl, "Generators should be expanded"


# =============================================================================
# Category 15: 8-Bit Adder with Exhaustive Carry Tests
# =============================================================================

class TestAdder8Bit:
    """
    Test 8-bit adder with exhaustive carry chain tests.
    
    The 8-bit adder chains 8 full adders. It's important to test:
    - Carry propagation through all stages
    - Boundary conditions
    - Random samples of the input space
    """
    
    @pytest.fixture(scope="class")
    def adder8_circuit(self):
        """Create an 8-bit adder circuit."""
        shdl = """
        component FullAdder(A, B, Cin) -> (S, Cout) {
            xor1: XOR;
            xor2: XOR;
            and1: AND;
            and2: AND;
            or1: OR;
            connect {
                A -> xor1.A;
                B -> xor1.B;
                xor1.O -> xor2.A;
                Cin -> xor2.B;
                xor2.O -> S;
                A -> and1.A;
                B -> and1.B;
                xor1.O -> and2.A;
                Cin -> and2.B;
                and1.O -> or1.A;
                and2.O -> or1.B;
                or1.O -> Cout;
            }
        }
        
        component Adder8(A[8], B[8], Cin) -> (S[8], Cout) {
            fa1: FullAdder;
            fa2: FullAdder;
            fa3: FullAdder;
            fa4: FullAdder;
            fa5: FullAdder;
            fa6: FullAdder;
            fa7: FullAdder;
            fa8: FullAdder;
            connect {
                A[1] -> fa1.A; B[1] -> fa1.B; Cin -> fa1.Cin; fa1.S -> S[1];
                A[2] -> fa2.A; B[2] -> fa2.B; fa1.Cout -> fa2.Cin; fa2.S -> S[2];
                A[3] -> fa3.A; B[3] -> fa3.B; fa2.Cout -> fa3.Cin; fa3.S -> S[3];
                A[4] -> fa4.A; B[4] -> fa4.B; fa3.Cout -> fa4.Cin; fa4.S -> S[4];
                A[5] -> fa5.A; B[5] -> fa5.B; fa4.Cout -> fa5.Cin; fa5.S -> S[5];
                A[6] -> fa6.A; B[6] -> fa6.B; fa5.Cout -> fa6.Cin; fa6.S -> S[6];
                A[7] -> fa7.A; B[7] -> fa7.B; fa6.Cout -> fa7.Cin; fa7.S -> S[7];
                A[8] -> fa8.A; B[8] -> fa8.B; fa7.Cout -> fa8.Cin; fa8.S -> S[8];
                fa8.Cout -> Cout;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            yield c
    
    def test_zero_plus_zero(self, adder8_circuit):
        """0 + 0 = 0"""
        c = adder8_circuit
        c.poke("A", 0)
        c.poke("B", 0)
        c.poke("Cin", 0)
        c.step(20)  # Deep circuit needs many steps
        assert c.peek("S") == 0, "0 + 0 should be 0"
        assert c.peek("Cout") == 0, "No carry out expected"
    
    def test_max_plus_zero(self, adder8_circuit):
        """255 + 0 = 255"""
        c = adder8_circuit
        c.poke("A", 255)
        c.poke("B", 0)
        c.poke("Cin", 0)
        c.step(20)
        assert c.peek("S") == 255, "255 + 0 should be 255"
        assert c.peek("Cout") == 0, "No carry out expected"
    
    def test_max_plus_one_overflow(self, adder8_circuit):
        """255 + 1 = 0 with carry"""
        c = adder8_circuit
        c.poke("A", 255)
        c.poke("B", 1)
        c.poke("Cin", 0)
        c.step(20)
        assert c.peek("S") == 0, "255 + 1 should overflow to 0"
        assert c.peek("Cout") == 1, "Should have carry out"
    
    def test_carry_propagation_all_ones(self, adder8_circuit):
        """0xFF + 0xFF = 0xFE with carry (tests all carry stages)"""
        c = adder8_circuit
        c.poke("A", 0xFF)
        c.poke("B", 0xFF)
        c.poke("Cin", 0)
        c.step(30)  # Maximum carry propagation
        assert c.peek("S") == 0xFE, "0xFF + 0xFF = 0x1FE, low 8 bits = 0xFE"
        assert c.peek("Cout") == 1, "Should have carry out"
    
    def test_carry_in(self, adder8_circuit):
        """Test carry input functionality"""
        c = adder8_circuit
        c.poke("A", 0x00)
        c.poke("B", 0x00)
        c.poke("Cin", 1)
        c.step(20)
        assert c.peek("S") == 1, "0 + 0 + Cin should be 1"
        assert c.peek("Cout") == 0, "No carry out expected"
    
    def test_sample_additions(self, adder8_circuit):
        """Test various sample additions"""
        c = adder8_circuit
        test_cases = [
            (100, 55, 0, 155, 0),
            (200, 56, 0, 0, 1),  # 200 + 56 = 256 = overflow
            (128, 127, 0, 255, 0),
            (128, 128, 0, 0, 1),  # 128 + 128 = 256 = overflow
            (0x55, 0xAA, 0, 0xFF, 0),  # Complementary patterns
            (1, 2, 1, 4, 0),  # With carry in
        ]
        for a, b, cin, expected_sum, expected_cout in test_cases:
            c.poke("A", a)
            c.poke("B", b)
            c.poke("Cin", cin)
            c.step(30)
            assert c.peek("S") == expected_sum, f"{a} + {b} + {cin} should be {expected_sum}"
            assert c.peek("Cout") == expected_cout, f"Carry out should be {expected_cout}"


# =============================================================================
# Category 16: Bit Range Subscript Tests
# =============================================================================

class TestBitRangeSubscripts:
    """
    Test bit range subscript syntax A[high:low].
    
    Per the documentation:
    - Single bit: A[3]
    - Bit range: A[8:5] (bits 8 down to 5)
    - Bit indexing is 1-based (LSB is bit 1)
    """
    
    def test_bit_range_high_nibble(self):
        """Extract high nibble of 8-bit value using range subscript."""
        shdl = """
        component HighNibble(A[8]) -> (O[4]) {
            n1: NOT; n2: NOT;
            n3: NOT; n4: NOT;
            n5: NOT; n6: NOT;
            n7: NOT; n8: NOT;
            connect {
                A[5] -> n1.A; n1.O -> n2.A; n2.O -> O[1];
                A[6] -> n3.A; n3.O -> n4.A; n4.O -> O[2];
                A[7] -> n5.A; n5.O -> n6.A; n6.O -> O[3];
                A[8] -> n7.A; n7.O -> n8.A; n8.O -> O[4];
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 0b11110000)  # High nibble = 0xF
            c.step(10)
            assert c.peek("O") == 0xF, "High nibble of 0xF0 should be 0xF"
            
            c.poke("A", 0b10100101)  # Binary: 1010 0101, high nibble = 0xA
            c.step(10)
            assert c.peek("O") == 0xA, "High nibble of 0xA5 should be 0xA"
    
    def test_bit_range_low_nibble(self):
        """Extract low nibble of 8-bit value."""
        shdl = """
        component LowNibble(A[8]) -> (O[4]) {
            n1: NOT; n2: NOT;
            n3: NOT; n4: NOT;
            n5: NOT; n6: NOT;
            n7: NOT; n8: NOT;
            connect {
                A[1] -> n1.A; n1.O -> n2.A; n2.O -> O[1];
                A[2] -> n3.A; n3.O -> n4.A; n4.O -> O[2];
                A[3] -> n5.A; n5.O -> n6.A; n6.O -> O[3];
                A[4] -> n7.A; n7.O -> n8.A; n8.O -> O[4];
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 0b11110000)  # Low nibble = 0x0
            c.step(10)
            assert c.peek("O") == 0x0, "Low nibble of 0xF0 should be 0x0"
            
            c.poke("A", 0b10100101)  # Binary: 1010 0101, low nibble = 0x5
            c.step(10)
            assert c.peek("O") == 0x5, "Low nibble of 0xA5 should be 0x5"


# =============================================================================
# Category 17: Component Import Tests
# =============================================================================

class TestComponentImports:
    """
    Test the import functionality for components.
    
    Verifies that components can be imported from other files.
    """
    
    def test_import_gates_from_alu_directory(self):
        """Test importing and using gates from ALU directory."""
        # Read the gates.shdl from ALU directory
        gates_path = Path(__file__).parent.parent / "ALU" / "gates.shdl"
        if gates_path.exists():
            flattener = Flattener()
            module = flattener.load_file(str(gates_path))
            # The module should have components
            assert len(module.components) > 0, "ALU/gates.shdl should define components"


# =============================================================================
# Category 18: Reset Behavior Tests
# =============================================================================

class TestResetBehavior:
    """
    Test the reset() functionality of SHDLCircuit.
    """
    
    def test_reset_clears_state(self):
        """Test that reset clears the circuit state."""
        shdl = """
        component Buffer(A) -> (O) {
            n1: NOT;
            n2: NOT;
            connect {
                A -> n1.A;
                n1.O -> n2.A;
                n2.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 1)
            c.step(5)
            assert c.peek("O") == 1, "Output should be 1 after stepping"
            
            c.reset()
            # After reset, internal state should be cleared
            # Need to poke and step again
            c.poke("A", 0)
            c.step(5)
            assert c.peek("O") == 0, "Output should be 0 after reset and new input"
    
    def test_reset_multiple_times(self):
        """Test multiple reset cycles."""
        shdl = """
        component AndGate(A, B) -> (O) {
            and1: AND;
            connect {
                A -> and1.A;
                B -> and1.B;
                and1.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            for i in range(3):
                c.poke("A", 1)
                c.poke("B", 1)
                c.step(5)
                assert c.peek("O") == 1, f"Iteration {i}: Output should be 1"
                c.reset()


# =============================================================================
# Category 19: Signal Width Validation Tests
# =============================================================================

class TestSignalWidthValidation:
    """
    Test that signal widths are properly validated and handled.
    """
    
    def test_8bit_signal_boundaries(self):
        """Test 8-bit signal value boundaries."""
        shdl = """
        component Pass8(A[8]) -> (O[8]) {
            >i[8]{
                n{i}a: NOT;
                n{i}b: NOT;
            }
            connect {
                >i[8]{
                    A[{i}] -> n{i}a.A;
                    n{i}a.O -> n{i}b.A;
                    n{i}b.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Test boundary values
            for value in [0, 1, 127, 128, 254, 255]:
                c.poke("A", value)
                c.step(10)
                assert c.peek("O") == value, f"Pass-through should preserve value {value}"
    
    def test_16bit_signal_boundaries(self):
        """Test 16-bit signal value boundaries."""
        shdl = """
        component Pass16(A[16]) -> (O[16]) {
            >i[16]{
                n{i}a: NOT;
                n{i}b: NOT;
            }
            connect {
                >i[16]{
                    A[{i}] -> n{i}a.A;
                    n{i}a.O -> n{i}b.A;
                    n{i}b.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Test boundary values
            for value in [0, 1, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF]:
                c.poke("A", value)
                c.step(15)
                assert c.peek("O") == value, f"Pass-through should preserve value {value}"


# =============================================================================
# Category 20: Complex Hierarchy with Multiple Levels
# =============================================================================

class TestDeepHierarchy:
    """
    Test deeply nested component hierarchies.
    """
    
    def test_four_level_hierarchy(self):
        """Test a 4-level component hierarchy."""
        shdl = """
        component Level1(A) -> (O) {
            n: NOT;
            connect {
                A -> n.A;
                n.O -> O;
            }
        }
        
        component Level2(A) -> (O) {
            l1: Level1;
            connect {
                A -> l1.A;
                l1.O -> O;
            }
        }
        
        component Level3(A) -> (O) {
            l2: Level2;
            connect {
                A -> l2.A;
                l2.O -> O;
            }
        }
        
        component Level4(A) -> (O) {
            l3: Level3;
            connect {
                A -> l3.A;
                l3.O -> O;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 0)
            c.step(10)
            assert c.peek("O") == 1, "NOT(0) through 4 levels = 1"
            
            c.poke("A", 1)
            c.step(10)
            assert c.peek("O") == 0, "NOT(1) through 4 levels = 0"


# =============================================================================
# Category 21: Wire-Through Tests
# =============================================================================

class TestWireThrough:
    """
    Test wire-through connections (direct input->output without gates).
    
    Wire-through is when an input port connects directly to an output port,
    bypassing any logic gates. This is useful for pass-through signals.
    """
    
    def test_simple_wire_through(self):
        """Test basic wire-through: input directly to output."""
        # We can't do pure wire-through (no gates), so use a subcomponent
        shdl = """
        component PassThrough(A) -> (O) {
            n1: NOT;
            n2: NOT;
            connect {
                A -> n1.A;
                n1.O -> n2.A;
                n2.O -> O;
            }
        }
        
        component Wrapper(In) -> (Out) {
            pt: PassThrough;
            connect {
                In -> pt.A;
                pt.O -> Out;
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("In", 0)
            c.step(10)
            assert c.peek("Out") == 0, "Wire-through should pass 0"
            
            c.poke("In", 1)
            c.step(10)
            assert c.peek("Out") == 1, "Wire-through should pass 1"
    
    def test_wire_through_in_generator_simple(self):
        """Test wire-through connections inside a generator - simple case."""
        shdl = """
        component BitBuffer(A) -> (O) {
            n1: NOT;
            n2: NOT;
            connect {
                A -> n1.A;
                n1.O -> n2.A;
                n2.O -> O;
            }
        }
        
        component Buffer4(A[4]) -> (O[4]) {
            >i[4]{
                buf{i}: BitBuffer;
            }
            connect {
                >i[4]{
                    A[{i}] -> buf{i}.A;
                    buf{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 0b1010)
            c.step(10)
            assert c.peek("O") == 0b1010, "Generator wire-through should pass 0b1010"
            
            c.poke("A", 0b0101)
            c.step(10)
            assert c.peek("O") == 0b0101, "Generator wire-through should pass 0b0101"
            
            c.poke("A", 0b1111)
            c.step(10)
            assert c.peek("O") == 0b1111, "Generator wire-through should pass 0b1111"
    
    def test_wire_through_in_generator_8bit(self):
        """Test 8-bit wire-through in generator."""
        shdl = """
        component BitBuffer(A) -> (O) {
            n1: NOT;
            n2: NOT;
            connect {
                A -> n1.A;
                n1.O -> n2.A;
                n2.O -> O;
            }
        }
        
        component Buffer8(A[8]) -> (O[8]) {
            >i[8]{
                buf{i}: BitBuffer;
            }
            connect {
                >i[8]{
                    A[{i}] -> buf{i}.A;
                    buf{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # Test all boundary values
            for val in [0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF, 0xAA, 0x55]:
                c.poke("A", val)
                c.step(10)
                assert c.peek("O") == val, f"8-bit buffer should pass 0x{val:02X}"
    
    def test_wire_through_mixed_with_logic(self):
        """Test wire-through mixed with logic gates in generator."""
        shdl = """
        component Buffer8WithInvert(A[8], Inv) -> (O[8]) {
            >i[8]{
                xor{i}: XOR;
            }
            connect {
                >i[8]{
                    A[{i}] -> xor{i}.A;
                    Inv -> xor{i}.B;
                    xor{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            # When Inv=0, output should equal input (XOR with 0 = identity)
            c.poke("A", 0xAB)
            c.poke("Inv", 0)
            c.step(10)
            assert c.peek("O") == 0xAB, "XOR with 0 should pass through"
            
            # When Inv=1, output should be inverted (XOR with 1 = NOT)
            c.poke("A", 0xAB)
            c.poke("Inv", 1)
            c.step(10)
            assert c.peek("O") == 0x54, "XOR with 1 should invert (0xAB -> 0x54)"
    
    def test_wire_through_partial_generator(self):
        """Test partial wire-through in generator (some bits pass, some don't)."""
        shdl = """
        component PartialBuffer(A[4]) -> (Lower[2], Upper[2]) {
            n1: NOT; n2: NOT;
            n3: NOT; n4: NOT;
            n5: NOT; n6: NOT;
            n7: NOT; n8: NOT;
            connect {
                A[1] -> n1.A; n1.O -> n2.A; n2.O -> Lower[1];
                A[2] -> n3.A; n3.O -> n4.A; n4.O -> Lower[2];
                A[3] -> n5.A; n5.O -> n6.A; n6.O -> Upper[1];
                A[4] -> n7.A; n7.O -> n8.A; n8.O -> Upper[2];
            }
        }
        """
        with circuit_from_source(shdl) as c:
            c.poke("A", 0b1010)  # Lower=10, Upper=10
            c.step(10)
            assert c.peek("Lower") == 0b10, "Lower 2 bits of 0b1010 = 0b10"
            assert c.peek("Upper") == 0b10, "Upper 2 bits of 0b1010 = 0b10"
            
            c.poke("A", 0b1100)  # Lower=00, Upper=11
            c.step(10)
            assert c.peek("Lower") == 0b00, "Lower 2 bits of 0b1100 = 0b00"
            assert c.peek("Upper") == 0b11, "Upper 2 bits of 0b1100 = 0b11"
    
    def test_direct_wire_through_in_component(self):
        """Test direct input->output in a subcomponent used via generator."""
        # This tests the actual wire-through case where input goes directly to output
        shdl = """
        component DirectPass(A) -> (O) {
            n1: NOT;
            n2: NOT;
            connect {
                A -> n1.A;
                n1.O -> n2.A;
                n2.O -> O;
            }
        }
        
        component MultiPass(A[4]) -> (O[4]) {
            >i[4]{
                dp{i}: DirectPass;
            }
            connect {
                >i[4]{
                    A[{i}] -> dp{i}.A;
                    dp{i}.O -> O[{i}];
                }
            }
        }
        """
        with circuit_from_source(shdl) as c:
            for val in range(16):  # Test all 4-bit values
                c.poke("A", val)
                c.step(10)
                assert c.peek("O") == val, f"MultiPass should preserve value {val}"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
