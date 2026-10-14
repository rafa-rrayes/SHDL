"""Metadata assembly (base_shdl.md §4).

Builds the single JSON object embedded in ``meta { … }``. Block order follows
the table in §4.2; all content is collected by earlier phases — this module
only arranges it, plus the purely-derived ``stats`` block.

``validate_meta`` cross-checks every gate and wire name the metadata mentions
against the structural core. The two are emitted from the same in-memory
netlist, so a mismatch is an internal-invariant violation — a flattener bug,
never user input — surfaced as a structured :class:`MetaValidationError` (not
a bare ``assert``, so it survives ``python -O`` and is directly testable). The
pipeline runs it over every flatten via ``verify_meta``; the determinism and
conformance tests run it over every fixture.
"""

from __future__ import annotations

from .phases.flatten import FlatNetlist, FlatResult


class MetaValidationError(Exception):
    """A metadata block references a name absent from the structural core.

    Carries the failing ``invariant`` tag (one of the cross-consistency rules
    below) and the offending ``detail`` so callers — and tests — can pin the
    exact violation without parsing the message string.
    """

    def __init__(self, invariant: str, detail: object) -> None:
        super().__init__(f"meta invariant {invariant!r} violated: {detail!r}")
        self.invariant = invariant
        self.detail = detail


def build_meta(
    result: FlatResult,
    timing: dict,
    *,
    description: str | None,
    source: str,
    flattened_at: str,
) -> dict:
    netlist = result.netlist

    by_type: dict[str, int] = {}
    for gate in netlist.gates.values():
        by_type[gate.type_name] = by_type.get(gate.type_name, 0) + 1

    doc: dict = {}
    if description is not None:
        doc["description"] = description
    doc["source"] = source
    doc["flattened_at"] = flattened_at

    return {
        "version": "2.0",
        "ports": {
            "inputs": netlist.input_groups,
            "outputs": netlist.output_groups,
        },
        "hierarchy": result.hierarchy,
        "source_map": {
            "gates": result.source_map_gates,
            "lines": result.source_map_lines,
        },
        "constants": {
            name: {
                "value": c["value"],
                "width": c["width"],
                "bits": {str(bit): gate for bit, gate in c["bits"].items()},
            }
            for name, c in result.constants.items()
        },
        "timing": timing,
        "monitors": {},
        "stats": {
            "total_gates": len(netlist.gates),
            "total_connections": len(netlist.connections),
            "total_ports": len(netlist.inputs) + len(netlist.outputs),
            "by_type": by_type,
        },
        "doc": doc,
        "init": result.init,
    }


def validate_meta(meta: dict, netlist: FlatNetlist) -> None:
    """Public cross-consistency validator (MET-7): every name a metadata block
    mentions must exist in the structural core. Raises
    :class:`MetaValidationError` on the first violation; returns ``None`` when
    the metadata is consistent with the netlist."""
    gates = set(netlist.gates)
    inputs = set(netlist.inputs)
    outputs = set(netlist.outputs)
    # Every name a metadata block may use to refer to a net.
    wires = inputs | outputs | {f"{g}.O" for g in gates}

    def fail(invariant: str, detail: object) -> None:
        raise MetaValidationError(invariant, detail)

    # 1. ports: the flattened wire lists reproduce the netlist port order exactly.
    for direction, groups, port_wires in (
        ("inputs", meta["ports"]["inputs"], netlist.inputs),
        ("outputs", meta["ports"]["outputs"], netlist.outputs),
    ):
        flat = [w for ws in groups.values() for w in ws]
        if flat != port_wires:
            fail("ports", (direction, flat))

    # 2/3. hierarchy: leaf gates exist; instance port wires are real nets.
    def check_hierarchy(instances: dict) -> None:
        for name, entry in instances.items():
            if "gate" in entry:
                if entry["gate"] not in gates:
                    fail("hierarchy.gate", (name, entry["gate"]))
            else:
                for wire_or_list in entry["ports"].values():
                    refs = (
                        wire_or_list
                        if isinstance(wire_or_list, list)
                        else [wire_or_list]
                    )
                    for w in refs:
                        if w not in wires:
                            fail("hierarchy.port", (name, w))
                check_hierarchy(entry["instances"])

    for entry in meta["hierarchy"].values():
        check_hierarchy(entry["instances"])

    # 4. source_map.gates is a bijection onto the gate set.
    if set(meta["source_map"]["gates"]) != gates:
        fail("source_map.gates", set(meta["source_map"]["gates"]) ^ gates)
    # 5. source_map.lines references only real gates.
    for lines in meta["source_map"]["lines"].values():
        for line_gates in lines.values():
            extra = set(line_gates) - gates
            if extra:
                fail("source_map.lines", extra)

    # 6. constants materialize to real power-pin gates.
    for const in meta["constants"].values():
        extra = set(const["bits"].values()) - gates
        if extra:
            fail("constants.bits", extra)

    # 7. timing.output_depths covers exactly the outputs.
    timing = meta["timing"]
    if set(timing["output_depths"]) != outputs:
        fail("timing.output_depths", set(timing["output_depths"]) ^ outputs)
    # 8. critical_path: start at a wire/pin, gates in the middle, output at the end.
    path = timing["critical_path"]
    for i, name in enumerate(path):
        if i == 0:
            allowed = wires | gates  # may start at an input wire or a power pin
        elif i == len(path) - 1:
            allowed = outputs
        else:
            allowed = gates
        if name not in allowed:
            fail("timing.critical_path", name)

    # 9. init targets are real nets.
    extra = set(meta["init"]) - wires
    if extra:
        fail("init", extra)


def verify_meta(meta: dict, netlist: FlatNetlist) -> None:
    """Pipeline hook (kept for the call site): delegates to
    :func:`validate_meta`. A failure here is a flattener bug, not user input."""
    validate_meta(meta, netlist)
