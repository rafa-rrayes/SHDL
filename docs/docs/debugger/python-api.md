---
sidebar_position: 9
---

# Python API

SHDB provides a Python API for programmatic debugging, test automation, and integration with other tools.

## Quick Start

```python
import shdb

# Load a circuit
circuit = shdb.Circuit("adder16.shdl")

# Basic operations
circuit.reset()
circuit.poke("A", 42)
circuit.poke("B", 17)
circuit.step()
print(circuit.peek("Sum"))  # 59

# Clean up
circuit.close()
```

## Loading Circuits

### from SHDL Source

```python
circuit = shdb.Circuit("myCircuit.shdl")
```

Compiles with `-g` automatically.

### From Compiled Library

```python
circuit = shdb.Circuit(
    library="libmyCircuit.dylib",
    debug_info="libmyCircuit.shdb"
)
```

### Context Manager

```python
with shdb.Circuit("adder16.shdl") as circuit:
    circuit.poke("A", 100)
    circuit.step()
    print(circuit.peek("Sum"))
# Automatically cleaned up
```

## Basic Operations

### Setting Values

```python
circuit.poke("A", 42)
circuit.poke("B", 0xFF)
circuit.poke("A", 0b10101010)

# Bit slicing
circuit.poke_bits("A", 1, 8, 0xFF)  # Set bits 1-8
```

### Reading Values

```python
value = circuit.peek("Sum")
cout = circuit.peek("Cout")

# Bit slicing
bit5 = circuit.peek_bit("Sum", 5)
upper = circuit.peek_bits("Sum", 8, 16)
```

### Simulation Control

```python
circuit.reset()           # Reset to initial state
circuit.step()            # Advance 1 cycle
circuit.step(10)          # Advance 10 cycles
```

### Cycle Count

```python
print(circuit.cycle)      # Current cycle number
```

## Internal Gate Access

### Reading Gates

```python
# By hierarchical name
value = circuit.peek_gate("fa1.x1")
value = circuit.peek_gate("fa1_x1")  # Flattened name also works

# Get gate info
gate = circuit.get_gate("fa1_x1")
print(gate.name)          # "fa1_x1"
print(gate.type)          # "XOR"
print(gate.output)        # 1 or 0
print(gate.hierarchy)     # "Adder16/fa1/x1"
```

### Listing Gates

```python
# All gates
for gate in circuit.gates():
    print(f"{gate.name}: {gate.output}")

# Filtered
for gate in circuit.gates("fa1*"):
    print(gate.name, gate.output)

# By type
xor_gates = circuit.gates(type="XOR")
```

## Breakpoints and Watchpoints

### Setting Breakpoints

```python
# Break on any change
bp1 = circuit.breakpoint("Cout")

# Conditional
bp2 = circuit.breakpoint("Cout", condition="Cout == 1")
bp3 = circuit.breakpoint("Sum", condition="Sum > 255")

# On internal gates
bp4 = circuit.breakpoint("fa1.o1")
```

### Watchpoints

```python
wp = circuit.watchpoint("Sum")
```

### Running to Breakpoint

```python
result = circuit.continue_()  # Note underscore (continue is Python keyword)

if result.stopped:
    print(f"Stopped at cycle {result.cycle}")
    print(f"Reason: {result.reason}")
    print(f"Signal: {result.signal}")
    print(f"Old: {result.old_value}, New: {result.new_value}")
```

### Callback-based Watching

```python
def on_carry(signal, old_value, new_value):
    print(f"Carry changed: {old_value} -> {new_value}")
    return True  # Continue execution (False to stop)

circuit.watch("Cout", on_carry)
circuit.run()  # Runs until callback returns False or error
```

### Managing Breakpoints

```python
bp.disable()
bp.enable()
bp.delete()

# Clear all
circuit.clear_breakpoints()
```

## Hierarchy Navigation

### Getting Hierarchy

```python
hier = circuit.hierarchy()
print(hier)  # Tree structure

for instance in circuit.instances():
    print(f"{instance.name}: {instance.type}")
```

### Scope

```python
circuit.scope("fa1")
print(circuit.current_scope)  # "Adder16/fa1"

# Relative access
circuit.peek("x1")  # Same as fa1.x1

circuit.scope("..")  # Go up
circuit.scope("/")   # Go to root
```

## Debug Information

### Port Info

```python
for port in circuit.inputs:
    print(f"{port.name}: {port.width} bits")

for port in circuit.outputs:
    print(f"{port.name}: {port.width} bits")
```

### Source Mapping

```python
# What gates came from a source line?
gates = circuit.gates_from_line("adder16.shdl", 8)

# What source line defined this gate?
loc = circuit.source_location("fa1_x1")
print(f"{loc.file}:{loc.line}")
```

## Waveform Recording

### Recording

```python
circuit.record_signals(["A", "B", "Sum", "Cout"])
circuit.record_start()

for a in range(256):
    circuit.poke("A", a)
    circuit.step()

circuit.record_stop()
```

### Accessing Recorded Data

```python
# Get all recorded data
data = circuit.record_data()
for sample in data:
    print(f"Cycle {sample.cycle}: Sum={sample['Sum']}")

# Get specific signal
sum_values = circuit.record_signal("Sum")
```

### Exporting

```python
circuit.record_export("waves.vcd")
circuit.record_export("waves.json")
circuit.record_export("waves.csv")
```

## Practical Examples

### Test Harness

```python
import shdb

def test_adder():
    with shdb.Circuit("adder16.shdl") as c:
        # Test cases: (a, b, expected_sum, expected_cout)
        tests = [
            (0, 0, 0, 0),
            (1, 1, 2, 0),
            (42, 17, 59, 0),
            (0xFFFF, 1, 0, 1),  # Overflow
        ]
        
        for a, b, exp_sum, exp_cout in tests:
            c.reset()
            c.poke("A", a)
            c.poke("B", b)
            c.step()
            
            assert c.peek("Sum") == exp_sum, f"Sum mismatch for {a}+{b}"
            assert c.peek("Cout") == exp_cout, f"Cout mismatch for {a}+{b}"
        
        print("All tests passed!")

test_adder()
```

### Exhaustive Testing

```python
import shdb

def exhaustive_test_4bit():
    with shdb.Circuit("adder4.shdl") as c:
        failures = 0
        
        for a in range(16):
            for b in range(16):
                c.poke("A", a)
                c.poke("B", b)
                c.step()
                
                expected = (a + b) & 0x1F
                actual = c.peek("Sum") | (c.peek("Cout") << 4)
                
                if actual != expected:
                    print(f"FAIL: {a}+{b}={actual}, expected {expected}")
                    failures += 1
        
        print(f"Exhaustive test: {256 - failures}/256 passed")
        return failures == 0

exhaustive_test_4bit()
```

### Performance Benchmarking

```python
import shdb
import time

with shdb.Circuit("adder16.shdl") as c:
    start = time.time()
    
    for i in range(1_000_000):
        c.poke("A", i & 0xFFFF)
        c.poke("B", (i >> 16) & 0xFFFF)
        c.step()
    
    elapsed = time.time() - start
    print(f"1M cycles in {elapsed:.2f}s = {1_000_000/elapsed:.0f} cycles/sec")
```

### Gate-Level Analysis

```python
import shdb

with shdb.Circuit("adder16.shdl") as c:
    c.poke("A", 0xFFFF)
    c.poke("B", 1)
    c.step()
    
    # Analyze carry chain
    print("Carry chain propagation:")
    for i in range(1, 17):
        gate = c.get_gate(f"fa{i}_o1")  # OR gate = carry out
        print(f"  Bit {i}: carry = {gate.output}")
```

### Waveform Analysis

```python
import shdb

with shdb.Circuit("adder16.shdl") as c:
    c.record_signals(["Sum", "Cout"])
    c.record_start()
    
    # Run test pattern
    for a in range(0, 65536, 1000):
        c.poke("A", a)
        c.poke("B", 1000)
        c.step()
    
    c.record_stop()
    
    # Analyze
    data = c.record_data()
    overflow_cycles = [s.cycle for s in data if s["Cout"] == 1]
    print(f"Overflow occurred at cycles: {overflow_cycles}")
    
    c.record_export("analysis.vcd")
```

### Integration with pytest

```python
# test_adder.py
import pytest
import shdb

@pytest.fixture
def adder():
    circuit = shdb.Circuit("adder16.shdl")
    yield circuit
    circuit.close()

def test_zero_addition(adder):
    adder.poke("A", 0)
    adder.poke("B", 0)
    adder.step()
    assert adder.peek("Sum") == 0
    assert adder.peek("Cout") == 0

def test_simple_addition(adder):
    adder.poke("A", 42)
    adder.poke("B", 17)
    adder.step()
    assert adder.peek("Sum") == 59

def test_overflow(adder):
    adder.poke("A", 0xFFFF)
    adder.poke("B", 1)
    adder.step()
    assert adder.peek("Sum") == 0
    assert adder.peek("Cout") == 1

@pytest.mark.parametrize("a,b,expected", [
    (0, 0, 0),
    (1, 1, 2),
    (100, 200, 300),
    (0x8000, 0x8000, 0),
])
def test_additions(adder, a, b, expected):
    adder.poke("A", a)
    adder.poke("B", b)
    adder.step()
    assert adder.peek("Sum") == expected
```

Run with:
```bash
pytest test_adder.py -v
```

## API Reference

### Circuit Class

```python
class Circuit:
    # Loading
    def __init__(self, source=None, library=None, debug_info=None)
    def close()
    
    # Properties
    @property cycle: int
    @property inputs: List[PortInfo]
    @property outputs: List[PortInfo]
    @property current_scope: str
    
    # Simulation
    def reset()
    def step(cycles=1)
    def poke(signal: str, value: int)
    def peek(signal: str) -> int
    def poke_bits(signal: str, start: int, end: int, value: int)
    def peek_bits(signal: str, start: int, end: int) -> int
    
    # Gates
    def peek_gate(name: str) -> int
    def get_gate(name: str) -> GateInfo
    def gates(pattern: str = "*", type: str = None) -> List[GateInfo]
    
    # Breakpoints
    def breakpoint(signal: str, condition: str = None) -> Breakpoint
    def watchpoint(signal: str, condition: str = None) -> Watchpoint
    def watch(signal: str, callback: Callable) -> Watch
    def clear_breakpoints()
    def continue_() -> StopResult
    def run()
    
    # Hierarchy
    def hierarchy() -> HierarchyNode
    def instances() -> List[InstanceInfo]
    def scope(path: str)
    
    # Source mapping
    def gates_from_line(file: str, line: int) -> List[str]
    def source_location(gate: str) -> SourceLocation
    
    # Recording
    def record_signals(signals: List[str])
    def record_start()
    def record_stop()
    def record_data() -> List[Sample]
    def record_signal(name: str) -> List[int]
    def record_export(path: str)
```

### Data Classes

```python
@dataclass
class PortInfo:
    name: str
    width: int
    
@dataclass
class GateInfo:
    name: str
    type: str
    output: int
    hierarchy: str
    source_file: str
    source_line: int

@dataclass
class StopResult:
    stopped: bool
    cycle: int
    reason: str
    signal: str
    old_value: int
    new_value: int
```
