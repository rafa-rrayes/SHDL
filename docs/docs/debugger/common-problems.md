---
sidebar_position: 11
---

# Common Problems

This page covers common issues you may encounter when using SHDB and SHDL, along with their causes and solutions.

## Simulation Behavior

### Circuit Outputs Are Wrong or Zero After One Step

**Problem:** After calling `step()` once, the output values are incorrect or still zero.

**Cause:** SHDL uses a gate-level simulation model where each gate (XOR, AND, OR, NOT) is evaluated in parallel per step. In circuits with multiple gate levels, signals must propagate through each level, requiring multiple steps.

For example, in a Full Adder:
- **Step 1:** XOR and AND gates compute from inputs
- **Step 2:** Second-level XOR and AND gates compute from first-level outputs
- **Step 3:** OR gate computes from AND outputs

**Solution:** Call `step()` multiple times to allow full propagation. For most circuits, 3-5 steps is sufficient:

```python
controller.reset()
controller.poke("A", 1)
controller.poke("B", 1)
controller.step(5)  # Allow full propagation

# Now outputs are stable
sum_val = controller.peek("Sum")
```

**Tip:** Use the `finish()` method to automatically step until signals stabilize:

```python
result = controller.finish(max_cycles=100)
# Stops when no signals change between cycles
```

---

### Gate Values Don't Match Expected Logic

**Problem:** You peek a gate and get a value that doesn't match what you calculated by hand.

**Cause:** This is usually due to propagation delay. Gates read their inputs from the *previous* cycle's state, not the current inputs.

**Solution:** Step enough times for the value to propagate through all dependent gates. Use `peek_gate()` after sufficient steps:

```python
controller.reset()
controller.poke("A", 1)
controller.poke("B", 0)
controller.step(3)  # Propagate through gate levels

# Now gate values are consistent
x1 = controller.peek_gate("x1")  # A XOR B
```

---

## Breakpoints and Watchpoints

### Breakpoint Never Triggers

**Problem:** You set a breakpoint on a signal, but it never triggers even when the value changes.

**Possible Causes:**

1. **Breakpoint is disabled:**
   ```python
   bp = controller.add_breakpoint("Cout")
   # Check if enabled
   print(bp.enabled)  # Should be True
   ```

2. **Signal name is wrong:** Verify the signal exists:
   ```python
   # Check available signals
   print(controller.symbols.get_all_signals())
   ```

3. **Value doesn't actually change:** The breakpoint only triggers on *changes*. If you're checking a signal that stays constant, it won't trigger.

4. **Using wrong breakpoint type:** A `CHANGE` breakpoint triggers on any change. A `VALUE` breakpoint only triggers when the signal equals a specific value:
   ```python
   # Triggers when Cout becomes 1 (not on every change)
   bp = controller.add_breakpoint("Cout", bp_type=BreakpointType.VALUE, value=1)
   ```

---

### Breakpoint Triggers Immediately

**Problem:** The breakpoint triggers on the first step after being added.

**Cause:** Before the first step, the "previous" value is 0 (or undefined). If the signal has a non-zero value after stepping, the breakpoint sees this as a change.

**Solution:** Initialize the circuit first, then add the breakpoint:

```python
controller.reset()
controller.poke("A", 0)
controller.poke("B", 0)
controller.step(5)  # Initialize to known state

# Now add breakpoint - it won't trigger until actual change
bp = controller.add_breakpoint("Cout")

controller.poke("A", 1)
controller.poke("B", 1)
result = controller.step()  # Should trigger now
```

---

## Loading and Compilation

### "Debug API not available" Error

**Problem:** You get `RuntimeError: Debug API not available (compile with -g)` when calling `peek_gate()`.

**Cause:** The circuit was compiled without debug information.

**Solution:** Recompile with the `-g` flag:

```bash
shdlc -g myCircuit.shdl -c -o libmyCircuit.dylib
```

---

### "Unknown signal" or "Unknown gate" Error

**Problem:** `peek()` or `peek_gate()` says the signal/gate doesn't exist.

**Possible Causes:**

1. **Typo in name:** Signal names are case-sensitive. `"sum"` ≠ `"Sum"`.

2. **Using hierarchical path incorrectly:** For flattened gates, use underscores:
   ```python
   # If you have instance "fa1" with gate "x1":
   controller.peek_gate("fa1_x1")  # Correct (flattened name)
   # NOT: controller.peek_gate("fa1.x1")  # Won't work with peek_gate
   ```

3. **Signal doesn't exist:** Check available signals:
   ```python
   print(list(controller.debug_info.gates.keys()))
   print([p.name for p in controller.debug_info.inputs])
   print([p.name for p in controller.debug_info.outputs])
   ```

---

### .shdb File Not Found

**Problem:** `DebugInfo.load()` fails because the `.shdb` file doesn't exist.

**Cause:** Either compilation failed, or you used `--no-shdb` flag.

**Solution:** 
1. Check that compilation succeeded without errors
2. The `.shdb` file is created in the same directory as the output library, with the same base name
3. Don't use `--no-shdb` if you need the debug metadata

```bash
# Creates both libmyCircuit.dylib AND libmyCircuit.shdb
shdlc -g myCircuit.shdl -c -o /path/to/libmyCircuit.dylib
ls /path/to/libmyCircuit.*
# Should show: libmyCircuit.dylib  libmyCircuit.shdb
```

---

## Python API Issues

### Controller Doesn't Reflect Poke Values

**Problem:** After calling `poke()`, `peek()` still returns the old value.

**Cause:** `poke()` only sets the input value; outputs are computed on `step()`.

**Solution:** Call `step()` after `poke()` to compute new outputs:

```python
controller.poke("A", 42)
controller.step(5)  # Compute outputs
value = controller.peek("Sum")  # Now reflects new inputs
```

---

### Library Loading Fails on macOS

**Problem:** `DebugController` fails to load the `.dylib` with an error about missing library or signature.

**Possible Causes:**

1. **Library not compiled:** Make sure you used `-c` flag to compile to a shared library.

2. **Wrong architecture:** If using Apple Silicon (M1/M2), ensure the library was compiled for arm64.

3. **Code signing issues:** macOS may quarantine downloaded/compiled libraries:
   ```bash
   xattr -d com.apple.quarantine libmyCircuit.dylib
   ```

4. **Missing dependencies:** The library needs standard C library. This is usually available.

---

### Import Error: Module Not Found

**Problem:** `from SHDL.debugger import DebugInfo` fails with ImportError.

**Cause:** SHDL is not installed or not in your Python path.

**Solution:**
```bash
# Install SHDL
pip install shdl
# or with uv
uv add shdl

# Verify installation
python -c "from SHDL.debugger import DebugInfo; print('OK')"
```

---

## Circuit Design Issues

### Circuit Has No Gates

**Problem:** After compiling, `debug_info.gates` is empty.

**Cause:** The component only has ports and connections, no primitive gates.

**Solution:** Make sure your component instantiates primitives (XOR, AND, OR, NOT) or other components that eventually use primitives:

```shdl
component MyComponent(A, B) -> (O) {
    x1: XOR;  // This creates a gate
    connect {
        A -> x1.A;
        B -> x1.B;
        x1.O -> O;
    }
}
```

---

### Constant Values Are Wrong

**Problem:** Constants in your circuit have unexpected values.

**Cause:** Constants are materialized as VCC/GND gates. Each bit is a separate gate.

**Solution:** Check how constants are defined and used:

```shdl
// 8-bit constant with value 100
const Hundred = 100:8;

// Use in circuit
connect {
    Hundred -> someInput;  // All 8 bits connected
}
```

---

## Performance Issues

### Simulation Is Slow

**Problem:** Stepping through many cycles is slow.

**Causes:**
1. Debug builds have overhead for gate tables and cycle counting
2. Large circuits have many gates to evaluate
3. Calling `peek_gate()` frequently triggers recomputation

**Solutions:**

1. **Step in batches:**
   ```python
   controller.step(1000)  # Much faster than 1000 individual steps
   ```

2. **Use release builds for performance testing:**
   ```bash
   shdlc myCircuit.shdl -c -o libmyCircuit.dylib  # No -g flag
   ```

3. **Cache gate values instead of repeated peek_gate() calls:**
   ```python
   all_gates = controller.get_all_gates()  # One call
   # Use all_gates dict instead of multiple peek_gate() calls
   ```

---

## Getting Help

If you encounter an issue not covered here:

1. Check the error message carefully - it often contains the solution
2. Verify your circuit compiles without the `-g` flag first
3. Test with a simple circuit (like FullAdder) to isolate the problem
4. Check the [SHDB overview](./overview.md) for implementation details
