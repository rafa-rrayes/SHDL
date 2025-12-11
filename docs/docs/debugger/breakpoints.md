---
sidebar_position: 5
---

# Breakpoints and Watchpoints

SHDB uses signal-based breakpoints instead of line-based breakpoints. This matches the nature of hardware simulation where you care about signal values, not source lines.

## Breakpoints

Breakpoints pause simulation when a signal condition is met.

### Basic Breakpoints

Break when a signal changes:

```
(shdb) break Cout
Breakpoint 1: Cout (any change)

(shdb) continue
... simulation runs ...
Breakpoint 1 hit: Cout changed 0 -> 1
Cycle: 15
```

### On Specific Bits

```
(shdb) break Sum[8]
Breakpoint 2: Sum[8] (any change)

(shdb) break Sum[1:4]
Breakpoint 3: Sum[1:4] (any change)
```

### On Internal Gates

```
(shdb) break fa1.x1.O
Breakpoint 4: fa1.x1.O (any change)

(shdb) break fa1_o1.O           # Using flattened name
Breakpoint 5: fa1_o1.O (any change)
```

## Conditional Breakpoints

Add conditions with `if`:

### Value Conditions

```
(shdb) break Cout if Cout == 1
Breakpoint 1: Cout == 1

(shdb) break Sum if Sum > 255
Breakpoint 2: Sum > 255

(shdb) break Sum if Sum == 0
Breakpoint 3: Sum == 0
```

### Complex Conditions

```
(shdb) break Sum if (Sum & 0xFF) == 0
Breakpoint 4: (Sum & 0xFF) == 0

(shdb) break Cout if A > B
Breakpoint 5: Cout when A > B

(shdb) break Sum if Sum == A + B
Breakpoint 6: Sum == A + B
```

### Using Debugger Variables

```
(shdb) set $threshold = 100
(shdb) break Sum if Sum > $threshold
Breakpoint 7: Sum > $threshold
```

## Edge-Triggered Breakpoints

For clock-like or toggle signals:

```
(shdb) break clk rising         # 0 -> 1 transition
Breakpoint 1: clk (rising edge)

(shdb) break clk falling        # 1 -> 0 transition
Breakpoint 2: clk (falling edge)

(shdb) break clk edge           # Any transition
Breakpoint 3: clk (any edge)
```

This is especially useful for:
- Clock signals
- Enable lines
- State machine outputs

## Temporary Breakpoints

One-shot breakpoints that delete themselves after triggering:

```
(shdb) tbreak Cout
Temporary breakpoint 1: Cout (any change)

(shdb) continue
Temporary breakpoint 1 hit: Cout changed 0 -> 1
Breakpoint 1 deleted.
```

## Managing Breakpoints

### List Breakpoints

```
(shdb) info breakpoints
(shdb) i b

Num  Type       Enabled  Condition          Hits
1    breakpoint yes      Cout (any change)  3
2    breakpoint yes      Cout == 1          1
3    breakpoint no       fa1.o1.O (change)  0
4    breakpoint yes      Sum > 255          0
```

### Disable/Enable

```
(shdb) disable 3
Breakpoint 3 disabled.

(shdb) enable 3
Breakpoint 3 enabled.
```

### Delete

```
(shdb) delete 2
Breakpoint 2 deleted.

(shdb) clear                    # Delete all breakpoints
All breakpoints deleted.
```

## Watchpoints

Watchpoints are specialized breakpoints for monitoring value changes.

### Basic Watchpoints

```
(shdb) watch Sum
Watchpoint 1: Sum

(shdb) continue
Watchpoint 1 hit: Sum changed 0x0000 -> 0x003B
Old value: 0 (0x0000)
New value: 59 (0x003B)
```

Watchpoints show both old and new values, making them ideal for debugging.

### Conditional Watchpoints

```
(shdb) watch Sum == 100
Watchpoint 2: Sum == 100

(shdb) watch Sum > $threshold
Watchpoint 3: Sum > $threshold
```

### Access Watchpoints

```
(shdb) awatch A                 # Trigger on read or write
Access watchpoint 1: A

(shdb) rwatch B                 # Trigger on read only
Read watchpoint 2: B
```

### Managing Watchpoints

```
(shdb) info watchpoints
(shdb) i w

Num  Type       Enabled  Signal    Condition
1    watchpoint yes      Sum       (any change)
2    watchpoint yes      Sum       == 100
3    awatch     yes      A         (access)
```

## Breakpoint Actions

### Commands on Break

Execute commands when a breakpoint triggers:

```
(shdb) break Cout
Breakpoint 1: Cout (any change)

(shdb) commands 1
> print/t A B Sum Cout
> end

(shdb) continue
Breakpoint 1 hit: Cout changed 0 -> 1
┌────────┬──────────────────┬─────────┐
│ Signal │ Hex              │ Decimal │
├────────┼──────────────────┼─────────┤
│ A      │ 0xFFFF           │ 65535   │
│ B      │ 0x0001           │ 1       │
│ Sum    │ 0x0000           │ 0       │
│ Cout   │ 0x1              │ 1       │
└────────┴──────────────────┴─────────┘
```

### Silent Breakpoints

Don't pause, just execute commands:

```
(shdb) break Sum
Breakpoint 1: Sum (any change)

(shdb) commands 1
> silent
> print Sum
> continue
> end
```

This logs every Sum change without stopping.

## Practical Examples

### Finding When Carry Propagates

```
(shdb) break Cout if Cout == 1
Breakpoint 1: Cout == 1

(shdb) reset
(shdb) set A = 0
(shdb) set B = 0

# Binary search for carry
(shdb) set A = 0x8000
(shdb) set B = 0x8000
(shdb) step
Breakpoint 1 hit: Cout changed 0 -> 1
```

### Detecting Overflow

```
(shdb) break Sum if Sum < A && Sum < B
Breakpoint 1: overflow condition

(shdb) continue
# Will trigger when addition wraps around
```

### Tracing a Specific Gate

```
(shdb) break fa8.o1.O          # 8th full adder carry
Breakpoint 1: fa8.o1.O (any change)

(shdb) commands 1
> print "Bit 8 carry changed at cycle " $cycle
> print fa8.A fa8.B fa8.Cin fa8.o1.O
> end
```

### Test Harness

```shdb
# test_all_bits.shdb
reset

# Test each bit position for carry
for $bit in 1..16
  set A = 1 << ($bit - 1)
  set B = 1 << ($bit - 1)
  step
  
  if Cout != 0
    print "Unexpected carry at bit " $bit
  end
end

print "Bit tests complete"
```

## Breakpoint Tips

1. **Start broad, then narrow**: Begin with unconditional breakpoints, then add conditions as you understand the behavior.

2. **Use watchpoints for debugging**: They show old and new values, making it easier to spot issues.

3. **Combine with waveforms**: Record signals while running to breakpoints, then analyze the trace.

4. **Use temporary breakpoints**: For one-time checks, `tbreak` keeps your breakpoint list clean.

5. **Remember cycle count**: Breakpoints report the cycle number, useful for correlating with waveforms.
