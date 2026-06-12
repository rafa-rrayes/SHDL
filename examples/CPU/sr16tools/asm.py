"""SR16 two-pass assembler (ISA.md §2/§3).

``assemble(source)`` returns the memory image as a list of ints, covering
addresses 0 .. highest emitted address. Gaps left by ``.org`` are zero-filled
(0x0000 decodes as ``ADD R0, R0, R0``, which is harmless but *not* a trap;
programs are expected to end in HALT).

Syntax:

    ; comment            # comment
    label:  ADD r1, r2, r3
            LD  r4, [r5+3]      ; also [r5-3] and [r5]
            ST  [sp], r1
            LI  r2, 0x1234      ; pseudo: LDI low byte + LDIH high byte
            BEQ loop            ; branch targets: labels or absolute addrs
            .org 0x10
            .word 0xBEEF        ; also .word label

Mnemonics and register names are case-insensitive; ``SP`` is an alias for
``R7``. Numbers: decimal, hex (0x), binary (0b), octal (0o), optional minus.
"""

from __future__ import annotations

__all__ = ["AsmError", "assemble"]


class AsmError(Exception):
    """Assembly error, carrying the 1-based source line number."""

    def __init__(self, line: int, msg: str):
        self.line = line
        self.msg = msg
        super().__init__(f"line {line}: {msg}")


# --- encoding tables (conventional bit numbering, ISA.md §3) ----------------

_ALU_FUNCT = {"ADD": 0, "SUB": 1, "AND": 2, "OR": 3, "XOR": 4, "ADC": 7}
_SHIFT_FUNCT = {"SHL": 0, "SHR": 1, "SAR": 2, "ROL": 3, "ROR": 4, "NOT": 5}
_COND = {
    "BEQ": 0, "BNE": 1,
    "BCS": 2, "BHS": 2,
    "BCC": 3, "BLO": 3,
    "BMI": 4, "BPL": 5,
    "BLT": 6, "BGE": 7,
}

_OP_ALU, _OP_SHIFT, _OP_LDI, _OP_LDIH = 0, 1, 2, 3
_OP_LD, _OP_ST, _OP_ADDI, _OP_B = 4, 5, 6, 7
_OP_JMP, _OP_CALL, _OP_MISC = 8, 9, 10

NOP = 0xA004
HALT = 0xA005

_REGS = {f"R{i}": i for i in range(8)} | {"SP": 7}


def _reg(tok: str, line: int) -> int:
    r = _REGS.get(tok.upper())
    if r is None:
        raise AsmError(line, f"expected a register, got {tok!r}")
    return r


def _split_operands(text: str, line: int) -> list[str]:
    """Split on commas that are outside [] brackets."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth < 0:
                raise AsmError(line, "unbalanced ']'")
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if depth:
        raise AsmError(line, "unbalanced '['")
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _is_number(tok: str) -> bool:
    try:
        int(tok, 0)
        return True
    except ValueError:
        return False


def _check_range(value: int, lo: int, hi: int, what: str, line: int) -> int:
    if not lo <= value <= hi:
        raise AsmError(line, f"{what} {value} out of range [{lo}, {hi}]")
    return value


class _Line:
    """One source statement after pass 1: mnemonic + operands + address."""

    def __init__(self, num: int, addr: int, mnem: str, ops: list[str]):
        self.num = num
        self.addr = addr
        self.mnem = mnem
        self.ops = ops


def _parse_mem_operand(tok: str, line: int) -> tuple[str, str]:
    """'[rs1+off]' / '[rs1-off]' / '[rs1]' -> (reg token, offset expr)."""
    if not (tok.startswith("[") and tok.endswith("]")):
        raise AsmError(line, f"expected a memory operand [reg+off], got {tok!r}")
    inner = tok[1:-1].strip()
    for i, ch in enumerate(inner):
        if ch in "+-" and i > 0:
            return inner[:i].strip(), inner[i:].strip()
    return inner, "0"


def assemble(source: str) -> list[int]:
    labels: dict[str, int] = {}
    stmts: list[_Line] = []

    # --- pass 1: strip comments, collect labels, lay out addresses ---------
    addr = 0
    for num, raw in enumerate(source.splitlines(), start=1):
        text = raw
        for marker in (";", "#"):
            if marker in text:
                text = text[: text.index(marker)]
        text = text.strip()
        while text:
            head = text.split(None, 1)[0]
            if not head.endswith(":"):
                break
            name = head[:-1]
            if not name.isidentifier():
                raise AsmError(num, f"bad label name {name!r}")
            if name.upper() in _REGS:
                raise AsmError(num, f"label {name!r} shadows a register name")
            if name in labels:
                raise AsmError(num, f"duplicate label {name!r}")
            labels[name] = addr
            text = text[len(head):].strip()
        if not text:
            continue

        parts = text.split(None, 1)
        mnem = parts[0].upper()
        ops = _split_operands(parts[1].strip() if len(parts) > 1 else "", num)
        stmt = _Line(num, addr, mnem, ops)

        if mnem == ".ORG":
            if len(ops) != 1 or not _is_number(ops[0]):
                raise AsmError(num, ".org takes one numeric address")
            target = int(ops[0], 0)
            if target < addr:
                raise AsmError(num, f".org {target} moves backwards (at {addr})")
            addr = target
            stmt.addr = target
        elif mnem == "LI":
            if len(ops) != 2:
                raise AsmError(num, "LI takes rd, value")
            # Known numeric values fitting signed 8-bit collapse to one LDI;
            # labels always get the full 2-word pair (no relaxation pass).
            if _is_number(ops[1]) and -128 <= int(ops[1], 0) <= 127:
                addr += 1
            else:
                addr += 2
        else:
            addr += 1
        stmts.append(stmt)

    # --- pass 2: encode ----------------------------------------------------

    def value_of(tok: str, line: int) -> int:
        if _is_number(tok):
            return int(tok, 0)
        if tok in labels:
            return labels[tok]
        raise AsmError(line, f"undefined symbol {tok!r}")

    image: dict[int, int] = {}

    def emit(at: int, word: int, line: int) -> None:
        if at in image:
            raise AsmError(line, f"address {at:#x} written twice")
        image[at] = word & 0xFFFF

    for st in stmts:
        n, a, ops = st.num, st.addr, st.ops
        m = st.mnem

        def need(count: int) -> None:
            if len(ops) != count:
                raise AsmError(n, f"{m} takes {count} operand(s), got {len(ops)}")

        if m == ".ORG":
            continue

        if m == ".WORD":
            need(1)
            v = value_of(ops[0], n)
            _check_range(v, -32768, 65535, ".word value", n)
            emit(a, v, n)

        elif m in _ALU_FUNCT:
            need(3)
            rd, rs1, rs2 = (_reg(t, n) for t in ops)
            emit(a, (_OP_ALU << 12) | (rd << 9) | (rs1 << 6) | (rs2 << 3) | _ALU_FUNCT[m], n)

        elif m == "MOV":
            need(2)
            rd, rs1 = _reg(ops[0], n), _reg(ops[1], n)
            emit(a, (_OP_ALU << 12) | (rd << 9) | (rs1 << 6) | 5, n)

        elif m == "CMP":
            need(2)
            rs1, rs2 = _reg(ops[0], n), _reg(ops[1], n)
            emit(a, (_OP_ALU << 12) | (rs1 << 6) | (rs2 << 3) | 6, n)

        elif m in _SHIFT_FUNCT:
            need(2)
            rd, rs1 = _reg(ops[0], n), _reg(ops[1], n)
            emit(a, (_OP_SHIFT << 12) | (rd << 9) | (rs1 << 6) | _SHIFT_FUNCT[m], n)

        elif m in ("LDI", "LDIH"):
            need(2)
            rd = _reg(ops[0], n)
            v = value_of(ops[1], n)
            _check_range(v, -128, 255, f"{m} immediate", n)
            op = _OP_LDI if m == "LDI" else _OP_LDIH
            emit(a, (op << 12) | (rd << 9) | (v & 0xFF), n)

        elif m == "LI":
            need(2)
            rd = _reg(ops[0], n)
            v = value_of(ops[1], n)
            _check_range(v, -32768, 65535, "LI value", n)
            if _is_number(ops[1]) and -128 <= v <= 127:
                emit(a, (_OP_LDI << 12) | (rd << 9) | (v & 0xFF), n)
            else:
                emit(a, (_OP_LDI << 12) | (rd << 9) | (v & 0xFF), n)
                emit(a + 1, (_OP_LDIH << 12) | (rd << 9) | ((v >> 8) & 0xFF), n)

        elif m == "LD":
            need(2)
            rd = _reg(ops[0], n)
            base, off = _parse_mem_operand(ops[1], n)
            rs1 = _reg(base, n)
            v = _check_range(value_of(off, n), -32, 31, "LD offset", n)
            emit(a, (_OP_LD << 12) | (rd << 9) | (rs1 << 6) | (v & 0x3F), n)

        elif m == "ST":
            need(2)
            base, off = _parse_mem_operand(ops[0], n)
            rs1 = _reg(base, n)
            rs2 = _reg(ops[1], n)
            v = _check_range(value_of(off, n), -32, 31, "ST offset", n)
            emit(a, (_OP_ST << 12) | (rs2 << 9) | (rs1 << 6) | (v & 0x3F), n)

        elif m == "ADDI":
            need(3)
            rd, rs1 = _reg(ops[0], n), _reg(ops[1], n)
            v = _check_range(value_of(ops[2], n), -32, 31, "ADDI immediate", n)
            emit(a, (_OP_ADDI << 12) | (rd << 9) | (rs1 << 6) | (v & 0x3F), n)

        elif m in _COND:
            need(1)
            target = value_of(ops[0], n)
            delta = _check_range(target - (a + 1), -256, 255, "branch offset", n)
            emit(a, (_OP_B << 12) | (_COND[m] << 9) | (delta & 0x1FF), n)

        elif m in ("JMP", "CALL"):
            need(1)
            target = _check_range(value_of(ops[0], n), 0, 0xFFF, f"{m} target", n)
            op = _OP_JMP if m == "JMP" else _OP_CALL
            emit(a, (op << 12) | target, n)

        elif m == "PUSH":
            need(1)
            emit(a, (_OP_MISC << 12) | (_reg(ops[0], n) << 9) | 0, n)

        elif m == "POP":
            need(1)
            emit(a, (_OP_MISC << 12) | (_reg(ops[0], n) << 9) | 1, n)

        elif m == "RET":
            need(0)
            emit(a, (_OP_MISC << 12) | 2, n)

        elif m == "JR":
            need(1)
            emit(a, (_OP_MISC << 12) | (_reg(ops[0], n) << 6) | 3, n)

        elif m == "NOP":
            need(0)
            emit(a, NOP, n)

        elif m == "HALT":
            need(0)
            emit(a, HALT, n)

        else:
            raise AsmError(n, f"unknown mnemonic {m!r}")

    if not image:
        return []
    top = max(image)
    return [image.get(i, 0) for i in range(top + 1)]
