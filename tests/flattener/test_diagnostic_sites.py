"""Per-raise-site diagnostic coverage (DIA-2 / DIA-8).

The diagnostics-matrix file (``test_diagnostics_matrix.py``) pins one trigger
per *code* and enforces ``codes-tested == ErrorCode enum``. That is necessary
but not sufficient: a code reached via one ``raise err(`` site can silently
break on another. This file extends the completeness mechanism to **per raise
site**.

Mechanism
---------
1. ``_inventory()`` mechanically scans every ``flattener/**/*.py`` file with the
   ``ast`` module and returns the set of ``(relpath, line)`` keys for every
   ``raise err(...)`` statement, together with the ``ErrorCode`` named at each
   site. This is re-derived from the tree on every run, so a new raise site
   cannot land untested (the same enforcement pattern as the enum-completeness
   assert — DIA-2).
2. ``REGISTRY`` curates one entry per site: a minimal trigger program plus the
   exact ``(line, col)`` the diagnostic must carry (DIA-8). A handful of sites
   are unreachable from user input through the public pipeline; those carry a
   ``monkeypatch`` recipe that disables the upstream guard so the backstop
   itself is still exercised (mirroring the E0504 monkeypatch in the matrix).
3. ``test_sites_complete`` asserts ``REGISTRY keys == inventory keys`` *and*
   that each registry entry names the code the source actually raises there.
4. ``test_site_trigger`` runs every trigger and proves it reaches **that exact
   site**: the innermost ``flattener/`` frame in the raised exception's
   traceback (excluding ``diagnostics.py``) must be the registered line. It
   also asserts the code and the exact line:col (DIA-8).

Failures embed the trigger source so the case is replayable from the message.
"""

from __future__ import annotations

import ast
import os
import traceback
from pathlib import Path

import pytest
from helpers import flatten_source

import flattener.pipeline as pipeline
from flattener.diagnostics import ErrorCode, SHDLError

FLATTENER = Path(pipeline.__file__).parent


# --------------------------------------------------------------------------- #
# Mechanical site inventory
# --------------------------------------------------------------------------- #


def _site_code(call: ast.Call) -> str | None:
    """The ErrorCode named as ``err(...)``'s first argument, or None if the
    code is computed at runtime (the one E0403/E0906 dual-code site)."""
    if not call.args:
        return None
    a = call.args[0]
    if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "ErrorCode":
        return a.attr
    return None  # dynamic code (resolved at runtime)


def _inventory() -> dict[tuple[str, int], str | None]:
    """Map ``(relpath, lineno) -> code`` for every ``raise err(...)`` site."""
    sites: dict[tuple[str, int], str | None] = {}
    for path in sorted(FLATTENER.rglob("*.py")):
        tree = ast.parse(path.read_text())
        rel = path.relative_to(FLATTENER.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            call = node.exc
            if isinstance(call.func, ast.Name) and call.func.id == "err":
                sites[(rel, node.lineno)] = _site_code(call)
    return sites


# --------------------------------------------------------------------------- #
# Trigger registry — one entry per raise site
# --------------------------------------------------------------------------- #

WIRE = "component W(In) -> (Out) { connect { In -> Out; } }"
INV = "component Inv(A) -> (Y) { connect { A -> Y; } }"


def _t(
    code: str,
    line: int,
    col: int,
    source: str,
    *,
    aux: dict | None = None,
    needs: str | None = None,
    note: str | None = None,
) -> dict:
    """One registry entry.

    ``line``/``col`` are the exact coordinates the diagnostic must carry
    (DIA-8). ``needs`` names a monkeypatch recipe for a site that is otherwise
    unreachable from user input; ``note`` documents why.
    """
    return dict(code=code, line=line, col=col, source=source, aux=aux, needs=needs, note=note)


# Each key is the (relpath, raise-line) the trigger must reach. The line equals
# the `raise err(` statement line in the current tree; test_sites_complete keeps
# these honest against the mechanical inventory.
REGISTRY: dict[tuple[str, int], dict] = {
    # --- flattener/expr.py ------------------------------------------------- #
    ("flattener/expr.py", 22): _t(
        "E0603",
        1,
        45,
        "top component M(A[2]) -> (Y) { connect { A[{j}] -> Y; } }",
    ),
    ("flattener/expr.py", 40): _t(
        "E0605",
        1,
        32,
        "top component M(A) -> (Y) { >i[4/0]{ b{i}: OR; } connect { A -> Y; } }",
    ),
    # --- flattener/lexer.py ------------------------------------------------ #
    ("flattener/lexer.py", 159): _t(
        "E0101",
        1,
        1,
        '"""unterminated triple comment\ntop component M(A) -> (Y) { connect { A -> Y; } }',
    ),
    ("flattener/lexer.py", 169): _t(
        "E0101",
        2,
        1,
        'top component M(A) -> (Y) { connect { A -> Y; } }\n"unterminated string',
    ),
    ("flattener/lexer.py", 185): _t(
        "E0101",
        1,
        19,
        "top component M(A[0x]) -> (Y) { connect { A -> Y; } }",
    ),
    ("flattener/lexer.py", 193): _t(
        "E0101",
        1,
        19,
        "top component M(A[0b]) -> (Y) { connect { A -> Y; } }",
    ),
    ("flattener/lexer.py", 200): _t(
        "E0101",
        1,
        19,
        "top component M(A[12ab]) -> (Y) { connect { A -> Y; } }",
    ),
    ("flattener/lexer.py", 230): _t(
        "E0101",
        2,
        1,
        "top component M(A) -> (Y) { connect { A -> Y; } }\n$",
    ),
    # --- flattener/loader.py ----------------------------------------------- #
    ("flattener/loader.py", 81): _t(
        "E0101",
        2,
        1,
        # Invalid UTF-8 bytes after a newline: the read-boundary diagnostic.
        None,  # built by a bytes path below (see _build_source)
        note="invalid UTF-8 source; bytes trigger built specially",
    ),
    ("flattener/loader.py", 93): _t(
        "E0701",
        1,
        1,
        None,  # missing main file; built specially (no on-disk main)
        note="main file not found; trigger points at a nonexistent path",
    ),
    ("flattener/loader.py", 110): _t(
        "E0701",
        1,
        5,
        None,  # resolved-path conflict; built specially with two lib.shdl files
        note="resolved-path conflict; built specially with two lib.shdl files",
    ),
    ("flattener/loader.py", 120): _t(
        "E0702",
        1,
        5,
        "use a::{A};\ntop component M(A) -> (Y) { connect { A -> Y; } }",
        aux={
            "a": "use b::{B};\ncomponent A(X) -> (Y) { connect { X -> Y; } }",
            "b": "use a::{A};\ncomponent B(X) -> (Y) { connect { X -> Y; } }",
        },
    ),
    ("flattener/loader.py", 131): _t(
        "E0301",
        2,
        1,
        "use lib::{Foo};\ntop component M(A) -> (Y) { connect { A -> Y; } }",
        aux={
            "lib": "component Foo(A) -> (Y) { connect { A -> Y; } }\n"
            "component Foo(A) -> (Y) { connect { A -> Y; } }",
        },
    ),
    ("flattener/loader.py", 144): _t(
        "E0701",
        1,
        5,
        "use missing::{X};\ntop component M(A) -> (Y) { connect { A -> Y; } }",
    ),
    ("flattener/loader.py", 155): _t(
        "E0701",
        1,
        5,
        None,  # case-mismatch import; built specially
        note="case-mismatch resolution; needs a real on-disk file",
    ),
    ("flattener/loader.py", 165): _t(
        "E0703",
        1,
        11,
        "use lib::{Bar};\ntop component M(A) -> (Y) { connect { A -> Y; } }",
        aux={"lib": "component Foo(A) -> (Y) { connect { A -> Y; } }"},
    ),
    ("flattener/loader.py", 171): _t(
        "E0301",
        2,
        9,
        # Two imports bring in the same component name: the second `use`'s
        # name collides with the first in module.visible. (A local-vs-import
        # collision can't reach here — `imports must precede components`, the
        # parser E0201, fires first.)
        "use a::{X};\nuse b::{X};\ntop component M(A) -> (Y) { connect { A -> Y; } }",
        aux={
            "a": "component X(A) -> (Y) { connect { A -> Y; } }",
            "b": "component X(A) -> (Y) { connect { A -> Y; } }",
        },
        note="imported name collides with an earlier import",
    ),
    # --- flattener/parser.py ----------------------------------------------- #
    ("flattener/parser.py", 80): _t(
        "E0201",
        1,
        231,
        None,  # 300-deep nesting; built specially
        # col 231 = the `{` whose entry crosses the 200-level cap (the inner
        # constant-width expr starts at col 31; the 201st `{` is at col 231).
        note="parser nesting cap; built from a deeply-nested expression",
    ),
    ("flattener/parser.py", 105): _t(
        "E0201",
        1,
        19,
        "component M(A) -> Y) { connect { A -> Y; } }",
    ),
    ("flattener/parser.py", 114): _t(
        "E0201",
        1,
        1,
        # A leading non-keyword where parse_module expects a component:
        # expect_keyword('component') fires at the offending token.
        "foo",
        note="expect_keyword 'component'; reached by a leading non-keyword",
    ),
    ("flattener/parser.py", 133): _t(
        "E0201",
        2,
        1,
        "component M(A) -> (Y) { connect { A -> Y; } }\nuse lib::{X};",
        aux={"lib": "component X(A) -> (Y) { connect { A -> Y; } }"},
    ),
    ("flattener/parser.py", 170): _t(
        "E0201",
        2,
        7,
        "component M(A) -> (Y) { connect { A -> Y; } }\nmeta {",
    ),
    ("flattener/parser.py", 181): _t(
        "E0201",
        2,
        9,
        "component M(A) -> (Y) { connect { A -> Y; } }\nmeta {} junk",
    ),
    ("flattener/parser.py", 326): _t(
        "E0604",
        1,
        36,
        "top component M(A) -> (Y) { >i[2]{ 5 -> b; } connect { A -> Y; } }",
    ),
    ("flattener/parser.py", 334): _t(
        "E0604",
        1,
        54,
        "top component M(A) -> (Y) { n: NOT; connect { >i[2]{ 5 -> Y; } } }",
    ),
    ("flattener/parser.py", 352): _t(
        "E0201",
        1,
        29,
        "top component M(A) -> (Y) { c{i} = 1; connect { A -> Y; } }",
    ),
    ("flattener/parser.py", 366): _t(
        "E0201",
        1,
        33,
        "top component M(A) -> (Y) { foo bar; connect { A -> Y; } }",
    ),
    ("flattener/parser.py", 591): _t(
        "E0201",
        1,
        31,
        "top component M(A) -> (Y) { K[+] = 1; connect { A -> Y; } }",
    ),
    ("flattener/parser.py", 635): _t(
        "E0201",
        1,
        43,
        "top component M(A) -> (Y) { >i[2]{ when {i} { x: OR; } } connect { A -> Y; } }",
    ),
    # --- flattener/phases/constants.py ------------------------------------- #
    ("flattener/phases/constants.py", 56): _t(
        "E0308",
        1,
        36,
        # A constant K referenced at bit 1 materializes a power pin named
        # 'K_bit1'; declaring an instance with that exact name collides.
        "top component M(A) -> (Y) { K = 1; K_bit1: NOT; "
        "connect { A -> K_bit1.A; K_bit1.O -> Y; K -> Y; } }",
        note="instance name collides with a materialized constant power pin",
    ),
    # --- flattener/phases/expand.py ---------------------------------------- #
    ("flattener/phases/expand.py", 65): _t(
        "E0601",
        1,
        32,
        "top component M(A) -> (Y) { >i[1:1000001]{ b{i}: OR; } connect { A -> Y; } }",
        note="SCL-7 instance-count cap (MAX_RANGE_VALUES) via _guard_span",
    ),
    ("flattener/phases/expand.py", 132): _t(
        "E0601",
        1,
        37,
        "top component M(A) -> (Y) { >i[1:3, 0-1]{ b{i}: OR; } connect { A -> Y; } }",
        note="bare negative value in a multi-range list",
    ),
    ("flattener/phases/expand.py", 138): _t(
        "E0601",
        1,
        32,
        "top component M(A) -> (Y) { >i[0]{ b{i}: OR; } connect { A -> Y; } }",
        note="count range [0] is empty",
    ),
    ("flattener/phases/expand.py", 149): _t(
        "E0601",
        1,
        32,
        "top component M(A) -> (Y) { >i[0-1:3]{ b{i}: OR; } connect { A -> Y; } }",
        note="RangeAB lower bound negative",
    ),
    ("flattener/phases/expand.py", 151): _t(
        "E0601",
        1,
        32,
        "top component M(A) -> (Y) { >i[2:1]{ b{i}: OR; } connect { A -> Y; } }",
        note="RangeAB ill-ordered",
    ),
    ("flattener/phases/expand.py", 161): _t(
        "E0601",
        1,
        32,
        "top component M(A) -> (Y) { >i[:0]{ b{i}: OR; } connect { A -> Y; } }",
        note="RangeTo bound < 1",
    ),
    ("flattener/phases/expand.py", 171): _t(
        "E0601",
        1,
        61,
        "top component M(A[2]) -> (Y) { b1: OR; b2: OR; "
        "connect { >i[0-1:]{ A[{i}] -> b{i}.A; } A[1] -> b1.B; A[2] -> b2.B; "
        "b1.O -> Y; } }",
        note="RangeOpen lower bound negative",
    ),
    ("flattener/phases/expand.py", 174): _t(
        "E0601",
        1,
        53,
        # Open range [5:] over governing signal A of width 2 resolves to the
        # empty [5:2]: the lower bound exceeds the scanned governing width.
        "top component M(A[2]) -> (Y) { b5: OR; "
        "connect { >i[5:]{ A[{i}] -> b5.A; } A[1] -> b5.B; b5.O -> Y; } }",
        note="open range resolves to empty after governing-signal scan",
    ),
    ("flattener/phases/expand.py", 314): _t(
        "E0307",
        1,
        57,
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.A; n -> Y; } }",
        note="signal_width: instance used as a whole signal",
    ),
    ("flattener/phases/expand.py", 320): _t(
        "E0307",
        1,
        39,
        "top component M(A) -> (Y) { connect { Ghost -> Y; } }",
        note="signal_width: unknown whole signal",
    ),
    ("flattener/phases/expand.py", 323): _t(
        "E0307",
        1,
        47,
        "top component M(A) -> (Y) { connect { A -> Y; ghost.O -> Y; } }",
        needs="disable_check_role",
        note="signal_width port-branch backstop: unknown instance. Shadowed by "
        "instance_port_dir (expand.py:350) via _check_role, which validates "
        "the same port first.",
    ),
    ("flattener/phases/expand.py", 328): _t(
        "E0307",
        1,
        57,
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.A; n.Z -> Y; } }",
        needs="disable_check_role",
        note="signal_width port-branch backstop: primitive has no such port. "
        "Shadowed by instance_port_dir (expand.py:357).",
    ),
    ("flattener/phases/expand.py", 336): _t(
        "E0307",
        2,
        55,
        "component C(A) -> (O) { connect { A -> O; } }\n"
        "top component M(A) -> (Y) { c: C; connect { A -> c.A; c.Z -> Y; } }",
        needs="disable_check_role",
        note="signal_width port-branch backstop: component has no such port. "
        "Shadowed by instance_port_dir (expand.py:365).",
    ),
    ("flattener/phases/expand.py", 350): _t(
        "E0307",
        1,
        44,
        "top component M(A) -> (Y) { connect { A -> ghost.A; A -> Y; } }",
        note="instance_port_dir: unknown instance (destination)",
    ),
    ("flattener/phases/expand.py", 357): _t(
        "E0307",
        1,
        52,
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.Z; n.O -> Y; } }",
        note="instance_port_dir: primitive has no such port (destination)",
    ),
    ("flattener/phases/expand.py", 365): _t(
        "E0307",
        2,
        50,
        "component C(A) -> (O) { connect { A -> O; } }\n"
        "top component M(A) -> (Y) { c: C; connect { A -> c.Z; c.O -> Y; } }",
        note="instance_port_dir: component has no such port (destination)",
    ),
    ("flattener/phases/expand.py", 394): _t(
        "E0301",
        1,
        29,
        "top component M(A) -> (Y) { A: NOT; connect { A -> A.A; A.O -> Y; } }",
        needs="disable_validate",
        note="declare_name backstop: instance name collides with a port. "
        "validate.py walks every component and rejects this first; the "
        "expand-phase guard is the shadowed backstop.",
    ),
    ("flattener/phases/expand.py", 400): _t(
        "E0301",
        1,
        37,
        "top component M(A) -> (Y) { n: NOT; n: NOT; connect { A -> n.A; n.O -> Y; } }",
        needs="disable_validate",
        note="declare_name backstop: duplicate instance/constant name. "
        "Shadowed by the per-component name check at validate.py:99.",
    ),
    ("flattener/phases/expand.py", 425): _t(
        "E0403",
        1,
        29,
        "top component M(A) -> (Y) { K[1-2] = 0; connect { A -> Y; } }",
        note="on_constant: derived (expand-phase) non-positive width",
    ),
    ("flattener/phases/expand.py", 431): _t(
        "E0801",
        1,
        29,
        "top component M(A) -> (Y) { K[1+1] = 9; connect { A -> Y; } }",
        note="on_constant: derived-width overflow at the expand phase",
    ),
    ("flattener/phases/expand.py", 459): _t(
        "E0602",
        1,
        50,
        "top component M(A) -> (Y) { b1: OR; "
        "connect { >i[1:]{ A -> b1.A; } A -> b1.B; b1.O -> Y; } }",
        note="resolve_open_conn: no governing signal",
    ),
    ("flattener/phases/expand.py", 466): _t(
        "E0602",
        1,
        75,
        "top component M(A[2], C[3]) -> (Y) { b1: OR; b2: OR; b3: OR; "
        "connect { >i[1:]{ A[{i}] -> b{i}.A; C[{i}] -> b{i}.B; } b1.O -> Y; } }",
        note="resolve_open_conn: ambiguous (multiple widths)",
    ),
    ("flattener/phases/expand.py", 500): _t(
        "E0601",
        1,
        40,
        "top component M(A) -> (Y) { connect { {0{A}} -> Y; } }",
        note="resolve_concat_item: replication count < 1",
    ),
    ("flattener/phases/expand.py", 543): _t(
        "E0602",
        1,
        32,
        "top component M(A) -> (Y) { >i[1:]{ b{i}: OR; } connect { A -> Y; } }",
        needs="disable_mono_open_reject",
        note="_reject_open_decl backstop: open range in declaration context. "
        "monomorphize's discovery walk rejects it first via the identical "
        "_reject_open_decl_range (monomorphize.py:458); this is the shadowed "
        "expand-phase twin.",
    ),
    # --- flattener/phases/expander.py -------------------------------------- #
    ("flattener/phases/expander.py", 77): _t(
        "E0402",
        1,
        42,
        "top component M(A[2]) -> (Y) { connect { A[5] -> Y; } }",
    ),
    ("flattener/phases/expander.py", 86): _t(
        "E0404",
        1,
        45,
        "top component M(A[4]) -> (Y[2]) { connect { A[3:2] -> Y; } }",
    ),
    ("flattener/phases/expander.py", 92): _t(
        "E0402",
        1,
        45,
        "top component M(A[2]) -> (Y[3]) { connect { A[1:3] -> Y; } }",
        note="slice upper bound past the signal width",
    ),
    ("flattener/phases/expander.py", 169): _t(
        "E0505",
        1,
        67,
        "top component M(A) -> (Y) { g: AND; connect { A -> g.A; A -> g.B; g.A -> Y; } }",
        note="_check_role: instance input as a source",
    ),
    ("flattener/phases/expander.py", 176): _t(
        "E0505",
        1,
        52,
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.O; n.O -> Y; } }",
        note="_check_role: instance output as a destination",
    ),
    ("flattener/phases/expander.py", 185): _t(
        "E0505",
        1,
        51,
        "top component M(A) -> (Y) { K = 1; connect { A -> K; A -> Y; } }",
        note="_check_role: constant as a destination",
    ),
    ("flattener/phases/expander.py", 197): _t(
        "E0505",
        1,
        50,
        "top component M(A) -> (Y, Z) { connect { A -> Y; Y -> Z; } }",
        note="_check_role: output port as a source",
    ),
    ("flattener/phases/expander.py", 203): _t(
        "E0505",
        1,
        47,
        "top component M(A, B) -> (Y) { connect { A -> B; A -> Y; } }",
        note="_check_role: input port as a destination",
    ),
    ("flattener/phases/expander.py", 214): _t(
        "E0505",
        1,
        47,
        "top component M(A) -> (Y[2]) { connect { A -> {2{Y}}; } }",
        note="replication in a connection destination",
    ),
    ("flattener/phases/expander.py", 227): _t(
        "E0401",
        1,
        45,
        "top component M(A[2]) -> (Y[3]) { connect { A -> Y; } }",
    ),
    ("flattener/phases/expander.py", 236): _t(
        "E0504",
        1,
        57,
        "top component M(A) -> (Y) { n: NOT; connect { A -> n.A; n.O -> n.O; n.O -> Y; } }",
        needs="self_connection",
        note="self-connection backstop; role checks normally fire first (EXP-9)",
    ),
    ("flattener/phases/expander.py", 256): _t(
        "E0501",
        1,
        50,
        "top component M(A, B) -> (Y) { connect { A -> Y; B -> Y; } }",
    ),
    ("flattener/phases/expander.py", 268): _t(
        "E0503",
        1,
        1,
        "top component M(A) -> (Y, Z) { connect { A -> Y; } }",
    ),
    ("flattener/phases/expander.py", 283): _t(
        "E0502",
        1,
        29,
        "top component M(A) -> (Y) { g: AND; connect { A -> g.A; g.O -> Y; } }",
    ),
    # --- flattener/phases/flatten.py --------------------------------------- #
    ("flattener/phases/flatten.py", 111): _t(
        "E0308",
        2,
        40,
        "component FA(A) -> (Y) { x1: NOT; connect { A -> x1.A; x1.O -> Y; } }\n"
        "top component M(A) -> (Y, Z) { fa: FA; fa_x1: NOT; "
        "connect { A -> fa.A; fa.Y -> Y; A -> fa_x1.A; fa_x1.O -> Z; } }",
        note="flattened gate name collides with an existing gate",
    ),
    ("flattener/phases/flatten.py", 118): _t(
        "E0308",
        1,
        25,
        "component C(A) -> (O) { b: NOT; connect { A -> b.A; b.O -> O; } }\n"
        "top component M(A) -> (a_b) { a: C; connect { A -> a.A; a.O -> a_b; } }",
        note="flattened gate name collides with a top-level port wire (FLT-9)",
    ),
    ("flattener/phases/flatten.py", 189): _t(
        "E0501",
        1,
        50,
        "top component M(A, B) -> (Y) { connect { A -> Y; B -> Y; } }",
        needs="disable_conn_validate",
        note="flatten-path multi-driver backstop; per-component check fires first",
    ),
    ("flattener/phases/flatten.py", 227): _t(
        "E0506",
        2,
        87,
        f"{WIRE}\n"
        "top component M(X) -> (Y) { w1: W; w2: W; "
        "connect { w1.Out -> w2.In; w2.Out -> w1.In; w1.Out -> Y; } }",
        note="pure alias cycle with no gate",
    ),
    ("flattener/phases/flatten.py", 237): _t(
        "E0502",
        1,
        43,
        "component C(A) -> (O) { g: AND; connect { A -> g.A; g.O -> O; } }\n"
        "top component M(A) -> (Y) { c: C; connect { c.O -> Y; } }",
        needs="disable_conn_validate",
        note="flatten-path floating-input backstop; per-component check fires first",
    ),
    ("flattener/phases/flatten.py", 259): _t(
        "E0503",
        1,
        1,
        "top component M(A) -> (Y, Z) { connect { A -> Y; } }",
        needs="disable_conn_validate",
        note="flatten-path floating-output backstop; per-component check fires first",
    ),
    ("flattener/phases/flatten.py", 292): _t(
        "E0A03",
        1,
        44,
        "top component M(A) -> (Y) { n: NOT; init { n.O = 2; } connect { A -> n.A; n.O -> Y; } }",
    ),
    ("flattener/phases/flatten.py", 303): _t(
        "E0A01",
        1,
        36,
        "top component M(A) -> (Y) { init { Y = 1; } connect { A -> Y; } }",
        note="seeded output aliases straight back to an input (resolve-time)",
    ),
    ("flattener/phases/flatten.py", 310): _t(
        "E0A02",
        1,
        53,
        "top component M(A) -> (Y) { n: NOT; init { n.O = 1; Y = 0; } "
        "connect { A -> n.A; n.O -> Y; } }",
    ),
    ("flattener/phases/flatten.py", 366): _t(
        "E0A01",
        1,
        44,
        "top component M(A) -> (Y) { n: NOT; init { n.A = 1; } connect { A -> n.A; n.O -> Y; } }",
        note="_check_init_target: instance input pin",
    ),
    ("flattener/phases/flatten.py", 374): _t(
        "E0A01",
        1,
        54,
        "top component M(A) -> (Y, Z) { K = 1; n: NOT; init { K = 1; } "
        "connect { A -> n.A; n.O -> Y; K -> Z; } }",
        note="_check_init_target: constant target",
    ),
    ("flattener/phases/flatten.py", 381): _t(
        "E0A01",
        1,
        36,
        "top component M(A) -> (Y) { init { A = 1; } connect { A -> Y; } }",
        note="_check_init_target: input port target",
    ),
    # --- flattener/phases/monomorphize.py ---------------------------------- #
    ("flattener/phases/monomorphize.py", 130): _t(
        "E0903",
        2,
        41,
        "component P<N = 1>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P<N = 1, 2>; "
        "connect { A -> p.A; p.Y -> Y; } }",
        note="positional argument after named",
    ),
    ("flattener/phases/monomorphize.py", 136): _t(
        "E0903",
        2,
        37,
        "component P<N = 1>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P<1, 2>; connect { A -> p.A; p.Y -> Y; } }",
        note="too many positional arguments",
    ),
    ("flattener/phases/monomorphize.py", 147): _t(
        "E0901",
        2,
        34,
        "component P<N = 1>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P<Q = 3>; connect { A -> p.A; p.Y -> Y; } }",
        note="named argument matches no parameter",
    ),
    ("flattener/phases/monomorphize.py", 154): _t(
        "E0904",
        2,
        37,
        "component P<N = 1>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P<1, N = 2>; "
        "connect { A -> p.A; p.Y -> Y; } }",
        note="parameter bound twice",
    ),
    ("flattener/phases/monomorphize.py", 161): _t(
        "E0905",
        2,
        34,
        "component P<N = 1>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P<0 - 3>; connect { A -> p.A; p.Y -> Y; } }",
        note="argument evaluates to a negative integer",
    ),
    ("flattener/phases/monomorphize.py", 172): _t(
        "E0902",
        2,
        29,
        "component P<N>(A) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { p: P; connect { A -> p.A; p.Y -> Y; } }",
        note="parameter unbound (no arg, no default)",
    ),
    ("flattener/phases/monomorphize.py", 380): _t(
        "E0902",
        1,
        13,
        # --top selects a non-top-marked parameterized component without a
        # default. validate.py:88 only rejects `top`-marked params, so this
        # selection-path E0902 is the one that fires. Position is the param.
        "component P<N>(A) -> (Y) { connect { A -> Y; } }\n"
        "component Q(A) -> (Y) { connect { A -> Y; } }",
        needs="top_selects_param",
        note="monomorphize top selection: parameterized top without defaults",
    ),
    ("flattener/phases/monomorphize.py", 399): _t(
        "E0311",
        1,
        29,
        "top component R(A) -> (Y) { r: R; connect { A -> r.A; r.Y -> Y; } }",
    ),
    ("flattener/phases/monomorphize.py", 421): _t(
        "E0901",
        1,
        32,
        "top component M(A) -> (Y) { g: AND<1>; connect { A -> g.A; g.O -> Y; } }",
        needs="disable_validate",
        note="primitive-with-params backstop at the monomorphize discovery "
        "site. validate.py:154 rejects it first for every component (used or "
        "not); reached only with validation disabled.",
    ),
    ("flattener/phases/monomorphize.py", 429): _t(
        "E0306",
        1,
        32,
        "top component M(A) -> (Y) { u: Mystery; connect { A -> u.A; u.O -> Y; } }",
        needs="disable_validate",
        note="unknown-type backstop at the monomorphize discovery site. "
        "validate.py:161 rejects it first; reached only with validation "
        "disabled.",
    ),
    ("flattener/phases/monomorphize.py", 458): _t(
        "E0602",
        1,
        32,
        # Open range in a declaration-context generator: monomorphize's
        # discovery walk rejects it during specialization (this is the live
        # site; the expand-phase twin at expand.py:543 is the backstop).
        "top component M(A) -> (Y) { >i[1:]{ b{i}: OR; } connect { A -> Y; } }",
        note="_reject_open_decl_range: open decl-range during specialization",
    ),
    ("flattener/phases/monomorphize.py", 475): _t(
        "E0403",
        1,
        13,
        "component C(A[0]) -> (Y) { connect { A -> Y; } }\n"
        "top component M(A) -> (Y) { c: C; connect { A -> c.A; c.Y -> Y; } }",
        note="_resolve_port_widths: non-positive width, non-param (E0403)",
    ),
    # --- flattener/pipeline.py --------------------------------------------- #
    ("flattener/pipeline.py", 48): _t(
        "E0001",
        1,
        1,
        "top component M(A) -> (Y) { connect { A -> Y; } }",
        needs="top_not_found",
        note="--top names a component that does not exist",
    ),
    ("flattener/pipeline.py", 60): _t(
        "E0001",
        1,
        1,
        "component A1(X) -> (Y) { connect { X -> Y; } }\n"
        "component B1(X) -> (Y) { connect { X -> Y; } }",
        note="ambiguous top: no marker, multiple components",
    ),
    ("flattener/pipeline.py", 82): _t(
        "E0001",
        1,
        1,
        "top component M(A) -> (Y) { connect { A -> Y; } }",
        needs="bad_source_date_epoch",
        note="garbage SOURCE_DATE_EPOCH (ROB-6)",
    ),
    # --- flattener/validate.py --------------------------------------------- #
    ("flattener/validate.py", 34): _t(
        "E0303",
        1,
        29,
        "top component M(A) -> (Y) { __g: NOT; connect { A -> __g.A; __g.O -> Y; } }",
    ),
    ("flattener/validate.py", 40): _t(
        "E0304",
        1,
        17,
        "top component M(A_1_) -> (Y) { connect { A_1_ -> Y; } }",
    ),
    ("flattener/validate.py", 55): _t(
        "E0310",
        2,
        1,
        "top component A1(X) -> (Y) { connect { X -> Y; } }\n"
        "top component B1(X) -> (Y) { connect { X -> Y; } }",
    ),
    ("flattener/validate.py", 66): _t(
        "E0305",
        1,
        1,
        "component AND(A, B) -> (O) { o1: OR; connect { A -> o1.A; B -> o1.B; o1.O -> O; } }",
    ),
    ("flattener/validate.py", 74): _t(
        "E0309",
        1,
        1,
        "top component M(A) -> (Y) { n: NOT; }",
        note="zero connect blocks",
    ),
    ("flattener/validate.py", 81): _t(
        "E0309",
        1,
        45,
        "top component M(A) -> (Y) { n: NOT; init {} init {} connect { A -> n.A; n.O -> Y; } }",
        note="more than one init block",
    ),
    ("flattener/validate.py", 88): _t(
        "E0902",
        1,
        1,
        "top component P<N>(A) -> (Y) { connect { A -> Y; } }",
        note="top-marked parameterized component without defaults",
    ),
    ("flattener/validate.py", 99): _t(
        "E0301",
        1,
        37,
        "top component M(A) -> (Y) { n: NOT; n: NOT; connect { A -> n.A; n.O -> Y; } }",
        note="duplicate plain name at the validate site",
    ),
    ("flattener/validate.py", 154): _t(
        "E0901",
        1,
        32,
        "top component M(A) -> (Y) { g: AND<1>; connect { A -> g.A; g.O -> Y; } }",
        note="primitive instantiated with parameters (validate site)",
    ),
    ("flattener/validate.py", 161): _t(
        "E0306",
        1,
        32,
        "top component M(A) -> (Y) { u: Mystery; connect { A -> u.A; u.O -> Y; } }",
        note="unknown component type (validate site)",
    ),
    ("flattener/validate.py", 174): _t(
        "E0403",
        1,
        29,
        "top component M(A) -> (Y) { K[0] = 1; connect { A -> Y; } }",
        note="non-positive constant width literal (validate site)",
    ),
    ("flattener/validate.py", 180): _t(
        "E0801",
        1,
        29,
        "top component M(A) -> (Y) { K[2] = 9; connect { A -> Y; } }",
        note="constant value overflows its declared width (validate site)",
    ),
}


# --------------------------------------------------------------------------- #
# Specially-built sources (bytes / on-disk layout / env / monkeypatch recipes)
# --------------------------------------------------------------------------- #


def _drive(entry: dict, tmp_path, monkeypatch) -> SHDLError:
    """Run the trigger and return the raised SHDLError (or raise AssertionError
    embedding the trigger if nothing was raised)."""
    needs = entry["needs"]
    source = entry["source"]

    # Sites whose minimal trigger is a non-source artifact (bytes, missing file,
    # on-disk layout). These are identified by note + (source is None) + no
    # monkeypatch recipe.
    if entry["note"] and source is None and needs is None:
        return _drive_special(entry, tmp_path, monkeypatch)
    if needs == "self_connection":
        import flattener.phases.expander as expander

        monkeypatch.setattr(expander, "_check_role", lambda *a, **k: None)
    elif needs == "disable_conn_validate":
        monkeypatch.setattr(pipeline, "validate_component_connections", lambda *a, **k: None)
    elif needs == "disable_check_role":
        # The signal-width port-branch (unknown-instance / no-such-port) is a
        # backstop: _check_role -> instance_port_dir validates the same port
        # first (EXP-8 / the E0504 pattern). Disable the role check so the
        # width-lookup backstop is the one that fires.
        import flattener.phases.expander as expander

        monkeypatch.setattr(expander, "_check_role", lambda *a, **k: None)
    elif needs == "disable_validate":
        # validate_program runs first and rejects unknown types, primitives
        # with parameters, and duplicate/colliding names for every component
        # (used or not). The matching expand/monomorphize-phase raises are
        # therefore backstops, reached only with validation disabled.
        monkeypatch.setattr(pipeline, "validate_program", lambda *a, **k: None)
    elif needs == "disable_mono_open_reject":
        # monomorphize's discovery walk rejects an open-ended range in
        # declaration context first; the identical expand-phase guard
        # (_reject_open_decl) is the shadowed backstop. Stub the monomorphize
        # reject (return a concrete bound) so expansion is reached.
        import flattener.phases.monomorphize as mm

        monkeypatch.setattr(mm, "_reject_open_decl_range", lambda gen, item, env: 1)
    elif needs == "top_selects_param":
        # --top names a (non-top-marked) parameterized component without
        # defaults: validate.py only rejects `top`-marked params, so the
        # selection path's E0902 in monomorphize() is the one that fires.
        return _capture(lambda: flatten_source(tmp_path, source, top="P"))
    elif needs == "top_not_found":
        return _capture(lambda: flatten_source(tmp_path, source, top="Nope"))
    elif needs == "bad_source_date_epoch":
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "notanumber")
        return _capture(lambda: flatten_source(tmp_path, source, timestamp=None))

    return _capture(lambda: flatten_source(tmp_path, source, aux=entry["aux"]))


def _drive_special(entry: dict, tmp_path, monkeypatch) -> SHDLError:
    """Build the non-source triggers identified by their note."""
    note = entry["note"]
    if note.startswith("parser nesting cap"):
        # A 300-deep `{expr}` substitution inside a constant-width arithmetic
        # expression recurses through Parser._parse_arith -> _enter, tripping
        # the MAX_NESTING_DEPTH cap (200) before any RecursionError (PAR-8).
        depth = 300
        src = (
            "top component M(A) -> (Y) { K["
            + "{" * depth
            + "1"
            + "}" * depth
            + "] = 0; connect { A -> Y; } }"
        )
        td = tmp_path / "main.shdl"
        td.write_text(src)
        return _capture(lambda: pipeline.flatten_program(str(td)))
    if note.startswith("invalid UTF-8"):
        bad = tmp_path / "main.shdl"
        bad.write_bytes(b"top component M(A) -> (Y) { connect { A -> Y; } }\n\xff\xfe")
        return _capture(lambda: pipeline.flatten_program(str(bad)))
    if note.startswith("main file not found"):
        return _capture(lambda: pipeline.flatten_program(str(tmp_path / "nonexistent.shdl")))
    if note.startswith("resolved-path conflict"):
        # `main` imports lib::X and (transitively) a second module whose own
        # `use lib::{X}` resolves a *different* file on disk than the first.
        sub = tmp_path / "sub"
        sub.mkdir()
        # main dir lib.shdl
        (tmp_path / "lib.shdl").write_text("component X(A) -> (Y) { connect { A -> Y; } }")
        # sub dir lib.shdl (different file, same module name)
        (sub / "lib.shdl").write_text("component X(A) -> (Y) { connect { A -> Y; } }")
        (sub / "mid.shdl").write_text(
            "use lib::{X};\ncomponent Mid(A) -> (Y) { connect { A -> Y; } }"
        )
        main = tmp_path / "main.shdl"
        main.write_text(
            "use lib::{X};\nuse mid::{Mid};\ntop component M(A) -> (Y) { connect { A -> Y; } }"
        )
        return _capture(lambda: pipeline.flatten_program(str(main), include_dirs=[str(sub)]))
    if note.startswith("case-mismatch"):
        import flattener.loader as loader

        (tmp_path / "lib.shdl").write_text("component X(A) -> (Y) { connect { A -> Y; } }")
        main = tmp_path / "main.shdl"
        main.write_text("use Lib::{X};\ntop component M(A) -> (Y) { connect { A -> Y; } }")

        # The IMP-11 case-mismatch guard fires only when `use Lib` opens
        # lib.shdl -- which a case-insensitive filesystem (APFS/NTFS) does but a
        # case-sensitive one (typical Linux) never will. Emulate that lookup so
        # the raise site is exercised on any host: resolve case-insensitively
        # and report the real on-disk basename, exactly as _resolve_module does
        # on a case-folding FS.
        def _ci_resolve(name, base_dir, include_dirs):
            want = f"{name}.shdl".lower()
            for d in [base_dir, *include_dirs]:
                try:
                    entries = os.listdir(d or os.curdir)
                except OSError:
                    continue
                actual = next((e for e in entries if e.lower() == want), None)
                if actual is not None:
                    stem = actual[: -len(".shdl")] if actual.endswith(".shdl") else actual
                    return os.path.abspath(os.path.join(d, actual)), stem
            return None, None

        monkeypatch.setattr(loader, "_resolve_module", _ci_resolve)
        return _capture(lambda: pipeline.flatten_program(str(main)))
    raise AssertionError(f"no special builder for note {note!r}")


def _capture(thunk) -> SHDLError:
    try:
        thunk()
    except SHDLError as e:
        return e
    raise AssertionError("trigger did not raise SHDLError")


def _innermost_site(exc: SHDLError) -> tuple[str, int]:
    """The (relpath, lineno) of the innermost flattener frame that is not in
    diagnostics.py — i.e. the actual `raise err(` statement."""
    frames = [
        f
        for f in traceback.extract_tb(exc.__traceback__)
        if "flattener" in f.filename and "diagnostics.py" not in f.filename
    ]
    assert frames, "no flattener frame in traceback"
    f = frames[-1]
    rel = Path(f.filename).relative_to(FLATTENER.parent).as_posix()
    return rel, f.lineno


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_sites_complete():
    # DIA-2: the curated registry must cover exactly the mechanical inventory of
    # `raise err(` sites — extend this assertion when a site is added, never
    # bypass it (golden_tests.md §5). Each entry must also name the code the
    # source actually raises (None for the one runtime-computed dual-code site).
    inventory = _inventory()
    inv_keys = set(inventory)
    reg_keys = set(REGISTRY)
    missing = sorted(inv_keys - reg_keys)
    stray = sorted(reg_keys - inv_keys)
    assert not missing, f"raise sites with no registry trigger: {missing}"
    assert not stray, f"registry entries for nonexistent sites: {stray}"
    # Code agreement (the dual-code site at monomorphize._resolve_port_widths is
    # computed at runtime — inventory reports None there).
    for key, code in inventory.items():
        if code is None:
            continue
        assert REGISTRY[key]["code"] == code, (
            f"{key}: registry says {REGISTRY[key]['code']}, source raises {code}"
        )


@pytest.mark.parametrize("key", sorted(REGISTRY), ids=lambda k: f"{k[0]}:{k[1]}")
def test_site_trigger(key, tmp_path, monkeypatch):
    # DIA-2 + DIA-8: every registered trigger must reach THAT raise site (proven
    # by the traceback's innermost flattener frame) and carry the exact code and
    # the exact line:col of the offending token.
    entry = REGISTRY[key]
    exc = _drive(entry, tmp_path, monkeypatch)
    d = exc.diagnostic

    reached = _innermost_site(exc)
    replay = entry["source"] if entry["source"] is not None else entry["note"]
    assert reached == key, (
        f"trigger reached {reached}, expected {key}\n"
        f"code={d.code.value} pos={d.pos}\nreplay: {replay!r}"
    )
    assert d.code is ErrorCode[entry["code"]], (
        f"{key}: expected {entry['code']}, got {d.code.value}\nreplay: {replay!r}"
    )
    # DIA-8: exact position (not just line>=1/col>=1).
    assert (d.pos.line, d.pos.col) == (entry["line"], entry["col"]), (
        f"{key}: position {d.pos.line}:{d.pos.col} != "
        f"expected {entry['line']}:{entry['col']}\nreplay: {replay!r}"
    )
