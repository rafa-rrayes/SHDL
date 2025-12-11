---
sidebar_position: 3
---

# Commands Reference

Complete reference for all SHDB commands.

## Simulation Control

### reset

Reset the circuit to its initial state.

```
(shdb) reset
Circuit reset. Cycle: 0
```

All signals return to 0, and the cycle counter resets.

### step

Advance simulation by N cycles (default: 1).

```
(shdb) step          # Advance 1 cycle
(shdb) step 10       # Advance 10 cycles
(shdb) s 100         # Short form
```

### continue

Run until a breakpoint or watchpoint triggers.

```
(shdb) continue
(shdb) c             # Short form
(shdb) run           # Alias
```

### finish

Run until all signals stabilize (for combinational circuits).

```
(shdb) finish
Signals stabilized after 3 cycles.
```

### quit

Exit the debugger.

```
(shdb) quit
(shdb) q             # Short form
```

---

## Signal Inspection

### print

Display signal values.

```
(shdb) print A              # Print signal A
A = 42 (0x002A)

(shdb) print A B Sum Cout   # Multiple signals
A = 42, B = 17, Sum = 59, Cout = 0

(shdb) p Sum                # Short form
```

#### Format Specifiers

```
(shdb) print/x Sum          # Hexadecimal
Sum = 0x003B

(shdb) print/b Sum          # Binary
Sum = 0b0000000000111011

(shdb) print/d Sum          # Decimal (default)
Sum = 59

(shdb) print/t A B Sum Cout # Table format
┌────────┬──────────────────┬─────────┐
│ Signal │ Hex              │ Decimal │
├────────┼──────────────────┼─────────┤
│ A      │ 0x002A           │ 42      │
│ B      │ 0x0011           │ 17      │
│ Sum    │ 0x003B           │ 59      │
│ Cout   │ 0x0              │ 0       │
└────────┴──────────────────┴─────────┘
```

#### Bit Slicing

```
(shdb) print A[0]           # Single bit
A[0] = 0

(shdb) print A[1:4]         # Bit range (1-indexed)
A[1:4] = 0b0101 (5)

(shdb) print Sum[8:16]      # Upper byte
Sum[8:16] = 0x00
```

#### Internal Gates

```
(shdb) print fa1.x1.O       # Gate output (hierarchical)
fa1.x1.O = 1

(shdb) print fa1_x1.O       # Flattened name
fa1_x1.O = 1
```

#### Expressions

```
(shdb) print A + B
A + B = 59

(shdb) print A ^ B
A ^ B = 59

(shdb) print (A + B) & 0xFF
(A + B) & 0xFF = 59

(shdb) print A == B
A == B = false
```

#### Wildcards

```
(shdb) print *              # All inputs and outputs
(shdb) print fa1.*          # All ports of instance fa1
(shdb) print /gates fa1*    # All gates matching pattern
```

### set

Set input values.

```
(shdb) set A = 100          # Decimal
(shdb) set A = 0xFF         # Hexadecimal
(shdb) set A = 0b10101010   # Binary
(shdb) set A[1] = 1         # Single bit
(shdb) set A[1:8] = 0xFF    # Bit range
```

#### Debugger Variables

```
(shdb) set $expected = A + B
(shdb) print Sum == $expected
Sum == $expected = true
```

### info

Display information about the circuit.

```
(shdb) info signals         # All signals
(shdb) i s                  # Short form

(shdb) info inputs          # Input ports only
(shdb) i i

(shdb) info outputs         # Output ports only
(shdb) i o

(shdb) info gates           # All gates
(shdb) info gates fa1*      # Filter by pattern
(shdb) i g fa1*

(shdb) info breakpoints     # Active breakpoints
(shdb) i b

(shdb) info watchpoints     # Active watchpoints
(shdb) i w
```

---

## Breakpoints

### break

Set a breakpoint on signal changes.

```
(shdb) break Cout           # Break on any change
Breakpoint 1: Cout (any change)

(shdb) break Sum[8]         # Break on specific bit
Breakpoint 2: Sum[8] (any change)

(shdb) break fa1.x1.O       # Break on internal gate
Breakpoint 3: fa1.x1.O (any change)

(shdb) b Cout               # Short form
```

#### Conditional Breakpoints

```
(shdb) break Cout if Cout == 1
Breakpoint 4: Cout == 1

(shdb) break Sum if Sum > 255
Breakpoint 5: Sum > 255

(shdb) break A if A == B
Breakpoint 6: A == B
```

#### Edge-Triggered

```
(shdb) break clk rising     # 0 -> 1 transition
(shdb) break clk falling    # 1 -> 0 transition
(shdb) break clk edge       # Any transition
```

### tbreak

Temporary breakpoint (automatically deleted after first hit).

```
(shdb) tbreak Cout
Temporary breakpoint 1: Cout (any change)
```

### delete

Delete a breakpoint by number.

```
(shdb) delete 1             # Delete breakpoint 1
(shdb) d 1                  # Short form
```

### disable / enable

Temporarily disable or re-enable a breakpoint.

```
(shdb) disable 1
(shdb) enable 1
```

### clear

Delete all breakpoints.

```
(shdb) clear
All breakpoints deleted.
```

---

## Watchpoints

### watch

Watch for value changes.

```
(shdb) watch Sum
Watchpoint 1: Sum

(shdb) continue
Watchpoint 1 hit: Sum changed 0x0000 -> 0x003B
Old value: 0 (0x0000)
New value: 59 (0x003B)
```

#### Conditional Watchpoints

```
(shdb) watch Sum == 100     # Watch for specific value
(shdb) watch Sum > 255      # Watch with condition
```

### awatch

Access watch - triggers on read or write.

```
(shdb) awatch A
```

### rwatch

Read watch - triggers only on read.

```
(shdb) rwatch A
```

---

## Hierarchy Navigation

### hierarchy

Show the component hierarchy tree.

```
(shdb) hierarchy
(shdb) hier                 # Short form

Adder16
├── fa1: FullAdder
│   ├── x1: XOR
│   ├── x2: XOR
│   ├── a1: AND
│   ├── a2: AND
│   └── o1: OR
├── fa2: FullAdder
│   └── ...
└── ...
```

### scope

Change the current scope for relative references.

```
(shdb) scope fa1
Current scope: Adder16/fa1

(shdb) print x1.O           # Now relative to fa1
fa1/x1.O = 1

(shdb) scope ..             # Go up one level
Current scope: Adder16

(shdb) scope /              # Go to root
Current scope: Adder16
```

### where

Show the current scope path.

```
(shdb) where
Current scope: Adder16/fa1
```

### list

Show source code at the current location.

```
(shdb) list
   5: COMPONENT FullAdder(A, B, Cin -> Sum, Cout)
   6:   x1 = XOR(A, B)
>  7:   x2 = XOR(x1.O, Cin)      # Current line
   8:   a1 = AND(A, B)
   9:   a2 = AND(x1.O, Cin)
  10:   o1 = OR(a1.O, a2.O)
```

---

## Waveform Recording

### record

Control waveform recording.

```
(shdb) record signals A B Sum Cout
Recording signals: A, B, Sum, Cout

(shdb) record start
Recording started at cycle 0

(shdb) step 100

(shdb) record stop
Recording stopped. 100 samples captured.

(shdb) record show
Cycle │ A     │ B     │ Sum   │ Cout
──────┼───────┼───────┼───────┼──────
    0 │    42 │    17 │     0 │    0
    1 │    42 │    17 │    59 │    0
  ... │   ... │   ... │   ... │  ...

(shdb) record show --ascii    # ASCII waveform
(shdb) record all             # Record all signals
(shdb) record export waves.vcd
(shdb) record export waves.json
```

---

## Scripting

### source

Run commands from a file.

```
(shdb) source test.shdb
```

### define

Define a custom command.

```
(shdb) define test-add
> set A = $arg0
> set B = $arg1
> step 1
> print Sum
> end

(shdb) test-add 100 50
Sum = 150
```

### python

Execute Python code.

```
(shdb) python print(circuit.peek("Sum"))
59

(shdb) py circuit.poke("A", 100)  # Short form
```

### python-interactive

Enter Python REPL mode.

```
(shdb) python-interactive
>>> circuit.poke("A", 42)
>>> circuit.step()
>>> print(circuit.peek("Sum"))
59
>>> exit()
(shdb)
```

---

## Miscellaneous

### help

Show help for commands.

```
(shdb) help                 # All commands
(shdb) help break           # Specific command
(shdb) h break
```

### history

Show command history.

```
(shdb) history
  1: set A = 42
  2: set B = 17
  3: step
  4: print Sum
```

### shell

Run a shell command.

```
(shdb) shell ls -la
(shdb) !ls -la              # Short form
```

### log

Log session to a file.

```
(shdb) log session.txt
Logging to session.txt

(shdb) log off
Logging stopped.
```
