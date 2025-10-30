# SHDL Compiler - Library API Update

## Overview

The SHDL compiler generates a **C library APIs** instead of standalone executables. This enables integration with testing frameworks, property-based testing, fuzzing, and scripting languages like Python.


### Library API
The compiler generates a basic API with these functions:

```c
void reset(void);
void poke(const char *signal_name, uint64_t value);
uint64_t peek(const char *signal_name);
void step(int cycles);
```

## API Functions

### `void reset(void)`
Resets all internal state to zero. Call this before starting a test.

```c
reset();
```

### `void poke(const char *signal_name, uint64_t value)`
Sets an input signal to a specific value. Marks outputs as dirty (requiring recomputation).

```c
poke("A", 42);
poke("B", 17);
poke("Cin", 1);
```

### `uint64_t peek(const char *signal_name)`
Reads the current value of an input or output signal. Automatically computes outputs if needed.

```c
uint64_t sum = peek("Sum");
uint64_t cout = peek("Cout");
```

### `void step(int cycles)`
Advances the simulation by the specified number of clock cycles. This commits state changes.

```c
step(1);   // Advance by 1 cycle
step(10);  // Advance by 10 cycles
```

## Two-Phase Update Model

The simulator uses a two-phase update model for correct timing:

1. **Pending State**: Computed from current state + inputs.
2. **Current State**: Committed state after `step()`

This ensures:
- We can write combinational and sequential logic correctly
- Using feedback loops we can store state
- Multiple `poke()` calls can be made before evaluation
- Clock boundaries are clearly defined

## Usage Example

### Basic C Test

```c
#include "adder16.c"

int main(void) {
    reset();
    
    // Test case: 42 + 17 + carry_in=1 = 60
    poke("A", 42);
    poke("B", 17);
    poke("Cin", 1);
    
    step(4);  // Advance time to compute outputs
    
    uint64_t sum = peek("Sum");
    uint64_t cout = peek("Cout");
    
    printf("Sum: %llu, Cout: %llu\n", sum, cout);
    
    
    return 0;
}
```

### Python Integration (via ctypes)

```python
import ctypes

# Load the shared library
lib = ctypes.CDLL("./adder16.so")

# Define function signatures
lib.reset.restype = None
lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
lib.peek.restype = ctypes.c_uint64
lib.peek.argtypes = [ctypes.c_char_p]
lib.step.argtypes = [ctypes.c_int]

# Run test
lib.reset()
lib.poke(b"A", 42)
lib.poke(b"B", 17)
lib.poke(b"Cin", 1)
lib.step(4)

sum_val = lib.peek(b"Sum")
cout_val = lib.peek(b"Cout")

print(f"Sum: {sum_val}, Cout: {cout_val}")

# Property-based testing example
import hypothesis
from hypothesis import given, strategies as st

@given(st.integers(0, 65535), st.integers(0, 65535), st.integers(0, 1))
def test_adder_properties(a, b, cin):
    lib.reset()
    lib.poke(b"A", a)
    lib.poke(b"B", b)
    lib.poke(b"Cin", cin)

    lib.step(4)

    sum_val = lib.peek(b"Sum")
    cout_val = lib.peek(b"Cout")
    
    # Verify result
    expected = a + b + cin
    actual = (cout_val << 16) | sum_val
    assert actual == expected, f"{a} + {b} + {cin} = {expected}, got {actual}"

# Run property tests
test_adder_properties()
```

## Building the Library

### As a Shared Library (.so)
```bash
gcc -shared -fPIC -O3 adder16.c -o adder16.so
```

### As a Static Library (.a)
```bash
gcc -c -O3 adder16.c -o adder16.o
ar rcs libadder16.a adder16.o
```

### With a Test Harness
```bash
gcc -O3 adder16.c test_harness.c -o test_adder
./test_adder
```

## Benefits

1. **Testability**: Write comprehensive test suites in any language
2. **CI Integration**: Automate testing on every commit
3. **Property Testing**: Use tools like Hypothesis (Python) or QuickCheck (Haskell)
4. **Fuzzing**: Feed random inputs to find edge cases
5. **Performance Benchmarking**: Measure throughput easily
6. **Debugging**: Inspect intermediate signals at any point

## Internal State Access

You can also peek at internal state vectors for debugging:

```c
uint64_t xor_state = peek("XOR_O_0");
uint64_t and_state = peek("AND_O_0");
```

This is useful for understanding the internal behavior of complex designs.

```c
reset();
poke("A", 42);
poke("B", 17);
poke("Cin", 1);
step(4);
printf("Sum=%llu\n", peek("Sum"));
```

## Future Enhancements

Potential additions to the library API:

- **VCD Generation**: Full waveform dumping for debugging.
- **GPIO Support**: Simulate your circuit with real pins.
- **GDB like Debugging**: Would be awesome.
- **Verilog Support**: Compile to Verilog for synthesis or simulation.

