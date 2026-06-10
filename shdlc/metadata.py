"""Metadata assembly (base_shdl.md §4).

Builds the single JSON object embedded in ``meta { … }``. Block order follows
the table in §4.2; all content is collected by earlier phases — this module
only arranges it, plus the purely-derived ``stats`` block.

``verify_meta`` cross-checks every gate and wire name the metadata mentions
against the structural core. The two are emitted from the same in-memory
netlist, so a mismatch is an internal invariant violation (AssertionError),
not a user-facing diagnostic; the determinism and conformance tests run it
over every fixture.
"""

from __future__ import annotations

from .phases.flatten import FlatNetlist, FlatResult


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


def verify_meta(meta: dict, netlist: FlatNetlist) -> None:
    gates = set(netlist.gates)
    inputs = set(netlist.inputs)
    outputs = set(netlist.outputs)
    # Every name a metadata block may use to refer to a net.
    wires = inputs | outputs | {f"{g}.O" for g in gates}

    for direction, groups, port_wires in (
        ("inputs", meta["ports"]["inputs"], netlist.inputs),
        ("outputs", meta["ports"]["outputs"], netlist.outputs),
    ):
        flat = [w for ws in groups.values() for w in ws]
        assert flat == port_wires, (direction, flat)

    def check_hierarchy(instances: dict) -> None:
        for name, entry in instances.items():
            if "gate" in entry:
                assert entry["gate"] in gates, (name, entry)
            else:
                for wire_or_list in entry["ports"].values():
                    refs = (
                        wire_or_list
                        if isinstance(wire_or_list, list)
                        else [wire_or_list]
                    )
                    for w in refs:
                        assert w in wires, (name, w)
                check_hierarchy(entry["instances"])

    for entry in meta["hierarchy"].values():
        check_hierarchy(entry["instances"])

    assert set(meta["source_map"]["gates"]) == gates
    for lines in meta["source_map"]["lines"].values():
        for line_gates in lines.values():
            assert set(line_gates) <= gates, line_gates

    for const in meta["constants"].values():
        assert set(const["bits"].values()) <= gates, const

    timing = meta["timing"]
    assert set(timing["output_depths"]) == outputs
    for i, name in enumerate(timing["critical_path"]):
        if i == 0:
            allowed = wires | gates  # may start at an input wire or a power pin
        elif i == len(timing["critical_path"]) - 1:
            allowed = outputs
        else:
            allowed = gates
        assert name in allowed, name

    assert set(meta["init"]) <= wires, meta["init"]
