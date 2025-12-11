---
sidebar_position: 7
---

# Waveform Recording

SHDB can record signal values over time and export them for visualization in waveform viewers like GTKWave.

## Quick Start

```
(shdb) record signals A B Sum Cout
(shdb) record start
(shdb) step 100
(shdb) record stop
(shdb) record export waves.vcd
```

## Recording Signals

### Select Signals

Choose which signals to record:

```
(shdb) record signals A B Sum Cout
Recording signals: A, B, Sum, Cout

(shdb) record signals fa1.x1.O fa1.o1.O
Recording signals: A, B, Sum, Cout, fa1.x1.O, fa1.o1.O
```

### Record All

Record all inputs and outputs:

```
(shdb) record all
Recording all 5 signals: A, B, Cin, Sum, Cout
```

### Include Gates

Record internal gates:

```
(shdb) record all --include-gates
Recording 361 signals (5 ports + 356 gates)
```

### Clear Selection

```
(shdb) record clear
Signal selection cleared.
```

## Recording Session

### Start Recording

```
(shdb) record start
Recording started at cycle 0
```

### Run Simulation

```
(shdb) step 100
# Or
(shdb) continue              # Until breakpoint
```

### Stop Recording

```
(shdb) record stop
Recording stopped. 100 samples captured.
```

### Recording Status

```
(shdb) record status
Recording: active
Started: cycle 0
Current: cycle 47
Samples: 47
Signals: 5
Memory: 1.2 KB
```

## Viewing Recorded Data

### ASCII Display

```
(shdb) record show
Cycle │ A     │ B     │ Sum   │ Cout
──────┼───────┼───────┼───────┼──────
    0 │    42 │    17 │     0 │    0
    1 │    42 │    17 │    59 │    0
    2 │   100 │    50 │   150 │    0
    3 │   200 │   100 │   300 │    0
    4 │   255 │     1 │   256 │    0
  ... │   ... │   ... │   ... │  ...
```

### ASCII Waveform

```
(shdb) record show --ascii

    A: ████████████████████████████████████████
    B: ▂▂▂▂████████████████▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂
  Sum: ▁▁▁▁████████████████████████████████████
 Cout: ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁████▁▁▁▁▁▁▁▁▁▁
```

### Cycle Range

```
(shdb) record show 10 20
Showing cycles 10-20:
Cycle │ A     │ B     │ Sum   │ Cout
──────┼───────┼───────┼───────┼──────
   10 │   100 │    50 │   150 │    0
   11 │   100 │    50 │   150 │    0
  ...
```

### Single Signal

```
(shdb) record show Sum
Sum values (cycles 0-99):
  0: 0
  1: 59
  2: 150
  ...
```

## Export Formats

### VCD (Value Change Dump)

Standard format for waveform viewers:

```
(shdb) record export waves.vcd
Exported 100 cycles to waves.vcd
```

Open with GTKWave:
```bash
gtkwave waves.vcd
```

VCD file format:
```vcd
$timescale 1ns $end
$scope module Adder16 $end
$var wire 16 A A $end
$var wire 16 B B $end
$var wire 16 Sum Sum $end
$var wire 1 Cout Cout $end
$upscope $end
$enddefinitions $end
#0
b0000000000101010 A
b0000000000010001 B
b0000000000000000 Sum
0Cout
#1
b0000000000111011 Sum
...
```

### JSON Format

For custom processing:

```
(shdb) record export waves.json
Exported 100 cycles to waves.json
```

JSON structure:
```json
{
  "format": "shdb-waveform",
  "version": "1.0",
  "component": "Adder16",
  "timescale": "1ns",
  "signals": [
    {"name": "A", "width": 16},
    {"name": "B", "width": 16},
    {"name": "Sum", "width": 16},
    {"name": "Cout", "width": 1}
  ],
  "data": [
    {"cycle": 0, "A": 42, "B": 17, "Sum": 0, "Cout": 0},
    {"cycle": 1, "A": 42, "B": 17, "Sum": 59, "Cout": 0},
    ...
  ]
}
```

### CSV Format

For spreadsheet analysis:

```
(shdb) record export waves.csv
Exported 100 cycles to waves.csv
```

```csv
cycle,A,B,Sum,Cout
0,42,17,0,0
1,42,17,59,0
2,100,50,150,0
...
```

### Including Gates

```
(shdb) record export debug.vcd --include-gates
```

This adds internal gate signals to the VCD file.

## Recording Options

### Buffer Size

```
(shdb) record buffer 1000000   # 1M samples
```

Default is 100,000 samples.

### Circular Buffer

Overwrite old samples when buffer is full:

```
(shdb) record circular on
```

### Triggered Recording

Start recording on a condition:

```
(shdb) record trigger Cout == 1
(shdb) record signals A B Sum Cout
(shdb) record arm
Recording armed, waiting for trigger...

(shdb) continue
Trigger hit: Cout == 1 at cycle 47
Recording started.
```

### Pre-trigger Buffer

Capture samples before the trigger:

```
(shdb) record pretrigger 100    # 100 cycles before trigger
```

## Practical Examples

### Test Pattern Recording

```shdb
# Record all test cases
reset
record signals A B Sum Cout
record start

# Test 0 + 0
set A = 0
set B = 0
step

# Test simple addition  
set A = 42
set B = 17
step

# Test overflow
set A = 0xFFFF
set B = 1
step

record stop
record export tests.vcd
```

### Long Simulation

```
(shdb) record all
(shdb) record buffer 10000000   # 10M samples
(shdb) record start
(shdb) step 1000000
(shdb) record stop
(shdb) record export long_run.vcd
Exported 1000000 cycles to long_run.vcd (45 MB)
```

### Focused Analysis

Record only during interesting periods:

```
(shdb) # Set up circuit
(shdb) set A = 0x1234
(shdb) set B = 0x5678
(shdb) step 10

(shdb) # Start recording for analysis
(shdb) record signals Sum Cout fa*.o1.O  # Carry chain
(shdb) record start
(shdb) step 5
(shdb) record stop
(shdb) record export carry_chain.vcd
```

### Debugging with GTKWave

1. Record signals:
```
(shdb) record all
(shdb) record start
(shdb) step 1000
(shdb) record stop
(shdb) record export debug.vcd
```

2. Open in GTKWave:
```bash
gtkwave debug.vcd &
```

3. Add signals in GTKWave, zoom to interesting region

4. Note the cycle number of interest

5. Back in SHDB:
```
(shdb) reset
(shdb) step 542           # Go to interesting cycle
(shdb) print *            # Inspect state
```

## Memory Considerations

Recording uses memory proportional to:
- Number of signals
- Number of cycles
- Signal widths

Approximate memory usage:
```
memory = signals × cycles × avg_bytes_per_signal
```

For a 16-bit adder with 5 ports, 100,000 cycles:
```
5 signals × 100,000 cycles × 2 bytes ≈ 1 MB
```

Recording all 356 gates:
```
361 signals × 100,000 cycles × 1 byte ≈ 36 MB
```

### Tips for Large Recordings

1. **Select specific signals** instead of `record all`
2. **Use circular buffer** for long runs where you only care about recent history
3. **Use triggered recording** to capture only interesting events
4. **Record in segments** and export incrementally
