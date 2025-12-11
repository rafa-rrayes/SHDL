---
sidebar_position: 8
---

# Scripting

SHDB supports scripting for automated testing, regression suites, and complex debug scenarios.

## Script Files

SHDB scripts use the `.shdb` extension and contain regular SHDB commands:

```shdb
# test_adder.shdb - Test script for Adder16

# Setup
reset
set A = 0
set B = 0

# Test 1: Zero addition
step 1
assert Sum == 0
assert Cout == 0
print "Test 1 passed: 0 + 0 = 0"

# Test 2: Simple addition
set A = 42
set B = 17
step 1
assert Sum == 59
assert Cout == 0
print "Test 2 passed: 42 + 17 = 59"

print "All tests passed!"
```

## Running Scripts

### From Command Line

```bash
shdb myCircuit.shdl -x test_adder.shdb
```

### From SHDB

```
(shdb) source test_adder.shdb
Test 1 passed: 0 + 0 = 0
Test 2 passed: 42 + 17 = 59
All tests passed!
```

## Assertions

### Basic Assertions

```shdb
assert Sum == 59
assert Cout == 0
assert A > B
```

### Assertion Messages

```shdb
assert Sum == 59, "Sum should be 59, got " Sum
```

### Soft Assertions

Continue after failure:

```shdb
check Sum == 59             # Warn but don't stop
```

## Variables

### Debugger Variables

```shdb
set $expected = 42 + 17
set $count = 0
set $threshold = 100
```

### Using Variables

```shdb
set A = $count
set B = $expected
assert Sum > $threshold
print "Count: " $count
```

### Incrementing

```shdb
set $count = $count + 1
```

## Control Flow

### If/Else

```shdb
if Sum > 255
  print "Overflow detected!"
  set $overflow = 1
else
  set $overflow = 0
end

if Cout == 1
  print "Carry out"
elsif Sum == 0
  print "Zero result"
else
  print "Normal result"
end
```

### For Loops

```shdb
for $i in 1..16
  set A = $i
  step 1
  print "A=" $i " Sum=" Sum
end
```

Range variations:
```shdb
for $i in 0..255          # 0 to 255 inclusive
for $i in 1..16           # 1 to 16 inclusive  
for $i in 0..100..2       # 0, 2, 4, ..., 100 (step 2)
```

### While Loops

```shdb
set $i = 0
while $i < 100
  set A = $i
  step 1
  set $i = $i + 1
end
```

### Break and Continue

```shdb
for $i in 1..1000
  set A = $i
  step 1
  if Cout == 1
    print "Carry at A=" $i
    break
  end
end
```

## Custom Commands

### Defining Commands

```shdb
define test-add
  set A = $arg0
  set B = $arg1
  step 1
  print "A=" A " B=" B " Sum=" Sum
  if Sum != ($arg0 + $arg1)
    print "FAIL!"
  end
end
```

### Using Custom Commands

```
(shdb) test-add 100 50
A=100 B=50 Sum=150

(shdb) test-add 255 1
A=255 B=1 Sum=256
```

### Commands with Defaults

```shdb
define test-value
  set A = $arg0
  set B = ${arg1:-0}        # Default to 0
  step 1
  print Sum
end
```

### Redefining Commands

```shdb
define test-add
  # New implementation
end
```

## Output and Logging

### Print

```shdb
print "Testing with A=" A
print "Result: " Sum " (expected " $expected ")"
print                       # Blank line
```

### Printf (Formatted)

```shdb
printf "A=%04x B=%04x Sum=%04x\n" A B Sum
printf "Pass rate: %.2f%%\n" ($passed / $total * 100)
```

### Logging to File

```shdb
log "test_results.txt"
print "Test output goes to file"
log off
```

## Error Handling

### Try/Catch

```shdb
try
  set A = $value
  step 1
  assert Sum == $expected
catch
  print "Test failed with error: " $error
  set $failures = $failures + 1
end
```

### Exit Codes

```shdb
if $failures > 0
  exit 1                    # Non-zero exit code
end
exit 0
```

## Practical Examples

### Exhaustive Test

```shdb
# exhaustive_4bit.shdb - Test all 4-bit input combinations

define test-all
  set $passed = 0
  set $failed = 0
  
  for $a in 0..15
    for $b in 0..15
      set A = $a
      set B = $b
      step 1
      
      set $expected = ($a + $b) & 0x1F  # 5 bits for sum+carry
      set $actual = Sum + (Cout << 4)
      
      if $actual == $expected
        set $passed = $passed + 1
      else
        print "FAIL: " $a "+" $b "=" $actual " expected " $expected
        set $failed = $failed + 1
      end
    end
  end
  
  print "Passed: " $passed "/" ($passed + $failed)
  if $failed > 0
    exit 1
  end
end

reset
test-all
```

### Regression Suite

```shdb
# regression.shdb

define run-test
  source $arg0
  if $result != 0
    print "FAILED: " $arg0
    set $failures = $failures + 1
  else
    print "PASSED: " $arg0
  end
end

set $failures = 0

run-test "tests/basic_add.shdb"
run-test "tests/overflow.shdb"
run-test "tests/carry_chain.shdb"
run-test "tests/boundary.shdb"

print ""
print "Failures: " $failures
exit $failures
```

### Performance Measurement

```shdb
# benchmark.shdb

define benchmark
  set $start = $cycle
  
  for $i in 1..10000
    set A = $i
    set B = $i * 2
    step 1
  end
  
  set $elapsed = $cycle - $start
  print "10000 iterations in " $elapsed " cycles"
end

reset
benchmark
```

### Test with Recording

```shdb
# recorded_test.shdb

reset
record signals A B Sum Cout
record start

# Run test patterns
for $pattern in 0x0000 0x5555 0xAAAA 0xFFFF
  set A = $pattern
  set B = ~$pattern & 0xFFFF
  step 1
end

record stop
record export pattern_test.vcd
print "Waveform saved to pattern_test.vcd"
```

## Script Best Practices

1. **Use meaningful names** for custom commands and variables

2. **Add comments** explaining test intent

3. **Use assertions** for expected values

4. **Print progress** for long-running tests

5. **Return exit codes** for CI integration

6. **Organize in directories**:
   ```
   tests/
   ├── unit/
   │   ├── test_add.shdb
   │   └── test_overflow.shdb
   ├── integration/
   │   └── test_full_circuit.shdb
   └── run_all.shdb
   ```

7. **Parameterize tests** with custom commands

8. **Record waveforms** for failed tests to aid debugging
