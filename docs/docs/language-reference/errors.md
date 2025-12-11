# SHDL Error Reference

This document describes all error codes that SHDL can produce, along with explanations and suggestions for fixing them.

## Error Code Categories

| Range | Category | Description |
|-------|----------|-------------|
| E01xx | Lexer Errors | Problems with tokenization (invalid characters, malformed literals) |
| E02xx | Parser Errors | Syntax errors (unexpected tokens, missing elements) |
| E03xx | Name Resolution | Undefined or duplicate identifiers |
| E04xx | Type Errors | Width mismatches and subscript issues |
| E05xx | Connection Errors | Missing or invalid signal connections |
| E06xx | Generator Errors | Problems with `for` loops and repetition |
| E07xx | Import Errors | Problems with `use` statements |
| E08xx | Constant Errors | Invalid constant values |
| W01xx | Warnings | Non-fatal issues that may indicate problems |

---

## Lexer Errors (E01xx)

### E0101: Invalid Character

**Description**: A character in the source file is not recognized by SHDL.

**Example**:
```shdl
component Test(A) -> (B) {
    X = @value;  // Error: '@' is not a valid character
    connect {}
}
```

**Solution**: Remove or replace the invalid character. SHDL supports:
- Letters (a-z, A-Z) for identifiers
- Digits (0-9) for numbers
- Operators: `=`, `&`, `|`, `^`, `~`, `+`, `-`
- Punctuation: `(`, `)`, `{`, `}`, `[`, `]`, `;`, `,`, `:`, `.`
- Comments: `//` for line comments, `/* */` for block comments

---

### E0102: Invalid Number Literal

**Description**: A number literal is malformed.

**Example**:
```shdl
X = 123abc;  // Error: invalid number
```

**Solution**: Ensure numbers are valid decimal, hexadecimal (`0x`), or binary (`0b`) literals.

---

### E0103: Unterminated String

**Description**: A string literal was not properly closed.

**Example**:
```shdl
use "gates.shdl   // Error: missing closing quote
```

**Solution**: Add the closing `"` to the string.

---

### E0104: Unterminated Comment

**Description**: A block comment was not properly closed with `*/`.

**Example**:
```shdl
/* This comment never ends
component Test...
```

**Solution**: Add `*/` to close the block comment.

---

### E0105: Invalid Hexadecimal Number

**Description**: A hexadecimal literal is malformed.

**Example**:
```shdl
X = 0xGHI;   // Error: G, H, I are not valid hex digits
X = 0x;      // Error: no hex digits after '0x'
```

**Solution**: Use only valid hexadecimal digits (0-9, a-f, A-F) after `0x`.

---

### E0106: Invalid Binary Number

**Description**: A binary literal is malformed.

**Example**:
```shdl
X = 0b;      // Error: no binary digits after '0b'
X = 0b123;   // The '23' part becomes a separate token
```

**Solution**: Use only `0` and `1` after `0b`.

---

## Parser Errors (E02xx)

### E0201: Unexpected Token

**Description**: The parser encountered a token that doesn't fit the expected syntax.

**Example**:
```shdl
component Test(A) -> (B) {
    AND ++   // Error: unexpected '++'
}
```

**Solution**: Check the syntax. Common issues:
- Missing operator between identifiers
- Extra punctuation
- Typo in keyword

---

### E0202: Missing Semicolon

**Description**: A statement is missing its terminating semicolon.

**Example**:
```shdl
component Test(A) -> (B) {
    g1 = And()    // Error: missing ';'
    g2 = Or();
    connect {}
}
```

**Solution**: Add `;` at the end of statements.

---

### E0203: Missing Colon

**Description**: A colon is expected (e.g., in port width declarations).

**Example**:
```shdl
component Test(A[8]) -> (B) {  // Error: should be A:8
    connect {}
}
```

**Solution**: Use `:` for width declarations: `A:8`.

---

### E0204: Missing Arrow

**Description**: The `->` separating inputs from outputs is missing.

**Example**:
```shdl
component Test(A) (B) {  // Error: missing '->'
    connect {}
}
```

**Solution**: Add `->` between input and output port lists.

---

### E0205: Missing Identifier

**Description**: An identifier is expected but not found.

**Example**:
```shdl
component (A) -> (B) {  // Error: missing component name
    connect {}
}
```

**Solution**: Add the required identifier.

---

### E0206: Missing Opening Brace

**Description**: An opening `{` is expected.

**Example**:
```shdl
component Test(A) -> (B)   // Error: missing '{'
    connect {}
}
```

**Solution**: Add `{` to open the component body.

---

### E0207: Missing Closing Brace

**Description**: A closing `}` is expected.

**Example**:
```shdl
component Test(A) -> (B) {
    connect {
        A -> B;
    // Error: missing '}'
}
```

**Solution**: Add `}` to close the block.

---

### E0208: Missing Opening Parenthesis

**Description**: An opening `(` is expected.

**Example**:
```shdl
component Test A) -> (B) {  // Error: missing '('
    connect {}
}
```

**Solution**: Add `(` before the port list.

---

### E0209: Missing Closing Parenthesis

**Description**: A closing `)` is expected.

**Example**:
```shdl
component Test(A, B -> (C) {  // Error: missing ')'
    connect {}
}
```

**Solution**: Add `)` to close the port list.

---

### E0210: Invalid Port Declaration

**Description**: A port declaration is malformed.

**Example**:
```shdl
component Test(123) -> (B) {  // Error: port must be identifier
    connect {}
}
```

**Solution**: Use valid identifiers for port names.

---

### E0215: Expected Component or Use

**Description**: Only `component` definitions or `use` statements are allowed at the top level.

**Example**:
```shdl
X = 5;  // Error: not valid at top level

component Test(A) -> (B) {
    connect {}
}
```

**Solution**: Move code inside a component body, or use `component` or `use` keywords.

---

## Name Resolution Errors (E03xx)

### E0301: Unknown Component Type

**Description**: Trying to instantiate a component that hasn't been defined.

**Example**:
```shdl
component Test(A) -> (B) {
    g1 = Annd();  // Error: 'Annd' is not defined (did you mean 'And'?)
    connect {}
}
```

**Solution**: Check the spelling of the component name. If it's from another file, use `use "file.shdl";` to import it.

---

### E0302: Undefined Signal

**Description**: Using a signal that hasn't been declared.

**Example**:
```shdl
component Test(A) -> (B) {
    connect {
        X -> B;  // Error: 'X' is not defined
    }
}
```

**Solution**: 
- Check spelling of the signal name
- Ensure the signal is declared as a port or as an output of an instance

---

### E0303: Undefined Instance

**Description**: Referencing an instance that hasn't been created.

**Example**:
```shdl
component Test(A) -> (B) {
    connect {
        g1.Q -> B;  // Error: 'g1' is not defined
    }
}
```

**Solution**: Create the instance before referencing it:
```shdl
g1 = And();
```

---

### E0304: Unknown Port

**Description**: Accessing a port that doesn't exist on a component.

**Example**:
```shdl
component Test(A) -> (B) {
    g1 = And();
    connect {
        g1.X -> B;  // Error: 'And' has no port 'X'
    }
}
```

**Solution**: Check the component definition for valid port names.

---

### E0305: Duplicate Instance Name

**Description**: Creating two instances with the same name.

**Example**:
```shdl
component Test(A) -> (B) {
    g1 = And();
    g1 = Or();  // Error: 'g1' already defined
    connect {}
}
```

**Solution**: Use unique names for each instance.

---

### E0306: Duplicate Component Definition

**Description**: Defining two components with the same name.

**Example**:
```shdl
component Test(A) -> (B) { connect {} }
component Test(X) -> (Y) { connect {} }  // Error: duplicate
```

**Solution**: Use unique names for each component.

---

## Type Errors (E04xx)

### E0401: Width Mismatch

**Description**: Connecting signals of different widths.

**Example**:
```shdl
component Test(A:8) -> (B:16) {
    connect {
        A -> B;  // Error: 8 bits doesn't match 16 bits
    }
}
```

**Solution**: 
- Use matching widths
- Use subscripts to select specific bits: `A -> B[0:8];`
- Use explicit width conversion

---

### E0402: Invalid Width

**Description**: A width value is invalid (e.g., zero or negative).

**Example**:
```shdl
component Test(A:0) -> (B) {  // Error: width must be positive
    connect {}
}
```

**Solution**: Use positive integer widths (1 or greater).

---

### E0403: Subscript Out of Range

**Description**: Bit index is beyond the signal's width.

**Example**:
```shdl
component Test(A:8) -> (B) {
    connect {
        A[10] -> B;  // Error: A is only 8 bits (0-7)
    }
}
```

**Solution**: Use indices within the valid range (0 to width-1).

---

### E0404: Invalid Bit Range

**Description**: A bit range is malformed (e.g., start > end).

**Example**:
```shdl
component Test(A:8) -> (B:4) {
    connect {
        A[7:3] -> B;  // Error: end index should be greater than start
    }
}
```

**Solution**: Ensure start index ≤ end index: `A[3:7]`.

---

## Connection Errors (E05xx)

### E0501: Missing Input Connection

**Description**: An instance input port has no driver.

**Example**:
```shdl
component Test(A) -> (B) {
    g1 = And();
    connect {
        // Error: g1.A and g1.B not connected
        g1.Q -> B;
    }
}
```

**Solution**: Connect all input ports of instances:
```shdl
connect {
    A -> g1.A;
    A -> g1.B;
    g1.Q -> B;
}
```

---

### E0502: Missing Output Driver

**Description**: An output port has no signal driving it.

**Example**:
```shdl
component Test(A) -> (B) {
    connect {
        // Error: B has no driver
    }
}
```

**Solution**: Connect a signal to the output port:
```shdl
connect {
    A -> B;
}
```

---

### E0503: Multiply Driven Signal

**Description**: A signal has more than one driver.

**Example**:
```shdl
component Test(A, B) -> (C) {
    connect {
        A -> C;
        B -> C;  // Error: C has two drivers
    }
}
```

**Solution**: Signals can only have one driver. Use logic gates or multiplexers to combine signals.

---

### E0504: Self-Connection

**Description**: A signal is connected to itself.

**Example**:
```shdl
connect {
    A -> A;  // Error: connecting A to itself
}
```

**Solution**: Remove the self-connection.

---

## Generator Errors (E06xx)

### E0601: Invalid Generator Range

**Description**: A generator range is invalid.

**Example**:
```shdl
for i in 8..0 {  // Error: start > end
    ...
}
```

**Solution**: Ensure start ≤ end in ranges.

---

### E0602: Invalid Generator Step

**Description**: The step value in a generator is invalid.

**Example**:
```shdl
for i in 0..8 step 0 {  // Error: step cannot be 0
    ...
}
```

**Solution**: Use a positive step value.

---

### E0603: Generator Variable Undefined

**Description**: The generator variable is used outside its scope.

**Example**:
```shdl
component Test(A:8) -> (B:8) {
    for i in 0..4 { ... }
    
    connect {
        A[i] -> B[0];  // Error: 'i' is not defined outside for loop
    }
}
```

**Solution**: Only use generator variables inside their `for` block.

---

### E0604: Generator Variable Type Error

**Description**: A generator variable is used incorrectly.

**Solution**: Generator variables can only be used as indices or in arithmetic expressions within the loop.

---

### E0605: Empty Generator Range

**Description**: A generator range produces no iterations.

**Example**:
```shdl
for i in 5..5 {  // Warning: no iterations
    ...
}
```

**Solution**: Use a non-empty range or remove the loop.

---

### E0606: Generator Variable Shadows

**Description**: A generator variable has the same name as an existing signal or instance.

**Example**:
```shdl
component Test(A:8) -> (B:8) {
    for A in 0..4 {  // Warning: shadows input 'A'
        ...
    }
    connect {}
}
```

**Solution**: Use a unique name for the generator variable.

---

## Import Errors (E07xx)

### E0701: File Not Found

**Description**: The imported file doesn't exist.

**Example**:
```shdl
use "nonexistent.shdl";  // Error: file not found
```

**Solution**: Check the file path and ensure the file exists.

---

### E0702: Circular Import

**Description**: File A imports file B, which imports file A.

**Solution**: Reorganize imports to break the cycle. Consider using a shared base file.

---

### E0703: Import Parse Error

**Description**: The imported file has syntax errors.

**Solution**: Fix the errors in the imported file first.

---

## Constant Errors (E08xx)

### E0801: Constant Overflow

**Description**: A constant value is too large for the target width.

**Example**:
```shdl
component Test() -> (A:8) {
    VAL = 300;  // Error: 300 > 255 (max for 8 bits)
    connect {
        VAL -> A;
    }
}
```

**Solution**: Use a smaller value or a wider signal.

---

### E0802: Invalid Constant Expression

**Description**: A constant expression is malformed.

**Solution**: Check the expression syntax.

---

### E0803: Negative Constant

**Description**: A negative value is used where unsigned is expected.

**Example**:
```shdl
X = -5;  // Error if unsigned expected
```

**Solution**: Use only non-negative values for unsigned signals.

---

## Warnings (W01xx)

Warnings indicate potential issues but don't prevent compilation.

### W0101: Unused Input Port

**Description**: An input port is declared but never used.

```shdl
component Test(A, B) -> (C) {  // Warning: B is unused
    connect {
        A -> C;
    }
}
```

---

### W0102: Unused Output Port

**Description**: An instance output is never connected.

---

### W0103: Unused Constant

**Description**: A constant is defined but never used.

---

### W0104: Unused Instance

**Description**: An instance is created but its outputs are never used.

---

### W0105: Dead Code

**Description**: Code that can never be executed or signals that can never affect outputs.

---

### W0106: Implicit Width

**Description**: A signal width is inferred rather than explicit.

---

### W0107: Unconnected Instance Output

**Description**: An instance output port is not connected to anything.

---

## Reading Error Messages

SHDL error messages follow a consistent format:

```
error[E0301]: Unknown component type 'Annd'
  --> circuit.shdl:5:10-14
     |
   5 |     g1 = Annd();
     |          ^^^^ help: did you mean 'And'?
```

Components:
1. **error[E0301]**: Severity and error code
2. **Unknown component type 'Annd'**: Description
3. **--> circuit.shdl:5:10-14**: File location (file:line:column)
4. **Source line**: The actual code with the error
5. **^^^^ help**: Pointer to the error with suggestion

Use the error code (E0301) to look up detailed information in this reference.
