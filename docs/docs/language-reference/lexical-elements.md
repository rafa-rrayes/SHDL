---
sidebar_position: 2
---

# Lexical Elements

This section covers the basic building blocks of SHDL syntax.

## Comments

SHDL supports three comment styles:

### Hash Comments (Single-line)

```
# This is a comment
A -> B;  # Inline comment
```

### String Comments (Single-line)

```
"This is also a comment"
```

### Triple-quoted Comments (Multi-line)

```
"""
This is a multi-line comment.
It can span multiple lines.
Useful for documentation blocks.
"""
```

## Identifiers

Identifiers name components, instances, ports, and constants.

### Rules

- Must start with a letter (a-z, A-Z)
- May contain letters, digits (0-9), and underscores (_)
- Case-sensitive (`MyGate` ≠ `mygate`)

### Examples

**Valid identifiers:**

```
gate1
FullAdder
my_component
ALU_8bit
DataBus
```

**Invalid identifiers:**

```
1gate       # Cannot start with digit
my-gate     # Hyphens not allowed
@special    # Special characters not allowed
```

## Operators and Delimiters

| Symbol | Name | Purpose |
|--------|------|---------|
| `->` | Arrow | Connection operator |
| `::` | Scope | Module scope resolution |
| `{}` | Braces | Block delimiters |
| `[]` | Brackets | Bit indexing, ranges, generators |
| `()` | Parentheses | Port lists |
| `:` | Colon | Type declaration, range separator |
| `;` | Semicolon | Statement terminator |
| `,` | Comma | List separator |
| `.` | Dot | Instance port access |
| `=` | Equals | Constant assignment |
| `>` | Greater-than | Generator prefix |

## Literals

### Decimal Integers

```
0
42
255
1024
```

### Hexadecimal Integers

Prefix with `0x` or `0X`:

```
0xFF
0x1A3B
0X00FF
```

### Binary Integers

Prefix with `0b` or `0B`:

```
0b1010
0b11111111
0B0001
```

## Number Formats Summary

| Format | Prefix | Example | Decimal Value |
|--------|--------|---------|---------------|
| Decimal | (none) | `100` | 100 |
| Hexadecimal | `0x` | `0x64` | 100 |
| Binary | `0b` | `0b01100100` | 100 |
