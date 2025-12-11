---
sidebar_position: 7
---

# 16-bit Register

A register stores data and outputs it on demand. This example shows a 16-bit register with load enable.

## Design Overview

A register is built from D flip-flops. In SHDL, we typically use a simplified model where:
- When `Load` is high, the register captures the input
- The stored value is always available on the output

## Single-Bit Register Cell

First, let's build a single-bit memory cell:

```
component BitCell(D, Load) -> (Q) {
    # Multiplexer: select between old value and new input
    muxAnd1: AND;  # D & Load
    muxAnd2: AND;  # Q & ~Load
    muxOr: OR;
    notLoad: NOT;
    
    # Feedback loop (this is a simplified latch model)
    # In real hardware, this would need proper clocking
    
    connect {
        # Invert Load for the "keep old value" path
        Load -> notLoad.A;
        
        # If Load=1, pass D through
        D -> muxAnd1.A;
        Load -> muxAnd1.B;
        
        # If Load=0, keep current Q (feedback)
        # Note: In simulation, this creates a feedback loop
        # that the simulator handles through iterative settling
        muxOr.O -> muxAnd2.A;
        notLoad.O -> muxAnd2.B;
        
        # Combine paths
        muxAnd1.O -> muxOr.A;
        muxAnd2.O -> muxOr.B;
        
        # Output
        muxOr.O -> Q;
    }
}
```

## 16-bit Register

Now we compose 16 bit cells into a full register:

```
use bitcell::{BitCell};

component Reg16(D[16], Load) -> (Q[16]) {
    # 16 bit cells, one for each bit
    >i[16]{
        cell{i}: BitCell;
    }
    
    connect {
        # Connect each bit cell
        >i[16]{
            D[{i}] -> cell{i}.D;
            Load -> cell{i}.Load;
            cell{i}.Q -> Q[{i}];
        }
    }
}
```

## How It Works

1. When `Load = 1`:
   - `muxAnd1` passes the input `D` through
   - `muxAnd2` is blocked (its `Load` input is 0 after NOT)
   - The new value propagates to `Q`

2. When `Load = 0`:
   - `muxAnd1` is blocked
   - `muxAnd2` passes the current `Q` back around
   - The value is retained

## Alternative: Using a 2-to-1 Mux

A cleaner implementation uses a dedicated multiplexer:

```
use mux2::{Mux2};

component BitCellMux(D, Load) -> (Q) {
    mux: Mux2;
    
    connect {
        # Sel=0: keep current value (feedback from Q)
        # Sel=1: load new value from D
        mux.O -> mux.A;  # Feedback path
        D -> mux.B;
        Load -> mux.Sel;
        mux.O -> Q;
    }
}
```

Where `Mux2` is:

```
component Mux2(A, B, Sel) -> (O) {
    # O = (A AND NOT Sel) OR (B AND Sel)
    notSel: NOT;
    andA: AND;
    andB: AND;
    orOut: OR;
    
    connect {
        Sel -> notSel.A;
        
        A -> andA.A;
        notSel.O -> andA.B;
        
        B -> andB.A;
        Sel -> andB.B;
        
        andA.O -> orOut.A;
        andB.O -> orOut.B;
        
        orOut.O -> O;
    }
}
```

## Register File

A collection of registers with addressing:

```
use reg16::{Reg16};
use decoder::{Decoder2to4};
use mux4_16::{Mux4_16};

component RegFile4x16(
    WriteData[16], 
    WriteAddr[2], 
    WriteEn,
    ReadAddr[2]
) -> (ReadData[16]) {
    # 4 registers
    >i[4]{
        reg{i}: Reg16;
    }
    
    # Write address decoder
    writeDec: Decoder2to4;
    
    # AND each decoder output with WriteEn
    >i[4]{
        loadAnd{i}: AND;
    }
    
    # Read multiplexer (4-to-1, 16-bit wide)
    readMux: Mux4_16;
    
    connect {
        # Decode write address
        WriteAddr[:2] -> writeDec.A[:2];
        
        # Generate load signals: decoder output AND WriteEn
        >i[4]{
            writeDec.Y[{i}] -> loadAnd{i}.A;
            WriteEn -> loadAnd{i}.B;
            loadAnd{i}.O -> reg{i}.Load;
        }
        
        # Connect write data to all registers
        >i[4]{
            >j[16]{
                WriteData[{j}] -> reg{i}.D[{j}];
            }
        }
        
        # Read multiplexer inputs
        >j[16]{
            reg1.Q[{j}] -> readMux.A[{j}];
            reg2.Q[{j}] -> readMux.B[{j}];
            reg3.Q[{j}] -> readMux.C[{j}];
            reg4.Q[{j}] -> readMux.D[{j}];
        }
        
        # Read address selects output
        ReadAddr[:2] -> readMux.Sel[:2];
        
        # Output
        readMux.O[:16] -> ReadData[:16];
    }
}
```

## Testing with PySHDL

```python
from SHDL import SHDLCircuit

with SHDLCircuit("reg16.shdl") as reg:
    # Test 1: Load a value
    reg.poke("D", 0xABCD)
    reg.poke("Load", 1)
    reg.step()
    
    assert reg.peek("Q") == 0xABCD, "Failed to load value"
    
    # Test 2: Value retained when Load=0
    reg.poke("D", 0x1234)  # New value on input
    reg.poke("Load", 0)    # But don't load it
    reg.step()
    
    assert reg.peek("Q") == 0xABCD, "Value not retained"
    
    # Test 3: Load new value
    reg.poke("Load", 1)
    reg.step()
    
    assert reg.peek("Q") == 0x1234, "Failed to update"
    
    print("All register tests passed!")
```

## Notes on Simulation

:::warning Feedback Loops
Registers create feedback loops in the circuit. SHDL's simulator handles this through iterative settling - it runs multiple `tick()` cycles until the circuit reaches a stable state.

For proper sequential logic with clock edges, you may need to structure your design to avoid race conditions.
:::

## Real-World Considerations

In actual hardware:
- Registers are clocked (edge-triggered)
- Setup and hold times must be respected
- Clock distribution is critical

SHDL's simplified model is great for learning the logical structure of registers without the complexity of timing analysis.
