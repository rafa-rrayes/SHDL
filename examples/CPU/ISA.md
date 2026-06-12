# SR16 — a 16-bit RISC CPU in SHDL

SR16 is a load-store RISC processor built entirely from SHDL primitive gates.
This document is the **specification of record**: the control unit
(`control.shdl`), the assembler (`sr16tools/asm.py`) and the golden model
(`sr16tools/golden.py`) all implement exactly what is written here.

Bit numbering in this document is **conventional**: bit 15 = MSB, bit 0 = LSB.
(SHDL source indexes the same wires 1-based: SHDL bit *k* = conventional bit
*k−1*.)

---

## 1. Programmer's model

| Resource | Description |
|----------|-------------|
| `R0`–`R7` | Eight 16-bit general-purpose registers |
| `R7` = SP | Stack pointer by convention: PUSH/POP/CALL/RET use it implicitly; it remains a normal GPR otherwise |
| `PC` | 16-bit program counter (wraps mod 2^16) |
| `FLAGS` | Z (zero), N (negative), C (carry), V (signed overflow) |
| Memory | Word-addressed (16-bit words), unified code+data. Physical size 2^A words (parameter `A`, default 8 → 256 words); the low A bits of every address select the word (addresses alias mod 2^A) |

Power-on / reset state: every latch is 0 → `PC = 0`, all registers 0, flags 0,
FSM in FETCH, not halted. Execution starts at address 0. With `R7 = 0`, the
first PUSH writes to `(0 − 1) mod 2^16` → top word of RAM: the stack grows
down from the top of memory by default.

The stack convention is **full-descending**: PUSH pre-decrements
(`R7 -= 1; MEM[R7] = value`), POP post-increments (`value = MEM[R7]; R7 += 1`).

## 2. Instruction formats

All instructions are one 16-bit word.

| Format | 15:12 | 11:9 | 8:6 | 5:3 | 2:0 |
|--------|-------|------|-----|-----|-----|
| R      | op    | rd   | rs1 | rs2 | funct |
| I8     | op    | rd   | x, imm8 in [7:0] | | |
| M      | op    | rd / rs2 | rs1 | simm6 in [5:0] | |
| B      | op    | cond | simm9 in [8:0] | | |
| J      | op    | imm12 in [11:0] | | | |

`simm6`/`simm8`/`simm9` are two's-complement sign-extended; `imm12` is
zero-extended. `x` = ignored on decode, assemble as 0.

## 3. Opcode map

| op (15:12) | Group | Format |
|------------|-------------|--------|
| `0000` | ALU register ops | R |
| `0001` | Shift/unary ops | R (rs2 ignored) |
| `0010` | LDI  `rd, imm8` | I8 |
| `0011` | LDIH `rd, imm8` | I8 |
| `0100` | LD  `rd, [rs1+simm6]` | M |
| `0101` | ST  `[rs1+simm6], rs2` | M (rs2 in [11:9]) |
| `0110` | ADDI `rd, rs1, simm6` | M |
| `0111` | Bcc `simm9` | B |
| `1000` | JMP `imm12` | J |
| `1001` | CALL `imm12` | J |
| `1010` | MISC (stack / control) | R-ish |
| `1011`–`1111` | **Reserved** — executing one HALTs the CPU | |

### 3.1 ALU group (op = 0000), funct:

| funct | Mnemonic | Semantics | Flags |
|-------|----------|-----------|-------|
| 000 | `ADD rd, rs1, rs2` | rd = rs1 + rs2 | Z N C V |
| 001 | `SUB rd, rs1, rs2` | rd = rs1 − rs2 (= rs1 + ~rs2 + 1) | Z N C V |
| 010 | `AND rd, rs1, rs2` | rd = rs1 & rs2 | Z N |
| 011 | `OR  rd, rs1, rs2` | rd = rs1 \| rs2 | Z N |
| 100 | `XOR rd, rs1, rs2` | rd = rs1 ^ rs2 | Z N |
| 101 | `MOV rd, rs1` | rd = rs1 (rs2 ignored) | — |
| 110 | `CMP rs1, rs2` | flags of rs1 − rs2, no writeback (rd ignored) | Z N C V |
| 111 | `ADC rd, rs1, rs2` | rd = rs1 + rs2 + C | Z N C V |

Carry semantics: for ADD/ADC, C = carry out of bit 15. For SUB/CMP, C = carry
out of `rs1 + ~rs2 + 1` (C = 1 ⇔ **no borrow** ⇔ rs1 ≥ rs2 unsigned — ARM
convention). V = signed two's-complement overflow of the operation.

### 3.2 Shift group (op = 0001), funct (rs2 ignored):

| funct | Mnemonic | Semantics | Flags |
|-------|----------|-----------|-------|
| 000 | `SHL rd, rs1` | rd = rs1 << 1 | Z N, C = old bit 15 |
| 001 | `SHR rd, rs1` | logical right; bit 15 ← 0 | Z N, C = old bit 0 |
| 010 | `SAR rd, rs1` | arithmetic right; bit 15 preserved | Z N, C = old bit 0 |
| 011 | `ROL rd, rs1` | rotate left; bit 0 ← old bit 15 | Z N, C = old bit 15 |
| 100 | `ROR rd, rs1` | rotate right; bit 15 ← old bit 0 | Z N, C = old bit 0 |
| 101 | `NOT rd, rs1` | rd = ~rs1 | Z N |
| 110, 111 | reserved | behave exactly as NOT — **do not use** | Z N |

V is never changed by this group. NOT does not change C.

### 3.3 Immediates (op = 0010 / 0011)

| Mnemonic | Semantics | Flags |
|----------|-----------|-------|
| `LDI rd, imm8` | rd = signext(imm8) | — |
| `LDIH rd, imm8` | rd = (imm8 << 8) \| (rd & 0x00FF) | — |

Any 16-bit constant k: `LDI rd, k&0xFF` then `LDIH rd, k>>8`
(LDIH overwrites the whole high byte, so LDI's sign extension never leaks).
The assembler pseudo-op `LI rd, k` emits this pair (or a single LDI when k
fits in a signed 8-bit immediate).

### 3.4 Memory (op = 0100 / 0101 / 0110)

| Mnemonic | Semantics | Flags |
|----------|-----------|-------|
| `LD rd, [rs1+simm6]` | rd = MEM[(rs1 + signext(simm6)) mod 2^16] | — |
| `ST [rs1+simm6], rs2` | MEM[(rs1 + signext(simm6)) mod 2^16] = rs2 | — |
| `ADDI rd, rs1, simm6` | rd = rs1 + signext(simm6) | Z N C V |

### 3.5 Branches (op = 0111)

`Bcc simm9` — if the condition holds, `PC = addr_of_branch + 1 + signext(simm9)`.
(The assembler computes `simm9 = target − (branch_addr + 1)`.)

| cond | Mnemonic | Taken when | After `CMP a, b` means |
|------|----------|------------|-------------------------|
| 000 | `BEQ` | Z = 1 | a == b |
| 001 | `BNE` | Z = 0 | a != b |
| 010 | `BCS` / `BHS` | C = 1 | a ≥ b (unsigned) |
| 011 | `BCC` / `BLO` | C = 0 | a < b (unsigned) |
| 100 | `BMI` | N = 1 | result negative |
| 101 | `BPL` | N = 0 | result non-negative |
| 110 | `BLT` | N ≠ V | a < b (signed) |
| 111 | `BGE` | N = V | a ≥ b (signed) |

There is no BGT/BLE; synthesize with `BEQ` + `BLT`/`BGE` pairs. Unconditional
jumps use `JMP`.

### 3.6 Jumps (op = 1000 / 1001)

| Mnemonic | Semantics |
|----------|-----------|
| `JMP imm12` | PC = imm12 |
| `CALL imm12` | R7 −= 1; MEM[R7] = return address (addr of CALL + 1); PC = imm12 |

### 3.7 MISC group (op = 1010), funct:

| funct | Mnemonic | Register field | Semantics |
|-------|----------|----------------|-----------|
| 000 | `PUSH rs` | rs in [11:9] | R7 −= 1; MEM[R7] = rs |
| 001 | `POP rd`  | rd in [11:9] | rd = MEM[R7]; R7 += 1 |
| 010 | `RET`     | — | PC = MEM[R7]; R7 += 1 |
| 011 | `JR rs`   | rs in [8:6]  | PC = rs |
| 100 | `NOP`     | — | nothing (encoding `0xA004`) |
| 101 | `HALT`    | — | enter HALTED state (encoding `0xA005`) |
| 110, 111 | reserved | — | behave as HALT — do not use |

No MISC instruction changes flags. `PUSH R7` stores the *old* R7 value;
`POP R7` loads the popped value (the SP increment is overridden by the load,
i.e. the final R7 is the value read from memory).

## 4. Microarchitecture

Multi-cycle FSM, 2-bit state register:

| State | # | Work done in the cycle | Next |
|-------|---|------------------------|------|
| FETCH | 0 | IR ← MEM[PC]; PC ← PC + 1 | EXEC |
| EXEC  | 1 | Everything in §3, except that POP/RET only do `R7 ← R7 + 1` here | FETCH, or MEMRD (POP/RET), or HALTED (HALT/reserved) |
| MEMRD | 2 | POP: rd ← MEM[R7−1]; RET: PC ← MEM[R7−1] | FETCH |
| HALTED| 3 | nothing; `Halted` output pin = 1 | HALTED |

Instruction cost: POP and RET take 3 clocks, everything else 2 clocks.

Within EXEC, simultaneous writes go to distinct resources, so one cycle
suffices even for CALL (RAM write port + R7 via the register-file write port +
PC register). POP needs both `rd ← MEM[old R7]` and `R7 ← R7+1` through the
single register-file write port — hence two cycles: the SP increment lands
first (EXEC), then MEMRD reads through `R7−1` (= the old R7) and writes rd.
The net effect equals §3.7, and `POP R7` ends with the loaded value.

Reserved opcodes (`1011`–`1111`) and reserved MISC functs decode to HALT so a
wild PC traps loudly instead of executing garbage.

## 5. Clocking: two-phase non-overlapping

All state elements are master-slave pairs of D latches:

- **phi1** high: master latches (and RAM cell latches) capture their inputs.
- **phi2** high: slave latches publish the captured values to the outputs.

RAM cells strobe on **phi1** (like masters): write data is a combinational
function of slave outputs, which are stable while phi2 is low.

The driver produces one clock cycle as:

```
poke phi1=1; step(T_CAP)   # masters + RAM cells capture
poke phi1=0; step(T_GAP)
poke phi2=1; step(T_CAP)   # slaves publish
poke phi2=0; step(T_SETTLE)  # combinational logic settles for the next cycle
```

`T_CAP`/`T_GAP`/`T_SETTLE` are pinned in `sr16tools/driver.py` and guarded by a
test that doubles them and asserts the architectural trace is unchanged.

## 6. Top-level pins (`sr16.shdl`, component `SR16<A = 8>`)

Inputs:

| Pin | Width | Purpose |
|-----|-------|---------|
| `Phi1`, `Phi2` | 1 | the two clock phases |
| `LdEn` | 1 | DMA mode: freezes the CPU (all CPU state-write enables masked) and steers the RAM address to `LdAddr` |
| `LdWe` | 1 | DMA write strobe (with `LdEn=1`, a phi1 pulse writes `LdData` to `MEM[LdAddr]`) |
| `LdAddr` | 16 | DMA address |
| `LdData` | 16 | DMA write data |

Outputs (debug/observability — all architectural state is peekable):

| Pin | Width | Meaning |
|-----|-------|---------|
| `Halted` | 1 | FSM in HALTED |
| `PCout` | 16 | PC |
| `IRout` | 16 | IR |
| `Flags` | 4 | {V,C,N,Z} (Z = bit 0) |
| `State` | 2 | FSM state |
| `MemOut` | 16 | RAM read port (DMA read: `LdEn=1, LdWe=0`, poke `LdAddr`, settle, peek) |
| `R0out`…`R7out` | 16 each | register file contents |

Program load protocol: `reset()`; for each word: poke `LdAddr`/`LdData`,
`LdEn=1`, `LdWe=1`, pulse phi1 (with settle before the pulse); then
`LdEn=LdWe=0` and start clocking. The CPU is frozen during load, so it
afterwards begins cleanly at PC = 0.
