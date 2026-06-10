# Base SHDL: Specification

*The Intermediate Representation of the SHDL Compilation Pipeline*
*github.com/rafa-rrayes/SHDL*

---

## 1. Introduction

### 1.1 What Is Base SHDL?

Base SHDL is the canonical **intermediate representation** (IR) at the heart of the SHDL compilation pipeline. It is the bridge between **Expanded SHDL** — the high-level language developers write — and the **generated C code** that performs the simulation.

Base SHDL is built on one fundamental design principle: **the structural core describes only single-bit logic**. All higher-level information — multi-bit ports, hierarchy traceability, source locations, debugger support — lives in a dedicated **metadata section** that travels with the structural description but is strictly separated from it.

This separation yields two benefits: the structural core becomes trivially simple to parse and compile, and the metadata becomes a well-defined, extensible contract between the frontend (flattener) and all downstream consumers (compiler, debugger, driver, future backends).

### 1.2 Role in the Pipeline

```
  Expanded SHDL  (what you write)
       │
       ▼
  ┌──────────────┐
  │  Flattener   │   6 sequential phases
  └──────────────┘
       │
       ▼
  Base SHDL    (this specification)
  ┌──────────────────────────────────┐
  │  Structural Core                 │  Pure single-bit logic
  │  + Metadata Section              │  Everything the tooling needs
  └──────────────────────────────────┘
       │
       ├──▶  SHDLC Compiler  ──▶  C  ──▶  Shared Library
       ├──▶  Debugger (SHDB)
       ├──▶  Python Driver (Circuit)
       └──▶  Future backends (Verilog, WASM, ...)
```

### 1.3 What Changed from v1

In v1, multi-bit port declarations like `A[16]` appeared in the structural core, so the compiler grammar, parser, and code generator all had to handle indexing and width rules. Debug metadata was a separate `.shdb` JSON file with no formal relationship to the IR.

In v2:

- The structural core contains **only single-bit port names**. A 16-bit port `A[16]` becomes 16 individual ports: `A_1_`, `A_2_`, ..., `A_16_`.
- A **metadata section** (`meta { … }`) follows the structural component and carries everything that isn't gate-level logic. The metadata is a single **JSON object** (Section 4) — there is one serialization, not two.
- The `.shdb` file *is* that metadata section verbatim (plus the compiler-added State Region layout); the metadata *is* the debug info.

---

## 2. Document Structure

A Base SHDL file has two parts:

```
┌─────────────────────────────────┐
│  STRUCTURAL CORE                │   component ... { ... }
│  Pure single-bit gate-level     │
│  logic description              │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  METADATA SECTION               │   meta { ... }
│  Port groups, hierarchy, source │
│  maps, timing, debugger config, │
│  statistics, documentation      │
└─────────────────────────────────┘
```

The structural core is **complete and self-contained** — a minimal consumer (e.g., a future Verilog backend) can parse only the structural core and ignore the metadata entirely. The metadata is **optional for parsing the circuit structure** but **required for full tooling support** (multi-bit `poke`/`peek`, hierarchy navigation, source-level debugging, `settle()`).

---

## 3. Structural Core

### 3.1 Design Principle

The structural core describes a circuit using **only single-bit wires and primitive gates**. No multi-bit ports, no indexing, no widths. Every port is a named single-bit wire. Every gate has single-bit inputs and a single-bit output. This is the most reduced possible representation of a digital circuit: a flat netlist of primitive Boolean gates connected by named wires.

### 3.2 Grammar

```ebnf
Component       = "component" IDENTIFIER
                    "(" IdentifierList ")"
                    "->"
                    "(" IdentifierList ")"
                  "{"
                    { InstanceDecl }
                    ConnectBlock
                  "}" ;

IdentifierList  = [ IDENTIFIER { "," IDENTIFIER } ] ;

InstanceDecl    = IDENTIFIER ":" PrimitiveType ";" ;
PrimitiveType   = "AND" | "OR" | "NOT" | "XOR" | "__VCC__" | "__GND__" ;

ConnectBlock    = "connect" "{" { Connection } "}" ;
Connection      = Signal "->" Signal ";" ;

Signal          = IDENTIFIER
                | IDENTIFIER "." IDENTIFIER ;
```

Key properties:

- **No `[N]` anywhere.** Ports are bare identifiers. Signals are bare identifiers or `instance.port` references.
- **Exactly one component per file** (the flattened top-level component).
- The grammar is parseable by a simple recursive-descent parser with one token of lookahead and no backtracking.

### 3.3 Primitive Types

Base SHDL has exactly **six primitive types**.

#### Logic Gates

| Gate  | Inputs   | Output | C Operator | Operation   |
|-------|----------|--------|------------|-------------|
| `AND` | `A`, `B` | `O`    | `&`        | O = A ∧ B   |
| `OR`  | `A`, `B` | `O`    | `\|`       | O = A ∨ B   |
| `NOT` | `A`      | `O`    | `~`        | O = ¬A      |
| `XOR` | `A`, `B` | `O`    | `^`        | O = A ⊕ B   |

#### Power Pins

| Pin       | Inputs   | Output | Behavior        |
|-----------|----------|--------|-----------------|
| `__VCC__` | *(none)* | `O`    | Always HIGH (1) |
| `__GND__` | *(none)* | `O`    | Always LOW (0)  |

All primitives use a consistent port convention: inputs are `A` (and `B` for two-input gates); the output is always `O`.

AND, OR, and NOT form a functionally complete set; XOR is included because it dominates arithmetic circuits and maps directly to a single C operator. Derived gates (NAND, NOR, XNOR) are compositions in Expanded SHDL and arrive in Base SHDL already decomposed.

### 3.4 Port Naming Convention for Expanded Ports

When the flattener decomposes a multi-bit port into single-bit wires:

```
{PortName}_{BitIndex}_
```

The trailing underscore is the **bus-index terminator**, distinguishing bus-expanded ports from hierarchy-flattened names (which use a single underscore separator, e.g., `fa1_x1`).

| Expanded SHDL Declaration | Base SHDL Port Names            |
|---------------------------|-------------------------------------|
| `A[4]`                    | `A_1_`, `A_2_`, `A_3_`, `A_4_`     |
| `Sum[16]`                 | `Sum_1_`, ..., `Sum_16_`            |
| `Cin` (single-bit)        | `Cin`                               |

Bit indexing remains **1-based** (LSB = bit 1), consistent with Expanded SHDL.

The `…_<digits>_` shape is **reserved**: Expanded SHDL forbids user identifiers matching it (`shdl.md` §2.2), so a bus-expanded wire such as `Sum_2_` can never collide with a user-named port. This is what lets the single trailing underscore unambiguously mark a bus index.

### 3.5 Instance Naming

| Pattern            | Example             | Origin                       |
|--------------------|---------------------|------------------------------|
| Simple name        | `x1`, `a1`          | Direct gate in top-level     |
| Hierarchy-prefixed | `fa1_x1`, `fa2_a1`  | Flattened from subcomponents |
| Deep hierarchy     | `alu1_add1_fa1_x1`  | Multi-level flattening       |
| Constant bit       | `FIVE_bit3`          | Materialized from constants  |

Names starting with `__` are reserved for system use.

### 3.6 Connection Rules

1. **Single driver.** Each gate input and each component output port has exactly one source.
2. **Fan-out allowed.** A single source may drive multiple destinations.
3. **No floating inputs.** Every gate input must be connected.
4. **No floating outputs.** Every component output must be driven.
5. **All connections are single-bit** — inherent, since every signal is a single-bit wire.

### 3.7 Complete Structural Example

A 2-bit ripple-carry adder:

```
component Add2(A_1_, A_2_, B_1_, B_2_, Cin) -> (Sum_1_, Sum_2_, Cout) {
    fa1_x1: XOR;
    fa1_x2: XOR;
    fa1_a1: AND;
    fa1_a2: AND;
    fa1_o1: OR;

    fa2_x1: XOR;
    fa2_x2: XOR;
    fa2_a1: AND;
    fa2_a2: AND;
    fa2_o1: OR;

    connect {
        A_1_ -> fa1_x1.A;
        B_1_ -> fa1_x1.B;
        A_1_ -> fa1_a1.A;
        B_1_ -> fa1_a1.B;
        fa1_x1.O -> fa1_x2.A;
        Cin -> fa1_x2.B;
        fa1_x1.O -> fa1_a2.A;
        Cin -> fa1_a2.B;
        fa1_a1.O -> fa1_o1.A;
        fa1_a2.O -> fa1_o1.B;
        fa1_x2.O -> Sum_1_;

        A_2_ -> fa2_x1.A;
        B_2_ -> fa2_x1.B;
        A_2_ -> fa2_a1.A;
        B_2_ -> fa2_a1.B;
        fa2_x1.O -> fa2_x2.A;
        fa1_o1.O -> fa2_x2.B;
        fa2_x1.O -> fa2_a2.A;
        fa1_o1.O -> fa2_a2.B;
        fa2_a1.O -> fa2_o1.A;
        fa2_a2.O -> fa2_o1.B;
        fa2_x2.O -> Sum_2_;
        fa2_o1.O -> Cout;
    }
}
```

No `[N]` indexing appears anywhere. Every port and signal is a bare identifier.

---

## 4. Metadata Section

### 4.1 Purpose and Placement

The metadata section carries everything downstream tools need that is not gate-level structure. It follows the structural core, after the component's closing brace, and its body is a single **JSON object**:

```
component Name(...) -> (...) {
    ...
}

meta {
  "version": "2.0",
  ...
}
```

There is exactly **one** serialization. The bytes between the `meta` braces are the same JSON that the `.shdb` file contains (Section 7) — the `.shdb` is produced by copying the embedded object out, not by translating a second text format. This makes it impossible for the structure and its metadata to fall out of sync, and gives every consumer one grammar (JSON) to parse instead of two.

A minimal consumer can stop reading at the component's closing brace. The full toolchain reads both.

### 4.2 Grammar Overview

The metadata section is the keyword `meta` followed by a JSON object whose top-level keys are the metadata blocks:

```ebnf
MetaSection  = "meta" JsonObject ;   (* JsonObject is standard RFC 8259 JSON *)
```

| Key          | Block                          | Status                                   |
|--------------|--------------------------------|------------------------------------------|
| `version`    | metadata format version        | recommended                              |
| `ports`      | port grouping (§4.3)           | required for multi-bit tooling           |
| `hierarchy`  | component hierarchy map (§4.4) | optional                                 |
| `source_map` | source location mapping (§4.5) | optional                                 |
| `constants`  | constant origin tracking (§4.6)| optional                                 |
| `timing`     | depth & propagation (§4.7)     | required for `settle()`                  |
| `monitors`   | debugger watch groups (§4.8)   | optional                                 |
| `stats`      | circuit statistics (§4.9)      | optional                                 |
| `doc`        | documentation/provenance (§4.10)| optional                                |
| `init`       | initial-state seeds (§4.11)    | optional                                 |

Every block is optional for *parsing the circuit structure* (a minimal consumer reads only the structural core), and the keys may appear in any order. **Unknown keys are ignored**, giving forward compatibility: a future block can be added without breaking existing tools. The `version` string lets a consumer detect the format revision it is reading. All examples below show the JSON exactly as it appears, both embedded in `meta { … }` and in the `.shdb` file.

### 4.3 `ports` — Port Grouping

*Optional for structural parsing; required for multi-bit tooling.* Maps user-facing multi-bit signal names to their constituent single-bit wires. This is what lets the driver and compiled library accept `poke("A", 42)`.

```json
"ports": {
  "inputs": {
    "A":   ["A_1_", "A_2_"],
    "B":   ["B_1_", "B_2_"],
    "Cin": ["Cin"]
  },
  "outputs": {
    "Sum":  ["Sum_1_", "Sum_2_"],
    "Cout": ["Cout"]
  }
}
```

- List order encodes bit position: index 0 = bit 1 (LSB).
- Single-bit ports map to a one-element list, keeping the representation uniform.

### 4.4 `hierarchy` — Component Hierarchy Map

Records the original hierarchy before flattening. Enables the debugger's tree view, `scope` navigation, hierarchical paths (`fa1.x1.O`), and instance inspection.

```json
"hierarchy": {
  "Add2": {
    "source_file": "add2.shdl",
    "source_line": 3,
    "instances": {
      "fa1": {
        "type": "FullAdder",
        "source_file": "fullAdder.shdl",
        "source_line": 8,
        "prefix": "fa1_",
        "ports": {
          "A": "A_1_", "B": "B_1_", "Cin": "Cin",
          "Sum": "Sum_1_", "Cout": "fa1_o1.O"
        },
        "instances": {
          "x1": { "type": "XOR", "gate": "fa1_x1" },
          "x2": { "type": "XOR", "gate": "fa1_x2" },
          "a1": { "type": "AND", "gate": "fa1_a1" },
          "a2": { "type": "AND", "gate": "fa1_a2" },
          "o1": { "type": "OR",  "gate": "fa1_o1" }
        }
      },
      "fa2": { }
    }
  }
}
```

The `ports` sub-object within each instance maps the instance's interface ports to the actual structural wires — essential for `print fa1.A` and connection inspection. For an instance of a parameterized component (`shdl.md` §4.4), record the bound parameter values alongside `type` (e.g. `"params": { "N": 8 }`) so the debugger can show the specialization.

### 4.5 `source_map` — Source Location Mapping

Maps gates back to their origin in the Expanded SHDL sources, in both directions (gate → location, and location → gates), since the debugger uses both frequently.

```json
"source_map": {
  "gates": {
    "fa1_x1": { "file": "fullAdder.shdl", "line": 3, "column": 5 },
    "fa1_x2": { "file": "fullAdder.shdl", "line": 3, "column": 16 }
  },
  "lines": {
    "fullAdder.shdl": {
      "3": ["fa1_x1", "fa1_x2", "fa2_x1", "fa2_x2"],
      "4": ["fa1_a1", "fa1_a2", "fa2_a1", "fa2_a2"]
    },
    "add2.shdl": {
      "8": ["fa1_x1", "fa1_x2", "fa1_a1", "fa1_a2", "fa1_o1"],
      "9": ["fa2_x1", "fa2_x2", "fa2_a1", "fa2_a2", "fa2_o1"]
    }
  }
}
```

The two directions (`gates` and `lines`) are redundant by construction — `lines` is the inverse of `gates`. The flattener emits both because the debugger queries each frequently; a consumer that edits one must regenerate the other rather than hand-maintain it.

### 4.6 `constants` — Constant Origin Tracking

Records which `__VCC__`/`__GND__` instances came from named constants, so the debugger can display `FIVE = 5` instead of raw power-pin states.

```json
"constants": {
  "FIVE": {
    "value": 5,
    "width": 3,
    "bits": {
      "1": "FIVE_bit1",
      "2": "FIVE_bit2",
      "3": "FIVE_bit3"
    }
  }
}
```

`bits` lists only the bits that were actually referenced and therefore materialized (`shdl.md` §8): an unreferenced high bit of a constant has no power-pin instance, since a constant is conceptually an unbounded unsigned value whose leading bits are all 0.

### 4.7 `timing` — Circuit Depth and Propagation

The combinational depth information computed during flattening/analysis. This is what makes `settle()` possible and propagation delay visible.

```json
"timing": {
  "max_depth": 5,
  "output_depths": { "Sum_1_": 3, "Sum_2_": 5, "Cout": 5 },
  "is_combinational": true,
  "has_feedback": false,
  "critical_path": ["A_1_", "fa1_x1", "fa1_o1", "fa2_x2", "fa2_o1", "Cout"]
}
```

- `max_depth` is the minimum number of simulation cycles for all outputs to reflect current inputs under SHDL's one-gate-level-per-cycle semantics.
- `has_feedback` tells the driver whether `settle()` can safely converge.
- Depths are computed on the feedback-free subgraph (feedback edges excluded from longest-path analysis).
- **Under feedback (`has_feedback = true`)** `max_depth` is the depth of the feedback-free shell *only*; it is **not** a settle count, since a circuit with feedback has no guaranteed fixed point. In that case `settle()` is disabled and the circuit must be advanced explicitly with `step(n)` (`shdl.md` §11.3).

### 4.8 `monitors` — Debugger Watch Configuration

Named groups of signals worth observing together, populated automatically by the flattener or via user annotations.

```json
"monitors": {
  "carry_chain": ["fa1_o1", "fa2_o1"]
}
```

Enables `watch :carry_chain`, `record signals :carry_chain`, and grouped display panels in SHDB.

### 4.9 `stats` — Circuit Statistics

```json
"stats": {
  "total_gates": 10,
  "total_connections": 22,
  "total_ports": 8,
  "by_type": { "XOR": 4, "AND": 4, "OR": 2 }
}
```

### 4.10 `doc` — Documentation and Provenance

```json
"doc": {
  "description": "2-bit ripple-carry adder",
  "author": "rafa-rrayes",
  "source": "add2.shdl",
  "flattened_at": "2026-06-10T14:30:00Z"
}
```

### 4.11 `init` — Initial State

Records the power-on value of any net seeded by an Expanded SHDL `init` block (`shdl.md` §11.4). Every wire defaults to 0 at cycle 0; this block lists only the nets given a different seed, so the compiler can initialize the State Region and the debugger can display the power-on state.

```json
"init": {
  "n1.O": 0,
  "n2.O": 1
}
```

- Keys are structural signals (an instance output `inst.O`, or a component output port). Multi-bit ports seeded in the source are recorded here already expanded to their single-bit wires (`Out_1_`, `Out_2_`, …).
- Values are `0` or `1`. A net absent from this block holds the default of `0`.
- `init` carries no logic — it is purely the value present before the first `step`; subsequent cycles evolve from the gate netlist alone.

---

## 5. How Each Consumer Uses the Metadata

| Consumer            | Blocks Used                                  | Purpose                                            |
|---------------------|----------------------------------------------|----------------------------------------------------|
| SHDLC (release)     | `ports`, `init`                              | Generate `poke()`/`peek()` with user-facing names; seed power-on state |
| SHDLC (debug)       | all                                          | Code generation + write `.shdb`                     |
| Python Driver       | `ports`, `timing`, `init`                    | Multi-bit poke/peek; `settle()`; reset to power-on state |
| SHDB Debugger       | all                                          | Hierarchy, source display, watch groups, constants, power-on state |
| External observers  | `ports`, `stats` + State Region layout (.shdb) | Shared-memory interpretation                      |
| Future backends     | `ports`                                      | Reconstruct multi-bit declarations                  |

---

## 6. Constraints Summary

### Structural Core

| Constraint                      | Rationale                                  |
|---------------------------------|--------------------------------------------|
| No multi-bit ports or `[N]`     | Single-bit wires are the true atomic unit   |
| No component parameters         | Bound and specialized during monomorphization |
| No user-defined component types | All hierarchy is flattened                   |
| No generators, conditionals, slices, or concatenation | All repetition, selection, slicing, and grouping is expanded |
| No named constants              | Replaced by `__VCC__`/`__GND__` instances    |
| No `init` blocks                | Power-on seeds live in metadata (`init`, §4.11) |
| No imports / comments           | Pure structural description                  |
| Exactly one component           | The flattened top-level                      |
| Only six primitive types        | AND, OR, NOT, XOR, `__VCC__`, `__GND__`      |
| No `…_<digits>_` user names     | Reserved for bus expansion (§3.4)            |

### Metadata

| Constraint                                | Rationale                                  |
|-------------------------------------------|---------------------------------------------|
| All blocks optional                        | Graceful degradation for minimal consumers |
| Unknown blocks ignored                     | Forward compatibility                       |
| All names referenced must exist in the core| Consistency between the two halves          |

---

## 7. Serialization

There is a **single** serialization for metadata: JSON. The object between the `meta` braces embedded in the Base SHDL file and the contents of the standalone `.shdb` file are the same bytes — the `.shdb` is produced by lifting the embedded object out and appending the compiler-added **State Region layout** (`state_region`), which is the only field the flattener does not itself emit. There is no second, text-only encoding to keep in sync.

```json
{
  "version": "2.0",
  "ports": {
    "inputs":  { "A": ["A_1_", "A_2_"], "B": ["B_1_", "B_2_"], "Cin": ["Cin"] },
    "outputs": { "Sum": ["Sum_1_", "Sum_2_"], "Cout": ["Cout"] }
  },
  "hierarchy":  { },
  "source_map": { },
  "constants":  { },
  "timing":     { "max_depth": 5, "is_combinational": true },
  "monitors":   { },
  "stats":      { },
  "doc":        { },
  "init":       { },
  "state_region": { }
}
```

The debugger, driver, and any external tool load one format. Because the embedded metadata and the `.shdb` are the same object, the structure and its metadata cannot fall out of sync.

---

## 8. Design Rationale

**Why remove multi-bit ports from the structural core?** The core's job is to describe logic, and logic operates on single bits. A multi-bit port is a convenience grouping, not a structural primitive. Moving it to metadata makes the structural grammar simpler (no indexing rules, no bounds checking) and more honest about what it is: a flat netlist of Boolean gates.

**Why embed the metadata rather than a separate file?** Embedding makes it impossible for the structure and metadata to fall out of sync. The JSON `.shdb` is the embedded object lifted out verbatim (plus the State Region layout), never generated independently.

**Why a single JSON serialization rather than a human-readable text form *and* JSON?** Two encodings of the same information mean two grammars, two parsers, and a translation step that can drift — and the text form's grammar was never fully specified, only shown by example. Collapsing to one canonical format (JSON, which every consumer already reads) removes the drift risk entirely and leaves nothing to translate. JSON is readable enough embedded in the file; the structural core above it remains the human-facing part.

**Why `PortName_N_`?** The trailing underscore disambiguates bus-expanded ports from hierarchy-flattened gate names without introducing new syntax characters. Alternatives like `PortName.N` (conflicts with `instance.port`) and `PortName#N` (conflicts with comments) were considered and rejected. The scheme is safe because the `…_<digits>_` pattern is **reserved** in Expanded SHDL (§3.4; `shdl.md` §2.2), so no user identifier can collide with a bus-expanded wire.

**Why include timing?** The single most common usability problem in SHDL v1 was users guessing how many `step()` calls a circuit needs. With `max_depth` in the metadata, the driver implements `settle()` definitively — without compromising SHDL's gate-level, one-level-per-cycle simulation model.

**Why keep `init` in metadata rather than the structural core?** Initial state is a power-on *value*, not a gate. Putting it in the core would mean either inventing a stateful primitive or letting wires carry annotations — both of which would compromise the core's one job: describing single-bit Boolean logic. As metadata, the seed reaches exactly the consumers that need it (the compiler seeds the State Region, the driver resets to it, the debugger displays it) while the netlist stays a pure netlist. Every wire still defaults to 0, so a circuit with no `init` block needs no `init` metadata at all.