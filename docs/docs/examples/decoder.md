---
sidebar_position: 6
---

# Decoder

A decoder converts a binary-encoded input into a one-hot output where exactly one output bit is high.

## 2-to-4 Decoder

A 2-bit input selects one of 4 outputs:

```
component Decoder2to4(A[2]) -> (Y[4]) {
    # Inverters for complement signals
    notA1: NOT;
    notA2: NOT;
    
    # AND gates for each output
    and1: AND;  # Y[1] = ~A[2] & ~A[1]  (input 00)
    and2: AND;  # Y[2] = ~A[2] &  A[1]  (input 01)
    and3: AND;  # Y[3] =  A[2] & ~A[1]  (input 10)
    and4: AND;  # Y[4] =  A[2] &  A[1]  (input 11)
    
    connect {
        # Generate complements
        A[1] -> notA1.A;
        A[2] -> notA2.A;
        
        # Y[1]: selected when A = 00
        notA2.O -> and1.A;
        notA1.O -> and1.B;
        and1.O -> Y[1];
        
        # Y[2]: selected when A = 01
        notA2.O -> and2.A;
        A[1] -> and2.B;
        and2.O -> Y[2];
        
        # Y[3]: selected when A = 10
        A[2] -> and3.A;
        notA1.O -> and3.B;
        and3.O -> Y[3];
        
        # Y[4]: selected when A = 11
        A[2] -> and4.A;
        A[1] -> and4.B;
        and4.O -> Y[4];
    }
}
```

## Truth Table

| A[2] | A[1] | Y[1] | Y[2] | Y[3] | Y[4] |
|------|------|------|------|------|------|
| 0 | 0 | 1 | 0 | 0 | 0 |
| 0 | 1 | 0 | 1 | 0 | 0 |
| 1 | 0 | 0 | 0 | 1 | 0 |
| 1 | 1 | 0 | 0 | 0 | 1 |

## How It Works

Each output `Y[i]` corresponds to a specific input combination. For a 2-to-4 decoder:

- `Y[1]` = active when input is `00` → needs `~A[2] AND ~A[1]`
- `Y[2]` = active when input is `01` → needs `~A[2] AND A[1]`
- `Y[3]` = active when input is `10` → needs `A[2] AND ~A[1]`
- `Y[4]` = active when input is `11` → needs `A[2] AND A[1]`

## 3-to-8 Decoder

Extending to 3 inputs and 8 outputs:

```
component Decoder3to8(A[3]) -> (Y[8]) {
    # Inverters
    >i[3]{
        not{i}: NOT;
    }
    
    # 8 AND gates (each needs 3 inputs, so we chain ANDs)
    >i[8]{
        and{i}_1: AND;  # First pair
        and{i}_2: AND;  # Combine with third
    }
    
    connect {
        # Generate complements
        >i[3]{
            A[{i}] -> not{i}.A;
        }
        
        # Y[1]: 000 -> ~A[3] & ~A[2] & ~A[1]
        not3.O -> and1_1.A;
        not2.O -> and1_1.B;
        and1_1.O -> and1_2.A;
        not1.O -> and1_2.B;
        and1_2.O -> Y[1];
        
        # Y[2]: 001 -> ~A[3] & ~A[2] & A[1]
        not3.O -> and2_1.A;
        not2.O -> and2_1.B;
        and2_1.O -> and2_2.A;
        A[1] -> and2_2.B;
        and2_2.O -> Y[2];
        
        # Y[3]: 010 -> ~A[3] & A[2] & ~A[1]
        not3.O -> and3_1.A;
        A[2] -> and3_1.B;
        and3_1.O -> and3_2.A;
        not1.O -> and3_2.B;
        and3_2.O -> Y[3];
        
        # Y[4]: 011 -> ~A[3] & A[2] & A[1]
        not3.O -> and4_1.A;
        A[2] -> and4_1.B;
        and4_1.O -> and4_2.A;
        A[1] -> and4_2.B;
        and4_2.O -> Y[4];
        
        # Y[5]: 100 -> A[3] & ~A[2] & ~A[1]
        A[3] -> and5_1.A;
        not2.O -> and5_1.B;
        and5_1.O -> and5_2.A;
        not1.O -> and5_2.B;
        and5_2.O -> Y[5];
        
        # Y[6]: 101 -> A[3] & ~A[2] & A[1]
        A[3] -> and6_1.A;
        not2.O -> and6_1.B;
        and6_1.O -> and6_2.A;
        A[1] -> and6_2.B;
        and6_2.O -> Y[6];
        
        # Y[7]: 110 -> A[3] & A[2] & ~A[1]
        A[3] -> and7_1.A;
        A[2] -> and7_1.B;
        and7_1.O -> and7_2.A;
        not1.O -> and7_2.B;
        and7_2.O -> Y[7];
        
        # Y[8]: 111 -> A[3] & A[2] & A[1]
        A[3] -> and8_1.A;
        A[2] -> and8_1.B;
        and8_1.O -> and8_2.A;
        A[1] -> and8_2.B;
        and8_2.O -> Y[8];
    }
}
```

## With Enable

Add an enable signal that disables all outputs when low:

```
component Decoder2to4Enable(A[2], En) -> (Y[4]) {
    notA1: NOT;
    notA2: NOT;
    
    # First stage: decode
    dec1: AND;
    dec2: AND;
    dec3: AND;
    dec4: AND;
    
    # Second stage: AND with enable
    >i[4]{
        out{i}: AND;
    }
    
    connect {
        A[1] -> notA1.A;
        A[2] -> notA2.A;
        
        notA2.O -> dec1.A;
        notA1.O -> dec1.B;
        
        notA2.O -> dec2.A;
        A[1] -> dec2.B;
        
        A[2] -> dec3.A;
        notA1.O -> dec3.B;
        
        A[2] -> dec4.A;
        A[1] -> dec4.B;
        
        # Gate outputs with enable
        dec1.O -> out1.A;
        En -> out1.B;
        out1.O -> Y[1];
        
        dec2.O -> out2.A;
        En -> out2.B;
        out2.O -> Y[2];
        
        dec3.O -> out3.A;
        En -> out3.B;
        out3.O -> Y[3];
        
        dec4.O -> out4.A;
        En -> out4.B;
        out4.O -> Y[4];
    }
}
```

## Testing with PySHDL

```python
from SHDL import SHDLCircuit

with SHDLCircuit("decoder.shdl") as dec:
    for i in range(4):
        dec.poke("A", i + 1)  # Remember: SHDL uses 1-based!
        dec.step()
        
        y = dec.peek("Y")
        expected = 1 << i  # One-hot encoding
        
        print(f"A={i}: Y={y:04b} (expected {expected:04b})")
        assert y == expected
    
    print("All decoder tests passed!")
```

## Common Uses

Decoders are fundamental building blocks used in:

- **Memory addressing** - Select which memory cell to read/write
- **Instruction decoding** - Determine which operation to perform
- **Demultiplexing** - Route one signal to one of many destinations
- **Seven-segment displays** - Convert binary to display segments
