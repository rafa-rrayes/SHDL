"""Independent reader for Base SHDL (base_shdl.md §3.2, §4.2).

Deliberately shares no code with the SHDL front-end: this is the consumer's
view of the emitted format, used by the test suite to check that what we emit
is what a conforming tool would read back. Hand-rolled single-token-lookahead
scanner for the structural core; standard JSON for the metadata.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|->|[(){},:;.]|\S")
_WS = re.compile(r"(?:\s+|#[^\n]*)*")  # tolerate comments, though we never emit them

_PRIMITIVES = frozenset({"AND", "OR", "NOT", "XOR", "__VCC__", "__GND__"})


class BaseParseError(ValueError):
    pass


@dataclass(slots=True)
class BaseComponent:
    name: str
    inputs: list[str]
    outputs: list[str]
    gates: dict[str, str] = field(default_factory=dict)  # name -> primitive type
    connections: list[tuple[str, str]] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class _Scanner:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def _skip_ws(self) -> None:
        self.pos = _WS.match(self.text, self.pos).end()

    def peek(self) -> str | None:
        self._skip_ws()
        m = _TOKEN.match(self.text, self.pos)
        return m.group(0) if m else None

    def next(self) -> str:
        self._skip_ws()
        m = _TOKEN.match(self.text, self.pos)
        if not m:
            raise BaseParseError(f"unexpected end of input at offset {self.pos}")
        self.pos = m.end()
        return m.group(0)

    def expect(self, token: str) -> None:
        got = self.next()
        if got != token:
            raise BaseParseError(f"expected {token!r}, got {got!r}")


def parse_base(text: str) -> BaseComponent:
    sc = _Scanner(text)
    sc.expect("component")
    comp = BaseComponent(name=_ident(sc.next()), inputs=[], outputs=[])
    comp.inputs = _ident_list(sc)
    sc.expect("->")
    comp.outputs = _ident_list(sc)
    sc.expect("{")

    while sc.peek() != "connect":
        name = _ident(sc.next())
        sc.expect(":")
        type_name = sc.next()
        if type_name not in _PRIMITIVES:
            raise BaseParseError(f"unknown primitive type {type_name!r}")
        if name in comp.gates:
            raise BaseParseError(f"duplicate instance {name!r}")
        comp.gates[name] = type_name
        sc.expect(";")

    sc.expect("connect")
    sc.expect("{")
    while sc.peek() != "}":
        src = _signal(sc)
        sc.expect("->")
        dst = _signal(sc)
        sc.expect(";")
        comp.connections.append((src, dst))
    sc.expect("}")
    sc.expect("}")

    if sc.peek() == "meta":
        sc.expect("meta")
        sc._skip_ws()
        try:
            comp.meta, end = json.JSONDecoder().raw_decode(sc.text, sc.pos)
        except json.JSONDecodeError as e:
            raise BaseParseError(f"malformed meta JSON: {e}") from e
        if sc.text[end:].strip():
            raise BaseParseError("trailing content after meta object")
    elif sc.peek() is not None:
        raise BaseParseError(f"unexpected token {sc.peek()!r} after component")
    return comp


def _ident(token: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
        raise BaseParseError(f"expected identifier, got {token!r}")
    return token


def _ident_list(sc: _Scanner) -> list[str]:
    sc.expect("(")
    names: list[str] = []
    if sc.peek() != ")":
        names.append(_ident(sc.next()))
        while sc.peek() == ",":
            sc.next()
            names.append(_ident(sc.next()))
    sc.expect(")")
    return names


def _signal(sc: _Scanner) -> str:
    name = _ident(sc.next())
    if sc.peek() == ".":
        sc.next()
        return f"{name}.{_ident(sc.next())}"
    return name
