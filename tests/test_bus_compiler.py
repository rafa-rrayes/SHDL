"""
Bus compiler regression tests.

Tests for correctness bugs found during RAM256 development:
1. Cross-level gate grouping: nested decoders at different bit ranges
   of the same port were incorrectly merged by partition refinement,
   causing self-AND operations in generated C code.
2. Feedback handling: NOR latches in registers must work through the
   bus compiler path (not just debug builds).
3. Memory address isolation: writes to one address must not corrupt
   adjacent addresses — the symptom that revealed bug #1.
"""

import pytest
import tempfile
import os
from pathlib import Path
from contextlib import contextmanager

from SHDL import Circuit, parse, Flattener
from SHDL.bus_compiler.graph import ConnectionGraph
from SHDL.bus_compiler.analyzer import BusAnalyzer


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_DIR = PROJECT_ROOT / "Memory"


@contextmanager
def circuit_from_source(source, component=None):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".shdl", delete=False) as f:
        f.write(source)
        temp_path = f.name
    try:
        circuit = Circuit(temp_path, component=component)
        yield circuit
        circuit.close()
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


# ── Memory test helpers ─────────────────────────────────────────────

def write_mem(circuit, addr, data, addr_width=8):
    mask = (1 << (addr_width * 1)) - 1 if addr_width <= 8 else 0xFF
    circuit.poke("DataIn", data & 0xFFFFFFFF)
    circuit.poke("Addr", addr & mask)
    circuit.poke("WriteEnable", 1)
    circuit.poke("clk", 0)
    circuit.step(100)
    circuit.poke("clk", 1)
    circuit.step(100)
    circuit.poke("clk", 0)
    circuit.poke("WriteEnable", 0)
    circuit.step(100)


def read_mem(circuit, addr, addr_width=8):
    mask = (1 << (addr_width * 1)) - 1 if addr_width <= 8 else 0xFF
    circuit.poke("Addr", addr & mask)
    circuit.poke("WriteEnable", 0)
    circuit.poke("clk", 0)
    circuit.step(100)
    return circuit.peek("DataOut")


# ── Inline SHDL sources ────────────────────────────────────────────

DUAL_DECODER_SHDL = """\
component Decoder2(addr[2], en) -> (Out[4]) {
    not_a1: NOT; not_a2: NOT;
    dec1: AND; dec2: AND; dec3: AND; dec4: AND;
    en1: AND; en2: AND; en3: AND; en4: AND;
    connect {
        addr[1] -> not_a1.A; addr[2] -> not_a2.A;
        not_a1.O -> dec1.A; not_a2.O -> dec1.B;
        addr[1]  -> dec2.A; not_a2.O -> dec2.B;
        not_a1.O -> dec3.A; addr[2]  -> dec3.B;
        addr[1]  -> dec4.A; addr[2]  -> dec4.B;
        dec1.O -> en1.A; en -> en1.B; en1.O -> Out[1];
        dec2.O -> en2.A; en -> en2.B; en2.O -> Out[2];
        dec3.O -> en3.A; en -> en3.B; en3.O -> Out[3];
        dec4.O -> en4.A; en -> en4.B; en4.O -> Out[4];
    }
}

component DualDecoder(Addr[4], en) -> (Lo[4], Hi[4]) {
    dec_lo: Decoder2;
    dec_hi: Decoder2;
    connect {
        Addr[1] -> dec_lo.addr[1]; Addr[2] -> dec_lo.addr[2];
        en -> dec_lo.en;
        Addr[3] -> dec_hi.addr[1]; Addr[4] -> dec_hi.addr[2];
        en -> dec_hi.en;
        >i[4]{ dec_lo.Out[{i}] -> Lo[{i}]; }
        >i[4]{ dec_hi.Out[{i}] -> Hi[{i}]; }
    }
}
"""

# D-latch built from primitives (OR+NOT = NOR), no file dependencies
DLATCH_SHDL = """\
component DLatch1(D, clk) -> (Q) {
    a1: AND; a2: AND; inv_d: NOT;
    or1: OR; nor1: NOT;
    or2: OR; nor2: NOT;
    connect {
        D -> a1.A; clk -> a1.B;
        D -> inv_d.A;
        inv_d.O -> a2.A; clk -> a2.B;

        a1.O -> or1.A; nor2.O -> or1.B;
        or1.O -> nor1.A;

        a2.O -> or2.A; nor1.O -> or2.B;
        or2.O -> nor2.A;

        nor2.O -> Q;
    }
}

component DLatch8(D[8], clk) -> (Q[8]) {
    >i[8]{
        a1{i}: AND; a2{i}: AND; inv_d{i}: NOT;
        or1{i}: OR; nor1{i}: NOT;
        or2{i}: OR; nor2{i}: NOT;
    }
    connect {
        >i[8]{
            D[{i}] -> a1{i}.A; clk -> a1{i}.B;
            D[{i}] -> inv_d{i}.A;
            inv_d{i}.O -> a2{i}.A; clk -> a2{i}.B;

            a1{i}.O -> or1{i}.A; nor2{i}.O -> or1{i}.B;
            or1{i}.O -> nor1{i}.A;

            a2{i}.O -> or2{i}.A; nor1{i}.O -> or2{i}.B;
            or2{i}.O -> nor2{i}.A;

            nor2{i}.O -> Q[{i}];
        }
    }
}
"""

BITWISE_NOT8_SHDL = """\
component BitwiseNot8(A[8]) -> (Y[8]) {
    >i[8]{ n{i}: NOT; }
    connect { >i[8]{ A[{i}] -> n{i}.A; n{i}.O -> Y[{i}]; } }
}
"""

BITWISE_AND8_SHDL = """\
component BitwiseAnd8(A[8], B[8]) -> (Y[8]) {
    >i[8]{ g{i}: AND; }
    connect { >i[8]{ A[{i}] -> g{i}.A; B[{i}] -> g{i}.B; g{i}.O -> Y[{i}]; } }
}
"""

BITWISE_XOR8_SHDL = """\
component BitwiseXor8(A[8], B[8]) -> (Y[8]) {
    >i[8]{ g{i}: XOR; }
    connect { >i[8]{ A[{i}] -> g{i}.A; B[{i}] -> g{i}.B; g{i}.O -> Y[{i}]; } }
}
"""

SR_LATCH_SHDL = """\
component SRLatch(S, R) -> (Q, Qn) {
    or1: OR; nor1: NOT;
    or2: OR; nor2: NOT;
    connect {
        R -> or1.A; nor2.O -> or1.B;
        or1.O -> nor1.A;
        S -> or2.A; nor1.O -> or2.B;
        or2.O -> nor2.A;
        nor1.O -> Q; nor2.O -> Qn;
    }
}
"""


# ====================================================================
# 1. Cross-Level Decoder Tests (the primary bug scenario)
# ====================================================================

class TestNestedDecoders:
    """Two Decoder2 instances using different bit ranges of the same port.

    Before the alignment fix, partition refinement merged gates across
    the two decoders, producing self-AND operations (bus_not & bus_not)
    in the generated C code. Addresses where (addr & 3) != 0 failed.
    """

    def test_all_16_address_combinations(self):
        with circuit_from_source(DUAL_DECODER_SHDL, component="DualDecoder") as c:
            for addr in range(16):
                c.poke("Addr", addr)
                c.poke("en", 1)
                c.step(10)

                lo = c.peek("Lo")
                hi = c.peek("Hi")
                expected_lo = 1 << (addr & 3)
                expected_hi = 1 << ((addr >> 2) & 3)

                assert lo == expected_lo, (
                    f"addr={addr}: Lo={lo:04b} expected {expected_lo:04b}"
                )
                assert hi == expected_hi, (
                    f"addr={addr}: Hi={hi:04b} expected {expected_hi:04b}"
                )

    def test_enable_disables_both_decoders(self):
        with circuit_from_source(DUAL_DECODER_SHDL, component="DualDecoder") as c:
            for addr in range(16):
                c.poke("Addr", addr)
                c.poke("en", 0)
                c.step(10)
                assert c.peek("Lo") == 0
                assert c.peek("Hi") == 0

    def test_decoder_independence(self):
        """Changing high bits must not affect low decoder output."""
        with circuit_from_source(DUAL_DECODER_SHDL, component="DualDecoder") as c:
            c.poke("en", 1)
            for hi in range(4):
                addr = (hi << 2) | 1  # lo=1 fixed, hi varies
                c.poke("Addr", addr)
                c.step(10)
                assert c.peek("Lo") == 0b0010, (
                    f"Lo changed when hi={hi}: got {c.peek('Lo'):04b}"
                )

            for lo in range(4):
                addr = (2 << 2) | lo  # hi=2 fixed, lo varies
                c.poke("Addr", addr)
                c.step(10)
                assert c.peek("Hi") == 0b0100, (
                    f"Hi changed when lo={lo}: got {c.peek('Hi'):04b}"
                )

    def test_previously_failing_addresses(self):
        """Addresses where (addr & 3) != 0 were the original failure pattern."""
        with circuit_from_source(DUAL_DECODER_SHDL, component="DualDecoder") as c:
            c.poke("en", 1)
            for addr in [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15]:
                c.poke("Addr", addr)
                c.step(10)
                lo = c.peek("Lo")
                hi = c.peek("Hi")
                assert lo == (1 << (addr & 3)), (
                    f"REGRESSION addr={addr}: Lo={lo:04b}"
                )
                assert hi == (1 << ((addr >> 2) & 3)), (
                    f"REGRESSION addr={addr}: Hi={hi:04b}"
                )


# ====================================================================
# 2. Analyzer Unit Test — no self-AND in analysis result
# ====================================================================

class TestAnalyzerAlignment:
    """Verify the bus analyzer alignment check prevents self-AND patterns."""

    def test_no_self_and_in_nested_decoder(self):
        """No bus group should reference the same source for both A and B."""
        f = Flattener()
        f.load_source(DUAL_DECODER_SHDL)
        flat = f.flatten("DualDecoder")
        graph = ConnectionGraph.from_component(flat)
        result = BusAnalyzer(graph).analyze()

        for group in result.bus_groups:
            a_src = group.input_sources.get("A")
            b_src = group.input_sources.get("B")
            if a_src and b_src:
                if a_src.kind == "bus_group" and b_src.kind == "bus_group":
                    assert a_src.ref != b_src.ref, (
                        f"Self-AND in {group.name}: A and B both reference "
                        f"{a_src.ref}"
                    )

    def test_misaligned_source_falls_to_mixed(self):
        """When gates read non-sequential positions from a source group,
        the source must be classified as 'mixed', not 'bus_group'."""
        f = Flattener()
        f.load_source(DUAL_DECODER_SHDL)
        flat = f.flatten("DualDecoder")
        graph = ConnectionGraph.from_component(flat)
        result = BusAnalyzer(graph).analyze()

        for group in result.bus_groups:
            for port_name, src in group.input_sources.items():
                if src.kind == "bus_group":
                    # Verify the referenced positions are sequential
                    src_group = None
                    for g in result.bus_groups:
                        if g.name == src.ref:
                            src_group = g
                            break
                    assert src_group is not None

                    src_gate_pos = {
                        gate.name: i for i, gate in enumerate(src_group.gates)
                    }
                    positions = []
                    for gate in group.gates:
                        wire = gate.inputs.get(port_name)
                        if wire and wire.kind == "gate_output":
                            pos = src_gate_pos.get(wire.name)
                            if pos is not None:
                                positions.append(pos)

                    assert positions == list(range(len(positions))), (
                        f"{group.name}.{port_name} references {src.ref} at "
                        f"non-sequential positions {positions}"
                    )


# ====================================================================
# 3. Feedback / Latch Tests
# ====================================================================

class TestFeedbackCircuits:
    """NOR-latch feedback must work through the bus compiler path."""

    @pytest.mark.xfail(
        reason="Single-bit feedback circuits become singletons — bus compiler "
               "only detects feedback in bus groups (width >= 2). "
               "Use SHDBCircuit for single-bit latches.",
        raises=Exception,
    )
    def test_sr_latch_set_and_reset(self):
        with circuit_from_source(SR_LATCH_SHDL) as c:
            # Initial state after reset pulse
            c.poke("S", 0); c.poke("R", 1); c.step(20)
            assert c.peek("Q") == 0
            assert c.peek("Qn") == 1

            # Set
            c.poke("S", 1); c.poke("R", 0); c.step(20)
            assert c.peek("Q") == 1
            assert c.peek("Qn") == 0

            # Hold after set
            c.poke("S", 0); c.poke("R", 0); c.step(20)
            assert c.peek("Q") == 1
            assert c.peek("Qn") == 0

            # Reset
            c.poke("S", 0); c.poke("R", 1); c.step(20)
            assert c.peek("Q") == 0
            assert c.peek("Qn") == 1

            # Hold after reset
            c.poke("S", 0); c.poke("R", 0); c.step(20)
            assert c.peek("Q") == 0
            assert c.peek("Qn") == 1

    @pytest.mark.xfail(
        reason="Single-bit feedback: bus compiler only detects feedback in "
               "bus groups (width >= 2).",
        raises=Exception,
    )
    def test_dlatch_single_bit(self):
        with circuit_from_source(DLATCH_SHDL, component="DLatch1") as c:
            # Write 1
            c.poke("D", 1); c.poke("clk", 1); c.step(20)
            c.poke("clk", 0); c.step(20)
            assert c.peek("Q") == 1

            # Write 0
            c.poke("D", 0); c.poke("clk", 1); c.step(20)
            c.poke("clk", 0); c.step(20)
            assert c.peek("Q") == 0

            # Hold: change D while clock is low
            c.poke("D", 1); c.step(20)
            assert c.peek("Q") == 0, "Latch should hold when clk=0"

    def test_dlatch_8bit_all_patterns(self):
        """Write and read back all 256 values through an 8-bit D-latch."""
        with circuit_from_source(DLATCH_SHDL, component="DLatch8") as c:
            for val in range(256):
                c.poke("D", val)
                c.poke("clk", 1); c.step(20)
                c.poke("clk", 0); c.step(20)
                got = c.peek("Q")
                assert got == val, f"DLatch8: wrote {val:#04x}, read {got:#04x}"

    def test_dlatch_8bit_hold_on_clock_low(self):
        """D-latch must not change output when clock is low."""
        with circuit_from_source(DLATCH_SHDL, component="DLatch8") as c:
            # Store 0xAA
            c.poke("D", 0xAA); c.poke("clk", 1); c.step(20)
            c.poke("clk", 0); c.step(20)
            assert c.peek("Q") == 0xAA

            # Change D to 0x55 while clk=0 — must NOT update
            c.poke("D", 0x55); c.step(20)
            assert c.peek("Q") == 0xAA, "Latch updated while clk=0"


# ====================================================================
# 4. Bitwise Operation Tests
# ====================================================================

class TestBitwiseOperations:
    """Bus-width bitwise operations must produce correct results.

    These use bus grouping internally (8 NOT/AND/XOR gates → one bus group).
    """

    def test_bitwise_not_exhaustive(self):
        with circuit_from_source(BITWISE_NOT8_SHDL) as c:
            for a in range(256):
                c.poke("A", a)
                c.step(5)
                expected = (~a) & 0xFF
                got = c.peek("Y")
                assert got == expected, (
                    f"NOT(0x{a:02x})=0x{got:02x}, expected 0x{expected:02x}"
                )

    def test_bitwise_and_exhaustive(self):
        """Test all 65536 input combinations for 8-bit AND."""
        with circuit_from_source(BITWISE_AND8_SHDL) as c:
            for a in range(256):
                for b in range(256):
                    c.poke("A", a)
                    c.poke("B", b)
                    c.step(5)
                    expected = a & b
                    got = c.peek("Y")
                    assert got == expected, (
                        f"AND(0x{a:02x}, 0x{b:02x})=0x{got:02x}, "
                        f"expected 0x{expected:02x}"
                    )

    def test_bitwise_xor_sample_cases(self):
        with circuit_from_source(BITWISE_XOR8_SHDL) as c:
            cases = [
                (0x00, 0x00, 0x00), (0xFF, 0xFF, 0x00), (0xFF, 0x00, 0xFF),
                (0xAA, 0x55, 0xFF), (0xF0, 0x0F, 0xFF), (0x12, 0x34, 0x26),
                (0x01, 0x01, 0x00), (0x80, 0x80, 0x00), (0x37, 0xCA, 0xFD),
            ]
            for a, b, expected in cases:
                c.poke("A", a)
                c.poke("B", b)
                c.step(5)
                got = c.peek("Y")
                assert got == expected, (
                    f"XOR(0x{a:02x}, 0x{b:02x})=0x{got:02x}, "
                    f"expected 0x{expected:02x}"
                )


# ====================================================================
# 5. Register Tests (using Memory/ files)
# ====================================================================

memory_available = pytest.mark.skipif(
    not (MEMORY_DIR / "reg32.shdl").exists(),
    reason="Memory/ directory not available",
)


@memory_available
class TestReg32:
    """32-bit register through the bus compiler (not debug build)."""

    def test_store_and_recall(self):
        with Circuit(str(MEMORY_DIR / "reg32.shdl")) as reg:
            reg.poke("In", 0xDEADBEEF)
            reg.poke("clk", 1); reg.step(100)
            reg.poke("clk", 0); reg.step(100)
            assert reg.peek("Out") == 0xDEADBEEF

    def test_all_ones_and_zeros(self):
        with Circuit(str(MEMORY_DIR / "reg32.shdl")) as reg:
            reg.poke("In", 0xFFFFFFFF)
            reg.poke("clk", 1); reg.step(100)
            reg.poke("clk", 0); reg.step(100)
            assert reg.peek("Out") == 0xFFFFFFFF

            reg.poke("In", 0x00000000)
            reg.poke("clk", 1); reg.step(100)
            reg.poke("clk", 0); reg.step(100)
            assert reg.peek("Out") == 0x00000000

    def test_clock_gating(self):
        """Changing input while clock is low must not change output."""
        with Circuit(str(MEMORY_DIR / "reg32.shdl")) as reg:
            reg.poke("In", 0xAAAAAAAA)
            reg.poke("clk", 1); reg.step(100)
            reg.poke("clk", 0); reg.step(100)
            assert reg.peek("Out") == 0xAAAAAAAA

            # Change input without clocking
            reg.poke("In", 0x55555555)
            reg.step(100)
            assert reg.peek("Out") == 0xAAAAAAAA

    def test_alternating_patterns(self):
        """Write several patterns and verify each overwrites correctly."""
        patterns = [0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0x00000000, 0xFFFFFFFF]
        with Circuit(str(MEMORY_DIR / "reg32.shdl")) as reg:
            for val in patterns:
                reg.poke("In", val)
                reg.poke("clk", 1); reg.step(100)
                reg.poke("clk", 0); reg.step(100)
                assert reg.peek("Out") == val, f"Expected 0x{val:08X}"


# ====================================================================
# 6. Mem4 Tests (4-word × 32-bit memory)
# ====================================================================

@memory_available
class TestMem4:

    def test_write_read_all_addresses(self):
        test_data = {0: 0x11111111, 1: 0x22222222, 2: 0x33333333, 3: 0x44444444}
        with Circuit(str(MEMORY_DIR / "mem4.shdl")) as mem:
            for addr, val in test_data.items():
                write_mem(mem, addr, val, addr_width=2)
            for addr, expected in test_data.items():
                got = read_mem(mem, addr, addr_width=2)
                assert got == expected, (
                    f"Mem4 addr {addr}: 0x{got:08X} != 0x{expected:08X}"
                )

    def test_isolation(self):
        """Write to addr 0, verify addrs 1-3 remain zero."""
        with Circuit(str(MEMORY_DIR / "mem4.shdl")) as mem:
            write_mem(mem, 0, 0xFEEDFACE, addr_width=2)
            for addr in [1, 2, 3]:
                got = read_mem(mem, addr, addr_width=2)
                assert got == 0, (
                    f"Mem4 addr {addr} contaminated: 0x{got:08X}"
                )

    def test_overwrite(self):
        with Circuit(str(MEMORY_DIR / "mem4.shdl")) as mem:
            write_mem(mem, 2, 0xAAAAAAAA, addr_width=2)
            write_mem(mem, 2, 0xBBBBBBBB, addr_width=2)
            got = read_mem(mem, 2, addr_width=2)
            assert got == 0xBBBBBBBB


# ====================================================================
# 7. Mem16 Tests — the original failure scenario
# ====================================================================

@pytest.mark.skipif(
    not (MEMORY_DIR / "mem16.shdl").exists(),
    reason="Memory/mem16.shdl not available",
)
class TestMem16:
    """16-word × 32-bit memory — the circuit that exposed the bus compiler bug.

    Before the fix, addresses 1,2,3,6,7,10,11 failed because the bank
    select decoder and within-bank decoders shared incorrectly grouped
    NOT/AND gates.
    """

    def test_all_16_addresses_unique_values(self):
        """Write a unique value to each of 16 addresses, read all back."""
        with Circuit(str(MEMORY_DIR / "mem16.shdl")) as mem:
            for addr in range(16):
                val = ((addr + 1) * 0x11111111) & 0xFFFFFFFF
                write_mem(mem, addr, val, addr_width=4)
            for addr in range(16):
                expected = ((addr + 1) * 0x11111111) & 0xFFFFFFFF
                got = read_mem(mem, addr, addr_width=4)
                assert got == expected, (
                    f"Mem16 addr {addr}: 0x{got:08X} != 0x{expected:08X}"
                )

    def test_previously_failing_addresses(self):
        """Addresses 1,2,3,6,7,10,11 failed with the original bug."""
        failing_addrs = [1, 2, 3, 6, 7, 10, 11]
        with Circuit(str(MEMORY_DIR / "mem16.shdl")) as mem:
            for addr in failing_addrs:
                val = 0xF0000000 | addr
                write_mem(mem, addr, val, addr_width=4)
                got = read_mem(mem, addr, addr_width=4)
                assert got == val, (
                    f"REGRESSION addr {addr}: 0x{got:08X} != 0x{val:08X}"
                )

    def test_sequential_writes_dont_corrupt(self):
        """Writing to sequential addresses must not corrupt earlier writes."""
        with Circuit(str(MEMORY_DIR / "mem16.shdl")) as mem:
            # Write all 16 addresses in order
            for addr in range(16):
                write_mem(mem, addr, 0xA0000000 | (addr << 16), addr_width=4)

            # Verify in reverse order
            for addr in reversed(range(16)):
                expected = 0xA0000000 | (addr << 16)
                got = read_mem(mem, addr, addr_width=4)
                assert got == expected, (
                    f"Mem16 addr {addr} corrupted: 0x{got:08X} != "
                    f"0x{expected:08X}"
                )

    def test_bank_boundary_isolation(self):
        """Addresses at bank boundaries (0,4,8,12) must be independent."""
        with Circuit(str(MEMORY_DIR / "mem16.shdl")) as mem:
            boundary_data = {0: 0xAAAAAAAA, 4: 0xBBBBBBBB,
                             8: 0xCCCCCCCC, 12: 0xDDDDDDDD}
            for addr, val in boundary_data.items():
                write_mem(mem, addr, val, addr_width=4)
            for addr, expected in boundary_data.items():
                got = read_mem(mem, addr, addr_width=4)
                assert got == expected, (
                    f"Bank boundary addr {addr}: 0x{got:08X}"
                )

    def test_within_bank_isolation(self):
        """Addresses within the same bank (0-3) must be independent."""
        with Circuit(str(MEMORY_DIR / "mem16.shdl")) as mem:
            for addr in range(4):
                write_mem(mem, addr, (addr + 1) * 0x11111111, addr_width=4)
            for addr in range(4):
                expected = (addr + 1) * 0x11111111
                got = read_mem(mem, addr, addr_width=4)
                assert got == expected, (
                    f"Within-bank addr {addr}: 0x{got:08X}"
                )

    def test_cross_bank_no_leakage(self):
        """Write to bank 0 addr 1, verify bank 1 addr 1 (addr 5) is zero."""
        with Circuit(str(MEMORY_DIR / "mem16.shdl")) as mem:
            write_mem(mem, 1, 0xDEADBEEF, addr_width=4)
            got = read_mem(mem, 5, addr_width=4)
            assert got == 0, f"Cross-bank leakage: addr 5 = 0x{got:08X}"


# ====================================================================
# 8. RAM256 Integration Tests
# ====================================================================

@pytest.mark.skipif(
    not (MEMORY_DIR / "ram256.shdl").exists(),
    reason="Memory/ram256.shdl not available",
)
class TestRAM256:
    """Full 256×32-bit RAM through the bus compiler."""

    def test_basic_write_read(self):
        with Circuit(str(MEMORY_DIR / "ram256.shdl")) as ram:
            write_mem(ram, 0, 0xDEADBEEF)
            assert read_mem(ram, 0) == 0xDEADBEEF

    def test_spread_addresses(self):
        with Circuit(str(MEMORY_DIR / "ram256.shdl")) as ram:
            data = {0: 0xAAAAAAAA, 42: 0xBBBBBBBB, 100: 0xCCCCCCCC,
                    200: 0xDDDDDDDD, 255: 0xEEEEEEEE}
            for addr, val in data.items():
                write_mem(ram, addr, val)
            for addr, expected in data.items():
                got = read_mem(ram, addr)
                assert got == expected, (
                    f"RAM256 addr {addr}: 0x{got:08X} != 0x{expected:08X}"
                )

    def test_overwrite(self):
        with Circuit(str(MEMORY_DIR / "ram256.shdl")) as ram:
            write_mem(ram, 42, 0x11111111)
            write_mem(ram, 42, 0x22222222)
            assert read_mem(ram, 42) == 0x22222222

    def test_isolation_adjacent(self):
        with Circuit(str(MEMORY_DIR / "ram256.shdl")) as ram:
            write_mem(ram, 10, 0xFEEDFACE)
            assert read_mem(ram, 11) == 0, "Adjacent address contaminated"
            assert read_mem(ram, 10) == 0xFEEDFACE
