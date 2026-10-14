"""Deterministic Base SHDL text emission (base_shdl.md §3, §7).

Output is byte-determined by the netlist and metadata alone: declaration
order is gate-registration (DFS) order, connection order is the flattener's
emission order, and the metadata is ``json.dumps`` with fixed options over
dicts whose insertion order earlier stages already fixed.
"""

from __future__ import annotations

import json

from .phases.flatten import FlatNetlist, node_str


def emit_text(netlist: FlatNetlist, meta: dict) -> str:
    lines = [
        f"component {netlist.name}"
        f"({', '.join(netlist.inputs)}) -> ({', '.join(netlist.outputs)}) {{"
    ]
    for gate in netlist.gates.values():
        lines.append(f"    {gate.name}: {gate.type_name};")
    if netlist.gates:
        lines.append("")
    lines.append("    connect {")
    for src, dst, _pos in netlist.connections:
        lines.append(f"        {node_str(src)} -> {node_str(dst)};")
    lines.append("    }")
    lines.append("}")
    lines.append("")
    lines.append("meta " + json.dumps(meta, indent=2, ensure_ascii=False))
    return "\n".join(lines) + "\n"
