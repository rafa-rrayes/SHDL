"""End-to-end flattening: phases 1-6, timing, metadata, emission.

``flatten_program`` keeps every intermediate on the returned object so the
test suite's high-level reference evaluator can interpret the phase-3 model
independently of the emitted Base SHDL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from .diagnostics import ErrorCode, err
from .emit import emit_text
from .loader import Program, load_program
from .metadata import build_meta, verify_meta
from .phases.constants import LoweredComponent, materialize_constants
from .phases.expand import ExpandedComponent, expand_all
from .phases.expander import expand_connections, validate_component_connections
from .phases.flatten import FlatResult, flatten
from .phases.monomorphize import MonoProgram, monomorphize
from .source import Pos
from .timing import compute_timing
from .validate import validate_program


@dataclass(slots=True)
class FlattenOutput:
    program: Program
    mono: MonoProgram
    expanded: dict[str, ExpandedComponent]
    lowered: dict[str, LoweredComponent]
    flat: FlatResult
    timing: dict
    meta: dict
    text: str


def select_top(program: Program, top: str | None) -> str:
    """Pick the top component of the main module: an explicit ``--top`` name,
    else the unique ``top``-marked component, else the sole component."""
    main = program.main
    names = [comp.name for comp in main.components]
    at = Pos(main.file, 1, 1)
    if top is not None:
        if top not in names:
            raise err(
                ErrorCode.E0001,
                f"--top component '{top}' not found in module '{main.name}' "
                f"(has: {', '.join(names) or 'none'})",
                at,
            )
        return top
    marked = [comp.name for comp in main.components if comp.is_top]
    if marked:  # validation guarantees at most one per module
        return marked[0]
    if len(names) == 1:
        return names[0]
    raise err(
        ErrorCode.E0001,
        f"cannot determine the top component of module '{main.name}': "
        f"no 'top' marker and {len(names)} components "
        f"({', '.join(names) or 'none'}); use --top",
        at,
    )


def resolve_timestamp(explicit: str | None) -> str:
    """doc.flattened_at: ``--timestamp`` wins, then SOURCE_DATE_EPOCH (the
    convention for reproducible builds), then the current UTC time."""
    if explicit is not None:
        return explicit
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        moment = datetime.fromtimestamp(int(epoch), tz=UTC)
    else:
        moment = datetime.now(tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def flatten_program(
    main_path: str,
    include_dirs: list[str] | None = None,
    top: str | None = None,
    timestamp: str | None = None,
) -> FlattenOutput:
    program = load_program(main_path, include_dirs)
    validate_program(program)
    top_name = select_top(program, top)

    mono = monomorphize(program, program.main_module, top_name)
    expanded = expand_all(mono)

    lowered: dict[str, LoweredComponent] = {}
    for key, ec in expanded.items():
        bit_conns = expand_connections(ec, mono)
        lc = materialize_constants(ec, bit_conns)
        validate_component_connections(ec, mono, lc.bit_conns)
        lowered[key] = lc

    flat = flatten(mono, lowered)
    timing = compute_timing(flat.netlist)
    meta = build_meta(
        flat,
        timing,
        description=program.main.doc_comment,
        source=program.main.file,
        flattened_at=resolve_timestamp(timestamp),
    )
    verify_meta(meta, flat.netlist)
    text = emit_text(flat.netlist, meta)

    return FlattenOutput(
        program=program,
        mono=mono,
        expanded=expanded,
        lowered=lowered,
        flat=flat,
        timing=timing,
        meta=meta,
        text=text,
    )
