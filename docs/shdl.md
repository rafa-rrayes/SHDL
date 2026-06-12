# SHDL: Specification

*The High-Level Hardware Description Language*
*github.com/rafa-rrayes/SHDL*

---

## 1. Introduction

### 1.1 What Is SHDL?

SHDL (Simple Hardware Description Language) is a minimalist language for describing digital circuits in terms of logic gates. It is the language developers actually write: it offers reusable, **parameterized** hierarchical **components**, multi-bit **ports**, **generators** (with compile-time **conditionals**) for repetitive structure, bit **slices** and **concatenation**, named **constants**, optional **initial state**, and **imports** — all of which keep real designs compact and readable.

SHDL is built on one design principle: **every circuit is ultimately a netlist of single-bit primitive gates**, and every high-level convenience in the language exists only to *write that netlist more concisely*. There are no behavioral abstractions, no implicit state elements, no synthesizable arithmetic operators — only gates, wires, and mechanical ways to repeat them. This keeps the mental model identical to the hardware: what you write is what is built.

This document specifies the full language. Within the compilation pipeline this language is also called **Expanded SHDL**, to contrast it with **Base SHDL** — the flattened, single-bit intermediate representation it lowers to (see [`base_shdl.md`](base_shdl.md)).

### 1.2 Role in the Pipeline

SHDL is the **front-end** of the toolchain. Everything downstream consumes Base SHDL, never SHDL directly:

```
  SHDL  (this specification — what you write)
  ┌────────────────────────────────────────┐
  │  Components, hierarchy, multi-bit ports │
  │  generators, slices, constants, imports │
  └────────────────────────────────────────┘
       │
       ▼
  ┌──────────────┐
  │  Flattener   │   6 sequential phases (§12)
  └──────────────┘
       │
       ▼
  Base SHDL    (intermediate representation)
       │
       ├──▶  SHDLC Compiler  ──▶  C  ──▶  Shared Library
       ├──▶  Debugger (SHDB)
       ├──▶  Python Driver (Circuit)
       └──▶  Future backends (Verilog, WASM, ...)
```

A circuit author works entirely in SHDL. The flattener mechanically removes every high-level construct, emitting an equivalent Base SHDL netlist plus the metadata that lets the tooling recover the high-level view (port groups, hierarchy, source maps).

### 1.3 Relationship to Base SHDL

SHDL and Base SHDL share the same structural grammar — `component … { instances; connect { … } }` — but SHDL *adds* a layer of authoring constructs on top of it. The relationship is exact and total: every SHDL feature has a defined Base SHDL expansion (§12), and a circuit with none of the high-level features is already valid Base SHDL.

| Capability                       | SHDL (this doc)                     | Base SHDL                          |
|----------------------------------|-------------------------------------|------------------------------------|
| User-defined component types     | ✓ (instantiated, hierarchical)      | ✗ (all inlined)                    |
| Parameterized components `Foo<N>`| ✓                                   | ✗ (bound to concrete widths)       |
| Multi-bit ports `A[16]`          | ✓                                   | ✗ (split into `A_1_ … A_16_`)      |
| Bit indexing / slices            | ✓ (`A[3]`, `A[:4]`)                 | ✗ (all explicit single bits)       |
| Concatenation `{hi, lo}`         | ✓                                   | ✗ (split into single-bit wires)    |
| Generators `>i[N]{ … }`          | ✓                                   | ✗ (fully unrolled)                 |
| Conditional generators `when{…}` | ✓                                   | ✗ (resolved at flatten time)       |
| Named constants                  | ✓ (`FIVE = 5`)                      | ✗ (`__VCC__`/`__GND__` instances)  |
| Initial state `init { … }`       | ✓                                   | ✗ (lowered to metadata)            |
| Imports / standard library       | ✓ (`use …`)                         | ✗ (resolved away)                  |
| Comments                         | ✓                                   | ✗ (stripped)                       |
| Multiple components per file     | ✓                                   | ✗ (exactly one)                    |
| Primitive gates, `connect` block | ✓                                   | ✓                                  |

---

## 2. Lexical Structure

SHDL source is **UTF-8** text. A source file that does not decode as UTF-8 is rejected at the **read boundary**, before any lexing, with a positioned diagnostic that reports the byte offset of the first undecodable byte (E0101); the lexer never sees a partially decoded stream. The lexer then produces a flat token stream; whitespace (spaces, tabs, newlines) is insignificant except as a token separator.

### 2.1 Comments

SHDL supports three comment forms, all of which are discarded before parsing:

```
# Hash comment — runs to end of line.

A -> B;   # may also trail a statement

"a double-quoted string is a single-line comment"

"""
A triple-quoted string is a multi-line comment,
useful for documentation blocks.
"""
```

String-literal comments (`"..."` and `"""..."""`) are a deliberate convenience: SHDL has no string *values*, so any quoted text is unambiguously a comment.

### 2.2 Identifiers

```ebnf
IDENTIFIER = (LETTER | "_") { LETTER | DIGIT | "_" } ;
LETTER     = "A" … "Z" | "a" … "z" ;   (* ASCII only *)
DIGIT      = "0" … "9" ;               (* ASCII only *)
```

- `LETTER` and `DIGIT` are **ASCII**: `[A-Za-z]` and `[0-9]`. Although source files are UTF-8, the *lexical alphabet* is ASCII — identifiers, numbers, and operators use only ASCII characters. Non-ASCII characters appear legally only inside comments (which are discarded). Any other non-whitespace character outside a comment — a Unicode letter, a Unicode or superscript digit, or any stray symbol — is a lexical error (E0101), never an identifier or a number.
- Case-sensitive: `MyGate` ≠ `mygate`.
- Name components, instances, ports, constants, and generator variables.
- **Identifiers beginning with `__` (double underscore) are reserved** for system use — the power pins `__VCC__` and `__GND__` are the only such names. User code must not introduce them.
- **Identifiers matching the pattern `…_<digits>_`** — any name ending in an underscore, one or more digits, and a closing underscore (e.g. `Sum_2_`) — are **reserved** for the flattener's bus expansion (§12; `base_shdl.md` §3.4). User code must not introduce them, because a single-bit port literally named `Sum_2_` would collide with the second bit of a bus `Sum[2]`. Violations are reported as naming errors (E03xx).

### 2.3 Numeric Literals

Numbers appear as port/constant widths, constant values, range bounds, and bit indices.

| Form        | Prefix      | Example      | Value |
|-------------|-------------|--------------|-------|
| Decimal     | *(none)*    | `100`        | 100   |
| Hexadecimal | `0x` / `0X` | `0x64`       | 100   |
| Binary      | `0b` / `0B` | `0b01100100` | 100   |

All literals are non-negative integers. There are no floating-point, signed, or string-valued literals.

### 2.4 Operators and Delimiters

| Symbol | Name        | Purpose                                            |
|--------|-------------|----------------------------------------------------|
| `->`   | arrow       | connection (source → destination)                  |
| `::`   | scope       | module scope in `use`                              |
| `.`    | dot         | instance-port access (`gate1.O`)                   |
| `>`    | generator   | introduces a generator                             |
| `=`    | equals      | constant assignment; `init` and parameter defaults |
| `:`    | colon       | instance type separator, range/slice separator     |
| `;`    | semicolon   | statement terminator                               |
| `,`    | comma       | list separator                                     |
| `{ }`  | braces      | blocks, generator bodies, `{expr}` substitutions, concatenation |
| `[ ]`  | brackets    | widths, indices, slices, generator ranges          |
| `( )`  | parens      | port lists                                         |
| `< >`  | angle brackets | component parameter list (`Adder<N>`)           |
| `+ - * /` | arithmetic | expressions inside `{ }` and indices             |

The following operators are **compile-time only** — they appear solely inside `{ }` substitution and `when` conditions and never reach a gate:

| Symbol               | Name        | Purpose                                       |
|----------------------|-------------|-----------------------------------------------|
| `== != < <= > >=`    | relational  | compare integers in a `when` condition (§7.7) |
| `&& \|\|`            | boolean     | combine comparisons in a `when` condition     |

Note the contextual overloading of `<`/`>`: angle brackets delimit a parameter list (after a component name); `>` at statement start introduces a generator; and `<`/`>` inside a `when { … }` condition are relational operators. The three contexts never overlap, so one token of lookahead disambiguates them.

### 2.5 Reserved Keywords

Seven words are reserved: **`component`**, **`use`**, **`connect`**, **`init`**, **`when`**, **`else`**, and **`top`**. Primitive gate names (`AND`, `OR`, `NOT`, `XOR`, `__VCC__`, `__GND__`) are predefined component types, not keywords — but they may **not** be redefined: declaring `component AND(…) { … }` is a primitive-shadowing error (E0305), since it would shadow a primitive. When the shadowed primitive is one of the dunder pins (`component __VCC__(…)` or `component __GND__(…)`), the name violates *both* the primitive-shadowing rule (E0305) and the reserved-`__…`-name rule (E0303); the more specific **E0305 takes precedence** — the diagnostic reports the shadowing, not the reserved prefix.

---

## 3. Module Structure

A `.shdl` file is a **module**. A module contains, in order:

1. Zero or more **import** statements (§9).
2. One or more **component** definitions (§4).

```ebnf
Module = { Import } { Component } ;
```

The module name is the file name without the `.shdl` extension (`fullAdder.shdl` → module `fullAdder`). Unlike Base SHDL — which holds exactly one flattened component — an SHDL module may define any number of components, and they may freely instantiate one another.

The **top-level component** (the one being compiled or simulated) is selected by the toolchain. A component may optionally be marked with the `top` modifier (`top component Foo(…) -> (…) { … }`) to declare the intended default; a module may contain at most one `top`-marked component. The marker is advisory — the toolchain may still override it — but it makes single-file examples self-describing. A parameterized component (§4.4) may only be marked `top` if all its parameters have defaults.

---

## 4. Components and Ports

A component is a reusable circuit module with a typed interface and an internal implementation.

```ebnf
Component = [ "top" ] "component" IDENTIFIER [ ParamList ]
            "(" [ PortList ] ")"
            "->" "(" [ PortList ] ")"
            "{" { Declaration } [ InitBlock ] ConnectBlock "}" ;

ParamList = "<" Param { "," Param } ">" ;
Param     = IDENTIFIER [ "=" NUMBER ] ;

PortList  = Port { "," Port } ;
Port      = IDENTIFIER [ "[" ArithExpr "]" ] ;
```

- The first parenthesized list declares **inputs**; the list after `->` declares **outputs**.
- Either list may be empty (e.g. a constant generator: `component ConstOne() -> (Out) { … }`).
- A port is single-bit by default, or a vector of width *N* when written `Name[N]`. The width is an integer expression: a literal, or — in a parameterized component — an arithmetic expression over the parameters (`A[N]`, `Sum[N+1]`).
- An optional `ParamList` after the name declares compile-time **parameters** (§4.4); an optional `InitBlock` before `connect` declares **initial state** (§11.4).
- `PascalCase` is the convention for component and type names; port names are free-form (`A`, `Cin`, `DataIn`, `clk`).

### 4.1 Single-bit and Multi-bit Ports

```
component FullAdder(A, B, Cin) -> (Sum, Cout) { … }       # all single-bit
component Adder8(A[8], B[8], Cin) -> (Sum[8], Cout) { … } # 8-bit vectors + carries
```

A vector `A[8]` is a bus of 8 parallel single-bit wires. Bit indexing is **1-based**: bit 1 is the LSB, bit *N* is the MSB of an *N*-bit signal (§6).

### 4.2 Component Body

The body contains **declarations** (instances, constants, generators — §5, §7, §8), an optional **`init` block** (§11.4), and exactly one **`connect` block** (§6). By convention declarations come first, then `init`, then `connect`; the parser also accepts declarations interleaved, but a component must contain exactly one `connect` block and at most one `init` block.

### 4.3 Complete Example

A full adder built from primitive gates — the canonical "hello, circuit":

```
component FullAdder(A, B, Cin) -> (Sum, Cout) {
    x1: XOR;  a1: AND;
    x2: XOR;  a2: AND;
    o1: OR;

    connect {
        A -> x1.A;   B -> x1.B;
        A -> a1.A;   B -> a1.B;

        x1.O -> x2.A;  Cin -> x2.B;
        x1.O -> a2.A;  Cin -> a2.B;
        a1.O -> o1.A;  a2.O -> o1.B;

        x2.O -> Sum;   o1.O -> Cout;
    }
}
```

### 4.4 Parameterized Components

A component may declare compile-time **parameters** in an angle-bracket list after its name. Parameters are non-negative integers, bound at the instantiation site (§5.3), and usable anywhere a width, range bound, index, or arithmetic expression is expected. Like generators, parameters are resolved entirely at flatten time — they produce *structure*, never runtime values.

```ebnf
ParamList = "<" Param { "," Param } ">" ;
Param     = IDENTIFIER [ "=" NUMBER ] ;
```

This is what makes a component genuinely reusable across widths: one definition serves every size, instead of one copy per width.

```
component Adder<N>(A[N], B[N], Cin) -> (Sum[N], Cout) {
    >i[N]{ fa{i}: FullAdder; }

    connect {
        >i[N]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i}.Sum -> Sum[{i}];
        }
        Cin -> fa1.Cin;
        >i[2:N]{ fa{i-1}.Cout -> fa{i}.Cin; }
        fa{N}.Cout -> Cout;
    }
}
```

- A parameter name is conventionally an uppercase letter or short word (`N`, `WIDTH`, `SEL`).
- Parameters participate in arithmetic: a port may be `Sum[N+1]`, a range `>i[2:N]`, an index `A[{N}]`.
- A parameter may carry a **default** (`<N = 8>`); a parameter with a default may be omitted at instantiation.
- Parameters are scoped to their component, exactly like generator variables — they are visible throughout its body and nowhere else.

#### 4.4.1 Multiple and Dependent Parameters

A component may declare several parameters; later parameters and port widths may depend on earlier ones.

```
component Mux<N, SEL = 1>(D[N], S[SEL]) -> (O) { … }     # SEL defaults to 1
component RegFile<W, DEPTH>(…) -> (…) { … }              # two independent sizes
component ShiftReg<N>(In[N]) -> (Out[N], Carry) { … }
```

Parameter values must be **positive** wherever they determine a width (a zero-width port is ill-formed), and every parameter must be bound (by an argument or a default) at instantiation. Validity of the *expanded* body — that every generated index lies in range, every referenced bit exists — is checked after binding, per instantiation (§14).

---

## 5. Instances

An instance is a concrete occurrence of a component type (a primitive gate or a user-defined component) inside another component.

```ebnf
InstanceDecl = NameTemplate ":" IDENTIFIER [ ArgList ] ";" ;
ArgList      = "<" Arg { "," Arg } ">" ;
Arg          = [ IDENTIFIER "=" ] ArithExpr ;     (* positional or named *)
```

The name on the left is the instance; the identifier after `:` is its component type. A parameterized type (§4.4) is instantiated by supplying arguments in an angle-bracket list (§5.3).

```
gate1: AND;          # primitive
adder: FullAdder;    # user-defined component
reg0:  Register<16>; # parameterized: bind N = 16
```

Several instances may share a line; the form is purely cosmetic:

```
and1: AND; and2: AND; and3: AND;
```

Generators (§7) create instances in bulk; `NameTemplate` is the instance name possibly carrying `{expr}` substitutions for that purpose (`gate{i}`).

### 5.1 Port Access

An instance's ports are reached with dot notation, and — because user components may have multi-bit ports — an instance port may itself be indexed or sliced:

```
gate1.A          # input A of a primitive
adder.Sum        # the (possibly multi-bit) Sum output
adder.Sum[1]     # bit 1 (LSB) of adder's Sum
sel.d0[{i}]      # bit i of sel's d0 input, inside a generator
```

This is a key difference from Base SHDL: there, every instance is a primitive whose ports are the single bits `A`, `B`, `O`. Here, instance ports inherit the full multi-bit interface of their component type.

### 5.2 Instance Uniqueness

Every instance name must be unique within its component. After hierarchical flattening, names are disambiguated by prefixing (`fa1` containing `x1` becomes `fa1_x1`); see §12 and `base_shdl.md` §3.5.

### 5.3 Parameter Arguments

When the instantiated type declares parameters (§4.4), arguments are passed in an angle-bracket list. Arguments may be **positional** (matched left-to-right) or **named** (`SEL = 2`); a parameter with a default may be omitted. Inside a generator or another parameterized component, an argument may itself be an arithmetic expression over the enclosing loop variables and parameters.

```
r8:  Register<8>;            # positional
r32: Register<32>;
m:   Mux<4>;                 # SEL omitted → uses its default of 1
m2:  Mux<N = 8, SEL = 2>;    # named, in any order

>i[4]{
    stage{i}: Pipe<WIDTH = W, ID = i>;   # argument depends on the loop variable
}
```

Rules (checked per §14):

- Every parameter must end up bound — by a positional argument, a named argument, or a default.
- Positional arguments must precede named arguments, and no parameter may be bound twice.
- Each argument expression must evaluate to a non-negative integer using only enclosing parameters, generator variables, and literals.

The two instances `r8` and `r32` reference the **same** component definition but flatten to different gate counts: binding happens during hierarchy flattening (§12), and Base SHDL never sees the parameter.

---

## 6. Signals and Connections

A **signal** is a reference to a wire — a port, an instance port, or a constant — optionally narrowed to specific bits. A **connection** drives one signal from another.

```ebnf
ConnectBlock = "connect" "{" { Connection | Generator | Conditional } "}" ;
Connection   = Signal "->" Signal ";" ;

Signal       = Concat | Primary ;
Concat       = "{" ConcatItem { "," ConcatItem } "}" ;
ConcatItem   = Replication | Primary ;
Replication  = ArithExpr "{" ConcatItem { "," ConcatItem } "}" ;   (* N copies of the group *)
Primary      = NameTemplate [ "." NameTemplate ] [ "[" IndexExpr "]" ] ;
IndexExpr    = ArithExpr                          (* single bit:  [3], [{i}]    *)
             |             ArithExpr ":"           (* slice to end: [5:]         *)
             | [ ArithExpr ] ":" ArithExpr ;       (* slice:        [2:7], [:4]  *)
```

A **signal** is either a single `Primary` (a port, instance port, or constant, optionally indexed or sliced) or a brace-delimited **concatenation** of several (§6.5).

The arrow reads **source `->` destination**. Connections are declarative and order-independent — like real wiring, they all hold simultaneously.

### 6.1 Valid Sources and Destinations

| Role          | May be                                                            |
|---------------|-------------------------------------------------------------------|
| Source        | a component **input** port, an instance **output** port, or a **constant** — optionally indexed/sliced |
| Destination   | a component **output** port or an instance **input** port — optionally indexed/sliced |

```
A -> gate1.A;        # input port  → instance input
gate1.O -> gate2.A;  # instance out → instance input
adder.Sum -> Sum;    # instance out → output port
A[1] -> fa1.A;       # one bit of a bus → instance input
gate.O -> Result[1]; # instance out → one bit of an output bus
```

### 6.2 Bit Indexing

`Signal[k]` selects bit *k* (1-based, LSB = 1). The index may be a literal or, inside a generator, an arithmetic expression in `{ }`:

```
In[1] -> Low;          # extract LSB
In[8] -> High;         # extract MSB of an 8-bit signal
A[{i}]      -> fa{i}.A; # bit i, in a generator
O[{2*i-1}]  -> …;       # computed index (odd bits)
```

### 6.3 Slices (Expanders)

A slice connects a **contiguous range** of bits in one statement. The flattener (the "expander" phase) rewrites a slice into one connection per bit.

| Notation     | Meaning                       |
|--------------|-------------------------------|
| `S[a:b]`     | bits *a* through *b* inclusive |
| `S[:b]`      | bits 1 through *b*            |
| `S[a:]`      | bits *a* through the signal's width |

```
component SplitByte(In[8]) -> (Low[4], High[4]) {
    connect {
        In[:4]  -> Low;     # In[1..4] → Low[1..4]
        In[5:8] -> High;    # In[5..8] → High[1..4]
    }
}
```

Source and destination of a slice connection must have **equal width**; they are wired lowest-to-lowest (`In[5] -> High[1]`, `In[6] -> High[2]`, …). Connecting two equal-width whole vectors (`A -> B` with both 8-bit) is likewise a bit-for-bit connection.

Slices are intentionally limited: they appear only in connections, handle only contiguous ranges, and perform no arithmetic. For anything more — non-contiguous bits, computed indices, repeated instances — use a **generator** (§7).

### 6.4 Connection Rules

These are checked semantically and carried unchanged into Base SHDL:

1. **Single driver.** Each instance input and each component output is driven by exactly one source.
2. **Fan-out is free.** A single source may drive any number of destinations.
3. **No floating inputs.** Every instance input must be connected.
4. **No floating outputs.** Every component output must be driven.
5. **Width agreement.** Both ends of a connection must reference the same number of bits.
6. **No self-connection.** A signal may not drive itself.

### 6.5 Concatenation and Split

A **concatenation** assembles several signals into one wider signal, written as a brace-delimited, comma-separated list. It may appear on either side of an arrow, filling the gap between contiguous slices (§6.3) and full generators (§7) for the bit-steering that datapaths need constantly — mux inputs, immediate assembly, splitting a result into flags and value, byte lanes.

Bits are ordered **most-significant-first within the braces**, matching how numbers are written. The combined width must agree with the other end (rule 5).

```
{hi, lo}      -> Byte;          # hi → high half, lo → low half of Byte
Word          -> {High, Low};   # split a 16-bit Word into two 8-bit halves
{Cin, A[1:7]} -> Shifted;       # mix a single-bit source with a slice (Cin lands in the MSB)
{Flags, Data} -> Result;        # heterogeneous widths; total must match Result
```

A concatenation may be a connection **source** or **destination**; an item may be any `Primary` — a whole signal, a single bit, or a slice. As with whole-vector and slice connections, bits are paired by position once both ends are flattened to ordered bit lists.

#### 6.5.1 Replication

An item may be written as a replication `N{ … }` — a count *N* applied to a braced group, emitting *N* copies of that group (Verilog-style). This expresses sign- and zero-extension compactly:

```
{8{sign}, Value} -> Extended;   # sign-extend: 8 copies of `sign`, then Value
{4{ZERO}, Nib}   -> Padded;     # zero-extend a nibble to a byte (ZERO = 0 constant)
```

The count *N* must be **≥ 1**. A replication count of 0 or a negative count is a generator-range error (E0601, "count must be ≥ 1") — the same diagnostic that guards empty generator ranges, since a zero-or-negative repeat count is the replication analogue of an empty range.

#### 6.5.2 Lowering

A concatenation is **pure structure**. The expander (§12, phase 4) flattens both ends to bit lists — expanding replications and slices — and emits one single-bit connection per bit, highest-to-highest:

```
{hi, lo} -> Byte;        # hi[2..1], lo[2..1]  →  Byte[4..1]
# becomes
hi[2] -> Byte[4];   hi[1] -> Byte[3];
lo[2] -> Byte[2];   lo[1] -> Byte[1];
```

> **Note on the `{ }` overload.** Braces already denote `{expr}` substitution and block bodies. A concatenation is unambiguous because it appears in *signal position* as a comma-separated list, whereas substitution appears *inside a name or index*; one token of lookahead distinguishes them. A bare `{expr}` in signal position (a single braced item with no comma) is read as a one-element concatenation and is equivalent to the `Primary` it contains.

---

## 7. Generators

Generators are SHDL's general-purpose mechanism for repetitive structure. A generator is a compile-time loop: its body is emitted once per value in a range, with the loop variable substituted. Generators run entirely at flatten time — they produce *structure*, never runtime control flow.

```ebnf
Generator   = ">" IDENTIFIER "[" RangeSpec "]" "{" { GenItem } "}" ;
RangeSpec   = SingleRange { "," SingleRange } ;
SingleRange = ArithExpr                   (* [N]    => 1, 2, …, N        *)
            | ArithExpr ":" [ ArithExpr ]  (* [a:b]  => a…b ; [a:] => a…width *)
            | ":" ArithExpr ;              (* [:b]   => 1, 2, …, b        *)
```

- `>` introduces the generator; the identifier is the loop variable (conventionally `i`, `j`, `k`).
- Range bounds are integer expressions: literals, or — inside a parameterized component (§4.4) or an enclosing generator — expressions over the parameters and outer loop variables (`>i[N]`, `>i[2:N]`, `>j[i]`).
- `GenItem` is an instance declaration, a constant, a connection, a conditional (§7.7), or a nested generator — depending on context (§7.4).

### 7.1 Ranges

| Range          | Values                              |
|----------------|-------------------------------------|
| `[8]`          | 1, 2, 3, 4, 5, 6, 7, 8              |
| `[4:10]`       | 4, 5, 6, 7, 8, 9, 10               |
| `[5:]`         | 5, 6, … up to the governing signal's width |
| `[1:4, 8, 12:16]` | 1, 2, 3, 4, 8, 12, 13, 14, 15, 16 |

**Value domain.** Range bounds evaluate to integers that must be **≥ 0**. A bound of 0 is legal: the count form `[0]` is empty (it iterates over no values), and a lower bound of 0 (`[0:b]`) iterates from index 0. A **negative** bound — whether a literal, a parameter expression, or a computed value — is rejected (E0601). A range that is empty or ill-ordered after evaluation (`[2:1]`, a count `< 1`, a resolved open range with no values) is likewise an E0601; the diagnostic covers all of these — an empty, ill-ordered, or negative range.

**Compound ranges iterate verbatim.** A compound range (`[a:b, c, d:e]`) emits its sub-ranges in written order, left to right, with **no de-duplication**. Overlapping sub-ranges such as `[1:4, 2:6]` therefore iterate `1, 2, 3, 4, 2, 3, 4, 5, 6` and emit the body once per value — including the repeated indices. Any structural collision this produces (two instances generated with the same name, or two drivers reaching one sink) is caught by the ordinary uniqueness and single-driver rules — a duplicate generated instance name is E0301, a duplicated sink driver is E0501 — rather than by a special range check; the author is responsible for keeping compound sub-ranges disjoint where the body declares names.

**Open-ended bounds may be expressions.** The bound expressions in any range — including the lower bound of an open-ended range — may be arithmetic over the enclosing parameters and loop variables (`>i[N/2:]`, `>i[a+1:]`). The bound is evaluated first; the governing-signal rule above then resolves the open upper bound from the width of the indexed signal. There is no restriction to literal bounds.

**Open-ended ranges.** Open-ended ranges (`[a:]`) resolve their upper bound from the width of the **governing signal** — the signal whose bits the range indexes. The scan collects the widths of *every* signal indexed by the loop variable in the body and requires them to **agree on a single width**: several signals of the same width are fine (they fix the same bound), but two signals of *different* widths leave the bound ambiguous and the open-ended form is rejected (E0602); an explicit bound must then be given (`[a:N]`). The governing-signal scan is **conservative with respect to conditionals**: both the `when` and the `else` body are scanned for governing signals *before* any condition is evaluated, so a signal in a branch that will not be emitted can still force a width disagreement (E0602) — write an explicit bound to avoid relying on which branch survives. An open-ended range whose body indexes no multi-bit signal under the loop variable has no governing signal and is also rejected (E0602). Inside a parameterized component the explicit form `[a:N]` over a parameter `N` is the clearest choice and is preferred.

### 7.2 Substitution and Arithmetic

`{expr}` inside a name or index is replaced by the value of *expr* for the current iteration:

```
>i[4]{ gate{i}: AND; }     # gate1, gate2, gate3, gate4
```

Expressions support `+`, `-`, `*`, and `/` (**integer** division), nested arbitrarily:

```
>i[2:8]{
    prev{i-1}.O -> curr{i}.A;   # i-1: previous index
    Data[{i+1}] -> curr{i}.B;   # i+1: next bit
}

>i[4]{
    A[{i}]     -> inv{i}.A;
    inv{i}.O   -> O[{2*i-1}];    # write odd output bits 1,3,5,7
}
```

**Scope of the range expression vs. the body.** The loop variable is bound for the generator's **body**, not for its own range. A generator's range bounds are evaluated in the **enclosing** scope — the loop variable does not yet exist there. This matters when the loop variable *shadows* an enclosing parameter or outer loop variable of the same name: in `>N[N]{ … }` inside `component Foo<N>(…)`, the range `[N]` evaluates against the **parameter** `N` (the enclosing binding), while the body sees the **loop variable** `N` ranging `1 … N`. The shadow takes effect at the opening brace of the body, so the range and the body can legitimately read two different `N` values.

### 7.3 Nesting

Generators nest to build multi-dimensional structure; inner generators expand first. A template name may interleave several substitutions and literal text:

```
>i[2]{
    >j[2]{
        cell{i}_{j}: BitCell;   # cell1_1, cell1_2, cell2_1, cell2_2
    }
}

>row[4]{
    >col[4]{
        mem{row*4+col}: Cell;   # linearized 2-D index
    }
}
```

### 7.4 Declaration vs. Connection Context

A generator's legal body depends on where it appears:

- **In the component body** (alongside declarations): the body holds **instance** and **constant** declarations (and nested generators or conditionals).
- **Inside `connect`**: the body holds **connections** (and nested generators or conditionals).

A `when` conditional (§7.7) follows the same rule: its body may contain whatever the enclosing context allows. Conditionals and generators may therefore appear in either context — declaration or connection — exactly where a generator may.

### 7.5 Worked Example: 8-bit Ripple-Carry Adder

```
use fullAdder::{FullAdder};

component Adder8(A[8], B[8], Cin) -> (Sum[8], Cout) {
    >i[8]{ fa{i}: FullAdder; }

    connect {
        A[1] -> fa1.A;  B[1] -> fa1.B;  Cin -> fa1.Cin;
        fa1.Sum -> Sum[1];

        >i[2:8]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            fa{i-1}.Cout -> fa{i}.Cin;   # chain the carry
            fa{i}.Sum    -> Sum[{i}];
        }

        fa8.Cout -> Cout;
    }
}
```

### 7.6 Generators vs. Slices

| Feature                  | Slices (`S[a:b]`) | Generators (`>i[…]{ }`) |
|--------------------------|-------------------|--------------------------|
| In connections           | ✓                 | ✓                        |
| In declarations          | ✗                 | ✓ (create instances)     |
| Arithmetic (`{i+1}`, `{i*2}`) | ✗            | ✓                        |
| Nesting                  | ✗                 | ✓                        |
| Non-contiguous ranges    | ✗                 | ✓ (`[1:4, 8, 12:]`)      |

### 7.7 Conditional Emission

A `when` conditional selects structure at **flatten time**. Its condition is an integer comparison over loop variables, parameters, and literals; when true, the body is emitted, otherwise it is skipped (or the `else` body is emitted). There is no runtime branch — this is structural selection, in the same spirit as a generator: it produces *structure*, never control flow.

```ebnf
Conditional = "when" "{" BoolExpr "}" "{" { GenItem } "}"
                     [ "else" "{" { GenItem } "}" ] ;

BoolExpr    = OrExpr ;
OrExpr      = AndExpr { "||" AndExpr } ;
AndExpr     = CmpExpr { "&&" CmpExpr } ;
CmpExpr     = ArithExpr RelOp ArithExpr | "(" BoolExpr ")" ;
RelOp       = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
```

The relational (`==`, `!=`, `<`, `<=`, `>`, `>=`) and boolean (`&&`, `||`) operators exist **only** inside a `when` condition; they are evaluated at flatten time and never become gates.

#### 7.7.1 Folding Boundary Cases into a Loop

The most common use is to handle a generator's first or last iteration without hoisting it out of the loop. Compare the ripple-carry carry chain of §7.5, where stage 1 is written separately, with the same logic expressed in one uniform loop:

```
component Adder<N>(A[N], B[N], Cin) -> (Sum[N], Cout) {
    >i[N]{ fa{i}: FullAdder; }

    connect {
        >i[N]{
            A[{i}] -> fa{i}.A;
            B[{i}] -> fa{i}.B;
            when {i == 1} { Cin          -> fa{i}.Cin; }   # first stage: external carry-in
            when {i >  1} { fa{i-1}.Cout -> fa{i}.Cin; }   # interior: chain the carry
            fa{i}.Sum -> Sum[{i}];
        }
        fa{N}.Cout -> Cout;
    }
}
```

An optional `else` pairs naturally with a two-way boundary:

```
>i[N]{
    when {i == N} { fa{i}.Cout -> Cout; }
    else          { fa{i}.Cout -> fa{i+1}.Cin; }
}
```

#### 7.7.2 Conditional Declarations

In declaration context, `when` conditionally creates instances — useful for optional structure governed by a parameter:

```
component Counter<N, WITH_CARRY = 0>(clk) -> (Q[N], Cout) {
    >i[N]{ ff{i}: TFlipFlop; }
    when {WITH_CARRY == 1} { co: AND; }
    connect { … }
}
```

#### 7.7.3 Lowering

`when` is resolved during **generator & conditional expansion** (§12, phase 3), before any structure is materialized. A true condition contributes its body to the unrolled output; a false condition contributes nothing (or its `else` body). After phase 3 the netlist contains only ordinary instances and connections, so Base SHDL never sees a conditional.

---

## 8. Constants

A constant is a fixed bit pattern usable as a connection source without an external input. Each **referenced** bit becomes a power-pin instance during flattening (§12).

```ebnf
ConstantDecl = IDENTIFIER [ "[" ArithExpr "]" ] "=" NUMBER ";" ;
```

The declared width is an `ArithExpr`, not a bare literal: like a port width (§4), a constant's width may be an arithmetic expression over the enclosing component's parameters (`K[N] = v`). The value to the right of `=` is always a literal `NUMBER`. A parameter-dependent width is resolved per instantiation during monomorphization (§12, phase 2); the overflow assertion (§8.1) is then re-checked against the concrete width (§14).

```
THRESHOLD = 100;     # width inferred from value
MASK      = 0xFF;
DATA[8]   = 100;     # explicit 8-bit width
```

### 8.1 Width

A constant is conceptually an **unsigned integer of unbounded width**: bit *k* is the *k*-th bit of its binary value, and **every bit beyond the value's significant bits is 0**. There is no such thing as an out-of-range constant bit — referencing `Hundred[99]` simply yields `0` (a `__GND__`), exactly as the leading zeros of an unsigned number would.

| Value | Significant bits | `[1]` | `[7]` | `[8]` | `[64]` |
|-------|------------------|-------|-------|-------|--------|
| 1     | `1`              | 1     | 0     | 0     | 0      |
| 6     | `110`            | 0     | 0     | 0     | 0      |
| 100   | `1100100`        | 0     | 1     | 0     | 0      |
| 255   | `11111111`       | 1     | 1     | 1     | 0      |

This removes a whole class of width-inference bugs: a constant feeding a fixed bit range — e.g. a `>i[8]{ … }` generator — needs no explicit width, because every referenced bit is defined. `Hundred = 100` and `Hundred[8] = 100` behave identically for any reference in range `1 … 8`.

A constant with **no declared width** has its width *inferred* from the value's bit length, with a floor of 1: the inferred width is `max(1, bit_length(value))`. The value 0 therefore infers width **1** — a single `__GND__` bit — so `ZERO = 0` is a one-bit low source, not a zero-width signal. (The unbounded-zeros rule above still applies above that width: `ZERO[5]` is `0`.) This floor is what lets `ZERO` be used as a one-bit source — e.g. `{4{ZERO}, Nib}` — without an explicit width.

Constant **values** are exact unbounded integers: a literal larger than 64 bits (e.g. a 256-bit hex mask) is perfectly legal in the flattener, since a constant is a pattern of referenced bits, not an ABI value. The 64-bit ceiling (§14.2) applies only to a multi-bit **port** crossing the compiled ABI, never to a constant's internal value — only the bits a constant actually feeds into ports or gates are materialized.

The optional declared width (`DATA[8] = 100`) therefore serves a single purpose: an **overflow assertion**. The value must fit in the declared width, or it is a constant error (E08xx):

```
DATA[8] = 100;     # OK: 100 fits in 8 bits
DATA[8] = 300;     # E08xx: value 300 does not fit in 8 bits
```

A declared width does **not** otherwise change behavior — referencing a bit above the declared width is still `0` — it only documents intent and catches a value that has grown too large.

### 8.2 Bit Semantics and Usage

Bit 1 is the LSB. Constants are referenced like any signal, including per-bit:

```
component Add100(A[8]) -> (Sum[8], Cout) {
    Hundred[8] = 100;
    >i[8]{ fa{i}: FullAdder; }
    connect {
        >i[8]{
            A[{i}]       -> fa{i}.A;
            Hundred[{i}] -> fa{i}.B;     # each bit of the constant
        }
        # … carry chain …
    }
}
```

A constant may only be a connection **source**, never a destination.

---

## 9. Imports and the Standard Library

Components defined in other modules are made available with `use`.

```ebnf
Import = "use" IDENTIFIER "::" "{" IDENTIFIER { "," IDENTIFIER } "}" ";" ;
```

```
use fullAdder::{FullAdder};
use alu::{ALU, Shifter, Comparator};
use stdgates::{NAND, NOR, XNOR};
```

### 9.1 Resolution

- The module name is the target file's name without `.shdl` (`fullAdder` → `fullAdder.shdl`).
- The toolchain searches the **importing file's own directory first**, then any directories supplied with the compiler's `-I`/`--include` flag, in the order they are given. Resolving relative to the importing file (rather than the process's current working directory) keeps a project relocatable and the resolution deterministic regardless of where the tool is invoked.
- A module name must match the real file name **case-sensitively**, independent of the host filesystem's case sensitivity. If a `use Add2` resolves a file whose actual name is `add2.shdl` (as a case-insensitive filesystem would permit), it is rejected as not found (E0701); the same source therefore behaves identically on every platform, and two spellings can never load one file as two modules.
- **Only names *defined* in the target module are importable.** A `use` brings in a name only if the target module itself declares that component; it does **not** re-export names the target merely imported. Importing a name that the target does not define is a missing-name error (E0703) — there is no transitive re-export. (Module identity is keyed by the bare module name and is program-global; a name resolves to whichever file first bound that module name for the whole compilation.)
- Imports must precede all component definitions in the file. A `use` appearing after a component definition is a syntax error (E0201).
- **Circular imports are not allowed** (file A importing B importing A, including a module importing itself). Refactor shared definitions into a common base module.

### 9.2 The Standard Library

`stdgates` is the conventional standard-library module providing common gates composed from the primitives — notably **NAND**, **NOR**, and **XNOR**. The six primitive types (§10) are **built in**: they are predefined in every file and cannot be defined in a module (defining one is a primitive-shadowing error, E0305) nor imported from one. A `use stdgates::{AND}` does not resolve a primitive — `stdgates` does not define `AND` — so it is a missing-name error (E0703); primitives need no import and importing them is not "harmless", it is rejected.

---

## 10. Primitive and Derived Gates

### 10.1 The Six Primitives

These are the only built-in component types and the only types that survive into Base SHDL. They are predefined — available in every file without `use`. Their names may **not** be redefined: a user `component AND(…)` that shadows a primitive is a naming error (§2.5, E03xx).

| Type      | Inputs   | Output | Operation        | C operator |
|-----------|----------|--------|------------------|------------|
| `AND`     | `A`, `B` | `O`    | O = A ∧ B        | `&`        |
| `OR`      | `A`, `B` | `O`    | O = A ∨ B        | `\|`       |
| `NOT`     | `A`      | `O`    | O = ¬A           | `~`        |
| `XOR`     | `A`, `B` | `O`    | O = A ⊕ B        | `^`        |
| `__VCC__` | *(none)* | `O`    | constant HIGH (1)|            |
| `__GND__` | *(none)* | `O`    | constant LOW (0) |            |

Every primitive uses the same port convention: inputs `A` (and `B`), output `O` (the letter O, not zero). `AND`, `OR`, `NOT` are functionally complete; `XOR` is included because it dominates arithmetic and maps to one C operator. The power pins exist to materialize constants after flattening.

### 10.2 Derived Gates

`NAND`, `NOR`, and `XNOR` are not primitives — they are ordinary components built from the primitives (and supplied by `stdgates`):

```
component NAND(A, B) -> (O) {
    and1: AND;  not1: NOT;
    connect { A -> and1.A;  B -> and1.B;  and1.O -> not1.A;  not1.O -> O; }
}
```

Because they are ordinary components, they are inlined like any other during hierarchy flattening.

---

## 11. Simulation Semantics

SHDL's meaning is defined by a single, deterministic evaluation model. Understanding it is essential, because it is what makes feedback, latches, and clocks behave correctly.

### 11.1 The Evaluation Model: Unit Delay, One Level per Cycle

Simulation advances in discrete **cycles**. On each cycle, **every gate simultaneously** computes its output from the values present on its inputs *at the end of the previous cycle*. Equivalently: **each gate has unit propagation delay**, and a circuit advances exactly one gate-level per cycle.

Consequences:

- A combinational result is not visible the instant inputs change; it ripples forward one gate-level per cycle. An *N*-deep circuit needs *N* cycles for its outputs to fully reflect new inputs.
- Component input ports hold their driven (`poke`d) values across cycles until changed.
- The model is fully deterministic: every wire has a defined value at cycle 0 (§11.4), so the same inputs always yield the same trace — including for feedback circuits.

### 11.2 Feedback and Sequential Circuits

Because evaluation is cycle-based with unit delay, **feedback loops are well-defined** — a wire may ultimately depend on its own previous value. This is how SHDL expresses state and timing with nothing but gates:

- **Latches / registers** arise from cross-coupled gates (e.g. an SR latch from two `NOR`s), which hold a value across cycles.
- **Oscillators / clocks** arise from feedback paths whose length sets the period — e.g. a ring of buffers whose last stage feeds the first.

```
# Ring oscillator / delay line: a pulse advances one stage per cycle,
# and stage 20 feeds back into stage 1.
component Clock(clk) -> (out[20]) {
    >i[20]{ o{i}: OR; }
    connect {
        clk -> o1.A;
        >i[2:20]{
            o{i-1}.O -> o{i}.A;
            o{i-1}.O -> o{i}.B;
            o{i-1}.O -> out[{i-1}];
        }
        o20.O -> o1.B;
        o20.O -> out[20];
    }
}
```

### 11.3 Combinational Depth and Settling

For a feedback-free (purely combinational) circuit there is a finite **combinational depth** — the longest gate path from any input to any output. Running that many cycles guarantees the outputs are stable for the current inputs. The flattener records this depth in Base SHDL metadata (`timing.max_depth`, `is_combinational`, `has_feedback`), which lets the Python driver offer a `settle()` operation that advances exactly enough cycles, instead of the author guessing a `step(n)` count. Circuits with feedback have no such guaranteed fixed point and are advanced explicitly with `step(n)`.

### 11.4 Initial State

Every wire has a defined value at **cycle 0**, before the first `step`. By default that value is **0** — as if every net were GND-driven prior to the first cycle. This makes the model deterministic for *all* circuits, not just combinational ones: an SR latch built from cross-coupled `NOR`s (§11.2) has a defined, reproducible power-on state rather than an undefined one.

For state-holding circuits whose power-on value matters, the default of 0 is not always the one you want — a latch may need to come up set. An optional **`init` block** seeds chosen nets to a specific value:

```ebnf
InitBlock  = "init" "{" { InitAssign } "}" ;
InitAssign = Primary "=" NUMBER ";" ;
```

The `init` block appears in the component body, before `connect` (§4.2). Each assignment seeds the named signal — an instance output, a component output, or a multi-bit port (whose value is spread across its bits, LSB first) — with the value it holds at cycle 0:

```
use stdgates::{NOR};

component SRLatch(S, R) -> (Q, Qn) {
    n1: NOR;  n2: NOR;

    init {
        n1.O = 0;     # power-on: Q  = 0
        n2.O = 1;     #           Qn = 1
    }

    connect {
        R -> n1.A;   n2.O -> n1.B;   n1.O -> Q;
        S -> n2.A;   n1.O -> n2.B;   n2.O -> Qn;
    }
}
```

(`NOR` is a derived gate from `stdgates` (§9.2, §10.2), so it must be imported. Seeding `n1.O`/`n2.O` here seeds only each composite `NOR`'s output `NOT`; for a power-on state that holds from cycle 0, every gate in the feedback loop must be seeded to a fixed point — a latch that *owns* its loop spells the two NORs out as `OR`+`NOT` and seeds all four nets. See `examples/srLatch.shdl`.)

```
component Datapath<N>(clk) -> (Out[N]) {
    acc: Register<N>;               # an N-bit register holds the accumulator
    init { acc.Q = 1; }             # the accumulator powers up at 1, not 0
    connect { acc.Q -> Out; … }
}
```

The seed must land on a **state-holding** node — a wire whose value persists across cycles (a feedback node, or an instance output that resolves to one). Seeding a purely combinational wire is allowed but has no lasting effect: it is overwritten on the next cycle by whatever drives it. In the example, `acc.Q` is the register's stored value (it flattens to the register's internal feedback nodes), so seeding it sets the accumulator's power-on contents. A multi-bit target receives the value spread across its bits, LSB first (`acc.Q = 1` sets bit 1 high, the rest low).

`init` produces **no gates**. It carries no behavioral meaning beyond the value present at cycle 0 — subsequent cycles evolve purely from the gate logic. During flattening it is lowered into Base SHDL metadata (an `init` block; see `base_shdl.md` §4.11), which the compiler uses to seed the State Region and the debugger uses to display power-on state. A net not mentioned in any `init` block keeps the default value of 0.

Rules (checked per §14):

- An `init` target must be a drivable signal (an instance output, or a component output port); it may not seed a component **input** (inputs are set by `poke`, not `init`).
- Each net may be seeded at most once.
- The seed value must fit the target's width (the same overflow rule as constants, §8.1).

---

## 12. Lowering to Base SHDL

The flattener mechanically removes every high-level construct in six sequential phases, producing an equivalent Base SHDL netlist. Each phase fully completes before the next begins.

| Phase | Name                       | Removes / Resolves                                                        |
|-------|----------------------------|---------------------------------------------------------------------------|
| 1     | **Lexical stripping**      | Comments; resolves and drops `use` imports                                |
| 2     | **Monomorphization**       | Binds parameters; specializes each parameterized component per argument set, evaluating parameter expressions in widths, ranges, indices, and `when` conditions |
| 3     | **Generator & conditional expansion** | Unrolls every `>i[…]{ }` (evaluating `{expr}` and substituting names) and resolves every `when { … }` guard |
| 4     | **Expander expansion**     | Rewrites every slice `S[a:b]` and every concatenation `{ … }` into individual single-bit connections |
| 5     | **Constant materialization** | Replaces each referenced constant bit with a `__VCC__` (1) or `__GND__` (0) instance |
| 6     | **Hierarchy flattening**   | Inlines every user component, prefixing instance names and rewiring ports; extracts `init` seeds and the rest of the metadata |

**Why monomorphization comes first.** A parameterized component's generator ranges, port widths, and `when` conditions all depend on its parameters, so they cannot be resolved until the parameters are bound. Phase 2 walks the instantiation graph from the top component, and for each distinct argument tuple clones the component definition with the concrete values substituted (`Adder<8>` and `Adder<16>` become two ordinary definitions). After phase 2 **no parameter identifiers remain** — the program is parameter-free, and phases 3–6 run as global passes exactly as before. This is the same specialization model as C++ templates or Rust monomorphization; non-recursive parameterization guarantees it terminates.

Construct-by-construct, the mapping is:

| SHDL construct                | Becomes in Base SHDL                                                |
|-------------------------------|---------------------------------------------------------------------|
| Parameter `Adder<N>` @ `<8>`  | a specialized parameter-free `Adder` with `N = 8` substituted       |
| Multi-bit port `A[16]`        | 16 single-bit ports `A_1_ … A_16_` (recorded in `meta.ports`)       |
| Slice `In[:4] -> Out[:4]`     | four explicit `In[k] -> Out[k]` connections                         |
| Concatenation `{hi, lo} -> B` | one explicit single-bit connection per bit, MSB-first               |
| Generator `>i[8]{ … }`        | the body emitted 8 times with `i` substituted                       |
| Conditional `when {c}{ … }`   | the body if `c` is true at flatten time, else nothing               |
| Constant `FIVE = 5`           | `FIVE_bit1: __VCC__; FIVE_bit2: __GND__; FIVE_bit3: __VCC__;` (referenced bits only) |
| `init { n1.O = 1 }`           | nothing structural — an `init` entry in `meta` (`base_shdl.md` §4.11) |
| Instance `fa1: FullAdder`     | `fa1`'s internal gates, renamed `fa1_x1`, `fa1_x2`, …               |
| `use …`                       | nothing — the imported definitions are inlined where instantiated   |
| Comments                      | nothing — discarded                                                 |

The flattening guarantees functional equivalence, name uniqueness (via hierarchical prefixing), full resolution to the six primitives, and determinism. The pipeline is detailed in [`base_shdl.md`](base_shdl.md); the resulting metadata is what lets the debugger and driver present multi-bit ports, hierarchy, and source locations even though the netlist itself is flat single-bit logic.

---

## 13. Grammar Reference

A consolidated EBNF for the full language. (`IDENTIFIER`, `NUMBER`, `LETTER`, `DIGIT` are lexical; comments and whitespace are removed by the lexer.)

```ebnf
Module        = { Import } { Component } ;

Import        = "use" IDENTIFIER "::" "{" IDENTIFIER { "," IDENTIFIER } "}" ";" ;

Component     = [ "top" ] "component" IDENTIFIER [ ParamList ]
                "(" [ PortList ] ")" "->" "(" [ PortList ] ")"
                "{" { Declaration } [ InitBlock ] ConnectBlock "}" ;

ParamList     = "<" Param { "," Param } ">" ;
Param         = IDENTIFIER [ "=" NUMBER ] ;

PortList      = Port { "," Port } ;
Port          = IDENTIFIER [ "[" ArithExpr "]" ] ;

Declaration   = InstanceDecl | ConstantDecl | Generator | Conditional ;
InstanceDecl  = NameTemplate ":" IDENTIFIER [ ArgList ] ";" ;
ArgList       = "<" Arg { "," Arg } ">" ;
Arg           = [ IDENTIFIER "=" ] ArithExpr ;
ConstantDecl  = IDENTIFIER [ "[" ArithExpr "]" ] "=" NUMBER ";" ;

InitBlock     = "init" "{" { InitAssign } "}" ;
InitAssign    = Primary "=" NUMBER ";" ;

ConnectBlock  = "connect" "{" { Connection | Generator | Conditional } "}" ;
Connection    = Signal "->" Signal ";" ;

Generator     = ">" IDENTIFIER "[" RangeSpec "]" "{" { GenItem } "}" ;
GenItem       = Connection | InstanceDecl | ConstantDecl | Generator | Conditional ;
RangeSpec     = SingleRange { "," SingleRange } ;
SingleRange   = ArithExpr
              | ArithExpr ":" [ ArithExpr ]
              | ":" ArithExpr ;

Conditional   = "when" "{" BoolExpr "}" "{" { GenItem } "}"
                       [ "else" "{" { GenItem } "}" ] ;
BoolExpr      = OrExpr ;
OrExpr        = AndExpr { "||" AndExpr } ;
AndExpr       = CmpExpr { "&&" CmpExpr } ;
CmpExpr       = ArithExpr RelOp ArithExpr | "(" BoolExpr ")" ;
RelOp         = "==" | "!=" | "<" | "<=" | ">" | ">=" ;

Signal        = Concat | Primary ;
Concat        = "{" ConcatItem { "," ConcatItem } "}" ;
ConcatItem    = Replication | Primary ;
Replication   = ArithExpr "{" ConcatItem { "," ConcatItem } "}" ;
Primary       = NameTemplate [ "." NameTemplate ] [ "[" IndexExpr "]" ] ;
IndexExpr     = ArithExpr
              | ArithExpr ":"
              | [ ArithExpr ] ":" ArithExpr ;

NameTemplate  = IDENTIFIER { "{" ArithExpr "}" [ IDENTIFIER ] } ;

ArithExpr     = Term { ( "+" | "-" ) Term } ;
Term          = Factor { ( "*" | "/" ) Factor } ;
Factor        = NUMBER | IDENTIFIER | "{" ArithExpr "}" ;
```

Notes:

- `NameTemplate` carries `{expr}` substitutions only meaningfully inside a generator; outside one it is a plain `IDENTIFIER`.
- An `IndexExpr` that is a bare `ArithExpr` selects a single bit; the colon forms are slices.
- `/` in `ArithExpr` is integer division.
- An `IDENTIFIER` inside an `ArithExpr` resolves to a generator variable or a component parameter (both compile-time integers); using one outside the scope where it is bound is an error (§14).
- `RelOp` and the boolean operators `&&`/`||` appear only inside a `when` condition (`BoolExpr`) and are evaluated at flatten time.
- A `Concat` in signal position is distinguished from a `{expr}` substitution (which appears inside a `NameTemplate`/`IndexExpr`) by context with one token of lookahead; a single-item brace group with no comma is an equivalent one-element concatenation.
- A `Replication` is recognized when a `ConcatItem` begins with an arithmetic **count immediately followed by a brace group of signals** (`8{sign}`); the group's contents are parsed as signals, never as a substitution expression. The count must be a literal or a parameter/loop-variable expression, and the group must be signal syntax — a brace group holding a single bare arithmetic expression after an identifier count (`N{i+1}`) is read as a `NameTemplate` with an `{expr}` substitution (a *template*), not a replication. Replication therefore requires a literal count or signal-only group contents; the two forms never overlap.
- The `Component` production fixes the body order `{ Declaration } [ InitBlock ] ConnectBlock` for readability, but the parser accepts the three kinds of body block (declarations, the optional `init`, the `connect`) in **any order** and freely interleaved. The only structural constraints are the count rules of §14 — exactly one `connect` block and at most one `init` block (E0309/E0310); order is not enforced.
- A flattener consumes its own emitted Base SHDL output: a **trailing `meta { … }` block** following the structural component (`base_shdl.md` §4) is *accepted and ignored* by the SHDL parser. The metadata is not re-interpreted — re-flattening already-flattened text reproduces the same structural core (the basis for the idempotence property; `base_shdl.md` §4). The block's body is a single JSON object; the parser skips it as a unit after the component's closing brace.

---

## 14. Constraints and Well-Formedness

A module is well-formed only if all of the following hold. Violations are reported with positioned diagnostics; categories mirror the compiler's error codes.

| Area               | Requirement                                                                 | Codes  |
|--------------------|------------------------------------------------------------------------------|--------|
| Names              | No duplicate component or instance names; no use of reserved `__…` or `…_<digits>_` names; no redefinition of a primitive type name | E03xx  |
| References         | Every referenced component, instance, port, and signal must exist            | E03xx  |
| Widths             | Connection ends agree in width (after concatenation/replication); bit indices lie in `1 … width`; widths > 0 | E04xx  |
| Connections        | One driver per sink; no floating inputs/outputs; no self-connection          | E05xx  |
| Generators         | Non-empty, well-ordered ranges; open-ended bound unambiguous; loop variables used only within their body; `when` conditions are well-formed; an emitted body is legal for its context | E06xx  |
| Imports            | Target module exists; no circular imports                                    | E07xx  |
| Constants          | Value fits its declared width (overflow assertion); non-negative             | E08xx  |
| Parameters         | Every parameter bound by argument or default; positional before named; no parameter bound twice; arguments evaluate to non-negative integers; widths derived from parameters are positive | E09xx  |
| Initial state      | `init` target is drivable (output port or instance output), never an input; each net seeded at most once; value fits the target width | E0Axx  |

Validity that depends on parameter values — that every generated index lies in range and every referenced bit exists — is checked **after monomorphization (§12, phase 2), per instantiation**: an `Adder<8>` and an `Adder<16>` are each validated against their bound widths.

**Width-error attribution (E0403 vs E0906).** A non-positive port width is reported by the **phase** that establishes it. A literal width in a non-parameterized context (`A[0]` in a plain component) is a static width error (E0403). The *same* literal `A[0]` written inside a parameterized component is re-checked during specialization, where any non-positive port width — whether it came from a parameter expression (`A[N-N]`) or a bare literal — is reported as a derived-width error (E0906). The distinction is path-dependent by design: E0403 is the width-validation site, E0906 the monomorphization site; both guard width > 0, and which one fires tells the author whether the offending width was fixed in the source or produced by binding.

Additional structural rules carried from the grammar:

- A component has exactly one `connect` block and at most one `init` block; at most one component per module is marked `top`.
- Generator variables and component parameters are scoped to the construct that binds them; referencing one outside is an error.
- Instance names must be unique *before* flattening; the flattener guarantees uniqueness *after* via prefixing.

### 14.1 Diagnostics Reporting (V1 contract)

How diagnostics are surfaced is pinned for V1:

- **Fail-fast.** The pipeline stops at the **first** diagnostic. A compile reports exactly one error — the first one encountered in pipeline order — rather than collecting several per pass. (Multi-error collection is a deliberate non-goal for V1; it may be revisited, but no current behavior depends on more than one diagnostic being reported.)
- **No warnings.** V1 defines errors only. There are no warning (`W…`) diagnostics — no "unused input port", "unused constant", or "unconnected output" advisories. Warning machinery is out of scope for V1.
- **No suggestions.** Diagnostics name the offending construct and its position but do not offer "did you mean …?" similar-name hints. Suggestion machinery is out of scope for V1.

Every diagnostic carries a source position (`line ≥ 1`, `column ≥ 1`) and a message naming the offending construct. Errors detected before lexing — an undecodable, non-UTF-8 source file (§2) — are reported at the read boundary with the byte offset of the first bad byte, never as an uncaught decoding failure.

### 14.2 Documented Limits

Two implementation limits are fixed by the downstream representation and are part of the V1 contract:

- **Maximum port width: 64 bits.** The compiled ABI carries a port's value in a `uint64_t` (`shdlc_goals.md` §3.1), so a port wider than 64 bits cannot be poked or peeked and is rejected.
- **Maximum single-bit input-wire count: 65535.** The generated C indexes input wires with a 16-bit table (`base_shdl.md` §3.4), capping a flattened component at 65535 single-bit input wires.

There is deliberately **no** maximum-gate-count limit in V1: total gate count is bounded only by available memory, not by a fixed cap.

---

## 15. Design Rationale

**Why high-level constructs at all, if everything flattens to gates?** Because writing a 16-bit adder as 176 explicit single-bit connections is unreadable and unmaintainable, while writing it as a generator over a `FullAdder` component is obvious. SHDL's constructs exist purely to author the netlist concisely; none of them change *what* is built, only *how it is written*. This keeps the language faithful to the hardware while remaining humane to write.

**Why generators instead of synthesizable operators?** A `+` operator would hide a structural choice (ripple-carry? carry-lookahead?) behind behavioral syntax. Generators keep the structure explicit and under the author's control — you still describe the gates, just without copy-paste. The same tool serves instances, connections, constants, and multi-dimensional arrays, so there is one repetition mechanism to learn rather than several.

**Why 1-based indexing with bit 1 = LSB?** It matches how the values are spoken about ("bit 1", "the first bit") and makes the LSB the natural starting point for the carry chains and shifters that dominate real circuits. The convention is uniform across ports, slices, generators, and constants.

**Why a separate, flattened IR (Base SHDL) rather than compiling SHDL directly?** Splitting the language from its IR lets the front-end be expressive and the back-ends be trivial. A compiler, debugger, or future Verilog/WASM backend consumes a flat single-bit netlist with no notion of parameters, generators, slices, concatenation, or hierarchy — and recovers the high-level view only when it wants to, through metadata. The six-phase flattener is the single, well-tested place where all the convenience is mechanically removed.

**Why a unit-delay, one-level-per-cycle model?** It gives the gate-level netlist a precise, deterministic meaning without introducing a separate clocking or event-queue abstraction. Feedback, latches, and oscillators all fall out of the same rule that governs combinational logic, so state and timing need no special syntax — only gates wired back on themselves.

**Why parameters when generators already exist?** A generator repeats structure *within* a fixed-width component; a parameter lets the *interface itself* scale. Without parameters a "standard library" could only ship one width per part — a single `Register16`, never a reusable `Register<N>`. Because a parameter is resolved by the same flatten-time arithmetic that drives generators (monomorphization is just "run the generator machinery on the width too"), it adds expressiveness without adding any new runtime notion: the bound component is indistinguishable from a hand-written fixed-width one.

**Why concatenation, given slices and generators?** Slices handle one contiguous range; generators handle everything but are verbose for the common case of "glue these few signals into a bus." Concatenation fills the gap with a notation a reader understands at a glance (`{8{sign}, Value}` is sign-extension), and it lowers to exactly the per-bit connections a generator would have produced — convenience that changes only how the netlist is written, never what it is.

**Why compile-time conditionals instead of hoisting boundary cases by hand?** Real regular structures have irregular edges — the first carry-in, the last carry-out, the corner of a mesh. Without `when`, every such edge forces a copy of the loop body to live outside the loop, where it drifts out of sync during edits. `when` keeps the whole pattern in one place and is pure structural selection: it chooses *which gates exist*, never *what a gate does at runtime*, so it stays faithful to "generators produce structure, not control flow."

**Why define an initial state?** A model that advertises feedback (latches, registers, oscillators) is not actually deterministic unless cycle 0 is defined — two simulators could disagree about an SR latch's power-on value. Fixing every wire to 0 by default, with an opt-in `init` block for the cases where the seed matters, makes "the same inputs always yield the same trace" true for *every* circuit, while keeping `init` out of the structural netlist: it is power-on state, not logic, so it lives in metadata.
