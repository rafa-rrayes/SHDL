"""Random VALID high-level SHDL programs for differential fuzzing (FUZ-3).

The flattener is SHDL's most complex component (six lowering phases over
parameters, generators, conditionals, slices, concat/replication, constants,
init, and hierarchy) and — until FUZ-3 — had no randomized adversary.
``gen_program`` builds a *valid-by-construction* high-level program: it tracks
every declared name and its width so that every reference resolves and every
connection's source width equals its destination width. The output is a dict
of module texts plus the main-module name; the FUZ-3 driver flattens it (which
must succeed — a diagnostic on valid-by-construction input is the bug we hunt)
and then lockstep-compares HighEval against BaseEval, cycle by cycle.

Construction strategy
---------------------
A program is a small hierarchy of 2-4 component *levels*. The deepest level is
a leaf built only from primitives; each higher level instantiates the level
below it (optionally with a compile-time parameter) and adds its own logic.
Within a component we maintain a :class:`Scope` mapping every available signal
(input ports, instance output ports, constants, the loop variables in scope)
to its width, so a connection is emitted by:

  1. picking a destination (an unfed instance input pin/bus, or an output port),
  2. building a source *signal expression of exactly that width* out of the
     signals currently in scope (slices, concat, replication, constants, ...).

Every instance input bit and every output-port bit is driven exactly once, so
the single-driver / no-floating-pin invariants hold by construction. Feedback
is introduced only inside self-owned latch leaves whose ``init`` block seeds a
fixed point (tasks/lessons.md: a feedback loop's state is *all* its gate
outputs; init must seed the whole loop or it oscillates) — so generated
feedback circuits power up stable and hold, never oscillate.

Determinism: everything is driven by the caller's ``random.Random``; the same
seed yields byte-identical text. Failures embed the full program for replay.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Identifier pools (ASCII-only per AMB-14 / WP-A lexer policy).
# ---------------------------------------------------------------------------

# Never collide with the `_<digits>_` bus-expansion reservation (shdl.md §2.2):
# our generated names are plain lowercase/CamelCase identifiers.
_PORT_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O confusion, no lowercase
_PRIMS_2 = ("AND", "OR", "XOR")


@dataclass
class Scope:
    """The signals visible at one point inside a component body.

    ``widths`` maps a *source-usable* signal base name to its bit width:
    input ports, instance output ports (as ``inst.Port`` keys), and constants.
    ``loopvars`` and ``params`` are the compile-time integers in scope (used
    only to size things; the generator keeps generator bodies literal-indexed
    so it never needs to reason about symbolic widths inside a loop).
    """

    widths: dict[str, int] = field(default_factory=dict)
    params: dict[str, int] = field(default_factory=dict)

    def sources(self) -> list[str]:
        return sorted(self.widths)


@dataclass
class CompSpec:
    """A generated component's externally visible contract.

    Port widths are *fixed literals* and never parameter-dependent: a parameter
    exists only to exercise binding (positional / named / default / dependent
    arg) and to optionally gate a ``when`` whose condition folds TRUE for every
    value we ever bind (>= 1), so the externally visible width contract is the
    same no matter what ``N`` a parent passes down. This is what makes the whole
    program valid by construction even under deep dependent-parameter chains.
    """

    name: str
    module: str
    inputs: list[tuple[str, int]]  # (name, width) — width is a literal
    outputs: list[tuple[str, int]]  # (name, width) — width is a literal
    param: tuple[str, int] | None  # (name, default) or None
    text: str
    children: list[str] = field(default_factory=list)  # instantiated type names


# ---------------------------------------------------------------------------
# Signal-expression builder: produce a source signal of an exact width.
# ---------------------------------------------------------------------------


class _ExprBuilder:
    def __init__(self, rng: random.Random, scope: Scope, consts: dict[str, int]):
        self.rng = rng
        self.scope = scope
        self.consts = consts  # const name -> declared/effective width

    def _bit_atoms(self) -> list[str]:
        """Every single-bit reference reachable from scope, as text atoms.

        Includes per-bit slices of multi-bit signals and per-bit constant
        references (which lower to power pins), giving the per-bit reference
        coverage FUZ-3 requires.
        """
        atoms: list[str] = []
        for name, w in self.scope.widths.items():
            if w == 1:
                atoms.append(name)
            else:
                atoms.extend(f"{name}[{b}]" for b in range(1, w + 1))
        # Constants contribute power-pin bits at any index (0 above the value).
        for cname, cw in self.consts.items():
            atoms.extend(f"{cname}[{b}]" for b in range(1, cw + 1))
        return atoms

    def _multibit(self, width: int) -> list[str]:
        """Signals of exactly ``width`` bits usable whole or via a full slice."""
        out = []
        for name, w in self.scope.widths.items():
            if w == width:
                out.append(name)
            elif w > width:
                # A contiguous slice [a:a+width-1] yields exactly `width` bits.
                hi = w - width + 1
                a = self.rng.randint(1, hi)
                out.append(f"{name}[{a}:{a + width - 1}]")
        return out

    def build(self, width: int) -> str:
        """A source signal expression (top-level ``Signal``) of exactly
        ``width`` bits.

        Grammar §13: a top-level ``Signal`` is a ``Primary`` or a ``Concat``,
        and a ``Concat``'s items are each a ``Primary`` or a ``Replication``
        (never another braced concat — that is rejected, E0201). So this method
        returns either a bare Primary or a single ``{...}`` concat whose items
        come from :meth:`_concat_item`; it never nests concats.
        """
        # A whole multi-bit signal or a full-width contiguous slice (a Primary).
        if width >= 2 and self.rng.random() < 0.45:
            mb = self._multibit(width)
            if mb:
                return self.rng.choice(mb)
        if width == 1 and self.rng.random() < 0.6:
            return self._primary(1)
        # Otherwise build a Concat: split the width into pieces, each piece a
        # single concat item (Primary or Replication). Items are MSB-first.
        pieces = self._split(width)
        items = [self._concat_item(p) for p in pieces]
        items.reverse()  # concat lists MSB-first
        return "{" + ", ".join(items) + "}"

    def _concat_item(self, width: int) -> str:
        """One ``ConcatItem`` of exactly ``width`` bits.

        Always realizable: a 1-bit primary realizes width 1, and a replication
        of 1-bit primaries (``n{b1, ..., bm}`` with ``n*m == width``) realizes
        any width >= 2 — so no piece width is ever unfillable.
        """
        if width == 1:
            return self._primary(1)
        # A whole/sliced multi-bit primary of exactly this width, if available.
        if self.rng.random() < 0.4:
            mb = self._multibit(width)
            if mb:
                return self.rng.choice(mb)
        # A replication n{group} with n*len(group) == width (always valid: this
        # is the only multi-bit ConcatItem form, since a braced concat may not
        # appear as a ConcatItem). Every width >= 2 divides by some n in
        # 2..width, so a replication of (width // n) 1-bit primaries fills it.
        n = self.rng.choice(self._divisors(width))  # n in 2..width, n | width
        group = ", ".join(self._primary(1) for _ in range(width // n))
        return f"{n}{{{group}}}"

    def _primary(self, width: int) -> str:
        """A single ``Primary`` (port/instance-port/constant ref or slice) of
        exactly ``width`` bits — never a brace group."""
        if width == 1:
            atoms = self._bit_atoms()
            return self.rng.choice(atoms) if atoms else self._const_bit()
        mb = self._multibit(width)
        if mb:
            return self.rng.choice(mb)
        # Defensive: callers only request width>1 when a multi-bit signal of
        # that width exists; if none, degrade to a 1-bit atom.
        atoms = self._bit_atoms()
        return atoms[0] if atoms else self._const_bit()

    def _const_bit(self) -> str:
        # When scope is empty (no inputs yet), fall back to a constant power
        # pin; the caller guarantees at least one constant exists in that case.
        cname = next(iter(self.consts))
        return f"{cname}[1]"

    def _split(self, width: int) -> list[int]:
        if width <= 1:
            return [width]
        k = self.rng.randint(1, min(4, width))
        if k == 1:
            return [width]
        # Random composition of `width` into k positive parts.
        cuts = sorted(self.rng.sample(range(1, width), k - 1))
        prev = 0
        parts = []
        for c in cuts:
            parts.append(c - prev)
            prev = c
        parts.append(width - prev)
        return parts

    @staticmethod
    def _divisors(width: int) -> list[int]:
        return [n for n in range(2, width + 1) if width % n == 0]


# ---------------------------------------------------------------------------
# Leaf components (primitives only): combinational and self-owned latch.
# ---------------------------------------------------------------------------


def _gen_leaf_comb(rng: random.Random, name: str, module: str) -> CompSpec:
    """A combinational leaf: a few primitive gates wired DAG-by-construction."""
    nin = rng.randint(1, 3)
    inputs = [(f"a{k}", 1) for k in range(nin)]
    n_gates = rng.randint(1, 5)
    gtypes = [rng.choice(_PRIMS_2 + ("NOT",)) for _ in range(n_gates)]

    avail = [f"a{k}" for k in range(nin)]  # 1-bit signals usable as gate inputs
    lines = [f"component {name}({', '.join(n for n, _ in inputs)}) -> (Y) {{"]
    for i, t in enumerate(gtypes):
        lines.append(f"    g{i}: {t};")
    lines.append("    connect {")
    for i, t in enumerate(gtypes):
        lines.append(f"        {rng.choice(avail)} -> g{i}.A;")
        if t in _PRIMS_2:
            lines.append(f"        {rng.choice(avail)} -> g{i}.B;")
        avail.append(f"g{i}.O")  # DAG: only earlier gates feed later ones
    lines.append(f"        {avail[-1]} -> Y;")
    lines.append("    }")
    lines.append("}")
    return CompSpec(name, module, inputs, [("Y", 1)], None, "\n".join(lines) + "\n")


def _gen_leaf_latch(rng: random.Random, name: str, module: str) -> CompSpec:
    """An SR latch that *owns its loop*: two NORs spelled as OR+NOT, with an
    ``init`` block seeding all four nets to a fixed point so it powers up
    stable and holds (tasks/lessons.md: seed the whole loop or it oscillates).
    """
    # Q=0/Qn=1 fixed point: or1=(R|n2)=(0|1)=1 -> n1=Q=0; or2=(S|n1)=(0|0)=0
    # -> n2=Qn=1.  Verified to hold under BaseEval+HighEval.
    text = f"""component {name}(S, R) -> (Q, Qn) {{
    or1: OR;  n1: NOT;  or2: OR;  n2: NOT;
    init {{ or1.O = 1; n1.O = 0; or2.O = 0; n2.O = 1; }}
    connect {{
        R -> or1.A;  n2.O -> or1.B;  or1.O -> n1.A;  n1.O -> Q;
        S -> or2.A;  n1.O -> or2.B;  or2.O -> n2.A;  n2.O -> Qn;
    }}
}}
"""
    return CompSpec(name, module, [("S", 1), ("R", 1)], [("Q", 1), ("Qn", 1)], None, text)


# ---------------------------------------------------------------------------
# Composite components: instantiate children + add own logic.
# ---------------------------------------------------------------------------


def _gen_composite(
    rng: random.Random,
    name: str,
    module: str,
    children: list[CompSpec],
    *,
    is_top: bool,
    use_param: bool,
) -> CompSpec:
    """A component that instantiates ``children`` and wires them, optionally
    parameterized. Drives every instance input and output port exactly once.
    """
    consts: dict[str, int] = {}  # const name -> effective width
    decls: list[str] = []
    conns: list[str] = []
    used: list[str] = []  # child type names instantiated (for import tracking)

    # Optional parameter. It is *bound* (positional/named/default coverage at
    # the instantiation site) and may gate a ``when`` below, but it never sizes
    # a port: the width contract must be independent of the value a parent binds
    # — otherwise a dependent arg (``child<N>``) deep in the hierarchy would
    # change a downstream port width and break valid-by-construction.
    param = None
    pval = None
    if use_param:
        pval = rng.randint(1, 4)
        param = ("N", pval)

    # Input ports: a few literal-width buses.
    n_in = rng.randint(1, 3)
    inputs: list[tuple[str, int]] = [
        (_PORT_LETTERS[k], rng.randint(1, 4)) for k in range(n_in)
    ]

    scope = Scope()
    for nm, w in inputs:
        scope.widths[nm] = w

    # Maybe a constant (per-bit refs + an optional width assertion).
    if rng.random() < 0.6:
        cval = rng.randint(0, 255)
        cw = max(1, cval.bit_length())
        if rng.random() < 0.5:
            # Explicit width >= significant bits (overflow assertion holds).
            declw = rng.randint(cw, cw + 3)
            decls.append(f"K[{declw}] = {cval};")
            consts["K"] = declw
        else:
            decls.append(f"K = {cval};")
            consts["K"] = cw  # effective width = significant bits (>=1)

    # Instantiate children, wiring their inputs from scope and exposing outputs.
    n_inst = rng.randint(1, min(3, len(children) + 1))
    eb = _ExprBuilder(rng, scope, consts)
    for j in range(n_inst):
        child = rng.choice(children)
        inst = f"u{j}"
        arg = _instantiate(rng, child, use_param)
        decls.append(f"{inst}: {child.name}{arg};")
        used.append(child.name)
        for pn, pw in child.inputs:
            src = eb.build(pw)
            conns.append(f"{src} -> {inst}.{pn};")
        for pn, pw in child.outputs:
            scope.widths[f"{inst}.{pn}"] = pw  # now usable as a source

    # Output ports, each driven once by a source of exactly its width.
    n_out = rng.randint(1, 3)
    outputs: list[tuple[str, int]] = []
    for k in range(n_out):
        ow = rng.randint(1, 4)
        oname = f"O{k}"
        outputs.append((oname, ow))
        conns.append(f"{eb.build(ow)} -> {oname};")

    # Optionally wrap a slab of connections in a flatten-time conditional
    # (declaration- or connection-context) using the full operator set. The
    # condition is constant-folded at flatten time; we pick comparisons that
    # are TRUE for the bound parameter/literal so the wiring above is emitted.
    body = _assemble_body(
        rng, name, is_top, param, inputs, outputs, decls, conns, pval
    )
    return CompSpec(name, module, inputs, outputs, param, body, used)


def _instantiate(rng: random.Random, child: CompSpec, parent_has_param: bool) -> str:
    """Render a child's parameter-argument list (positional/named/default).

    The bound value is never read for sizing (ports are literal-width), so any
    value >= 1 is safe; dependent args over the parent's ``N`` (also >= 1) are
    therefore always >= 1 too, which keeps every param-gated ``when`` true.
    """
    if child.param is None:
        return ""
    pname, _pdefault = child.param
    r = rng.random()
    if r < 0.34:
        return ""  # rely on the default
    # A literal, or — when the parent is parameterized — an arithmetic
    # expression over the parent's parameter N (dependent arg). Every form below
    # evaluates to a positive integer (N >= 1), so any param-gated `when` in the
    # child that we built to be true-for-all-positive-N stays true.
    if parent_has_param and rng.random() < 0.5:
        val_txt = rng.choice(["N", "N+1", "N*1", "N*2"])
    else:
        val_txt = str(rng.randint(1, 4))
    if r < 0.67:
        return f"<{val_txt}>"  # positional
    return f"<{pname} = {val_txt}>"  # named


def _assemble_body(rng, name, is_top, param, inputs, outputs, decls, conns, pval) -> str:
    # Port widths are always literals (parameters never size ports).
    port_txt = [f"{nm}[{w}]" if w > 1 else nm for nm, w in inputs]
    out_txt = [f"{nm}[{w}]" if w > 1 else nm for nm, w in outputs]

    head = "top component " if is_top else "component "
    head += name
    if param is not None:
        head += f"<{param[0]} = {param[1]}>"
    head += f"({', '.join(port_txt)}) -> ({', '.join(out_txt)}) {{"

    lines = [head]
    for d in decls:
        lines.append(f"    {d}")
    # Connection block, optionally with a (true) flatten-time conditional that
    # exercises the full RelOp / boolean operator set without changing wiring.
    lines.append("    connect {")
    cond = _true_condition(rng, param, pval) if conns and rng.random() < 0.4 else None
    if cond is not None:
        lines.append(f"        when {{{cond}}} {{")
        for c in conns:
            lines.append(f"            {c}")
        lines.append("        }")
    else:
        for c in conns:
            lines.append(f"        {c}")
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _true_condition(rng: random.Random, param, pval) -> str:
    """A BoolExpr that folds TRUE no matter what value a parent binds.

    Covers every RelOp and both boolean connectives across calls. Crucially the
    clauses are true for *every* value the parameter can ever take (we always
    bind N >= 1, and dependent args N+1 / N*1 / N*2 are also >= 1), not merely
    for this component's default — a child built here may be specialized with a
    different N by a parent's dependent arg, and its guarded body (which drives
    the child's outputs) must still emit, or we'd get a spurious E0503/E0401.
    No clause ever emits a negative literal (the parser rejects ``-`` in a
    NUMBER position, E0201).
    """
    if param is not None:
        # Clauses true for all N >= 1 (the universal lower bound on any bind).
        options = [
            "N >= 1",
            "N > 0",
            "N != 0",
            "N <= N",
            "N == N",
            "N < N + 1",
        ]
    else:
        # Pure-literal tautologies (no parameter in scope).
        lit = rng.randint(1, 8)
        options = [
            f"{lit} == {lit}",
            f"{lit} != {lit + 1}",
            f"{lit} < {lit + 1}",
            f"{lit} <= {lit}",
            f"{lit} > {lit - 1}",  # lit >= 1, so lit-1 >= 0 — never negative
            f"{lit} >= {lit}",
        ]
    a = rng.choice(options)
    if rng.random() < 0.5:
        b = rng.choice(options)
        joiner = rng.choice([" && ", " || "])
        # Every clause is individually true, so both && and || fold true.
        if rng.random() < 0.5:  # parenthesized sub-expression coverage
            return f"({a}){joiner}({b})"
        return f"{a}{joiner}{b}"
    return a


# ---------------------------------------------------------------------------
# Generator-context components: per-bit wiring through a generator loop with
# single / compound / open ranges and nesting, all literal-indexed so every
# generated reference is provably in range (valid by construction).
# ---------------------------------------------------------------------------


def _gen_generator_comp(rng: random.Random, name: str, module: str, *, is_top: bool) -> CompSpec:
    """A combinational component whose connect block is a generator loop.

    Wires ``A[w] -> Y[w]`` bit by bit through a generator, optionally with a
    compound or open range and an inner nested generator, exercising generator
    expansion (phase 3) with literal-safe indices.
    """
    w = rng.randint(2, 6)
    lines = [
        ("top component " if is_top else "component ")
        + f"{name}(A[{w}], B[{w}]) -> (Y[{w}], Z[{w}]) {{",
        "    connect {",
    ]
    # Y: A -> Y bit by bit, via a single / compound / open range.
    kind = rng.choice(["single", "compound", "open"])
    if kind == "single":
        rng_txt = f"[{w}]"
    elif kind == "compound":
        mid = rng.randint(1, w - 1)
        rng_txt = f"[1:{mid}, {mid + 1}:{w}]"  # disjoint, covers 1..w verbatim
    else:  # open: governing signal A (and Y) fix the upper bound at w
        rng_txt = "[1:]"
    lines.append(f"        >i{rng_txt} {{ A[{{i}}] -> Y[{{i}}]; }}")
    # Z: a generator nested to depth 1, 2, or 3 (the obligation's nesting-to-3),
    # all literal-indexed so every generated reference is provably in range. The
    # extra dimensions are single-iteration loops so the per-bit pairing is
    # still exactly B[k] -> Z[k] (valid by construction) — they exercise nested
    # generator expansion without changing the wiring.
    depth = rng.randint(1, 3)
    if depth == 1:
        lines.append(f"        >i[{w}] {{ B[{{i}}] -> Z[{{i}}]; }}")
    elif depth == 2:
        lines.append(f"        >i[{w}] {{ >j[1] {{ B[{{i}}] -> Z[{{i}}]; }} }}")
    else:
        lines.append(
            f"        >i[{w}] {{ >j[1] {{ >k[1] {{ B[{{i}}] -> Z[{{i}}]; }} }} }}"
        )
    lines.append("    }")
    lines.append("}")
    return CompSpec(
        name,
        module,
        [("A", w), ("B", w)],
        [("Y", w), ("Z", w)],
        None,
        "\n".join(lines) + "\n",
    )


# ---------------------------------------------------------------------------
# Program assembly.
# ---------------------------------------------------------------------------


def gen_program(rng: random.Random) -> tuple[dict[str, str], str]:
    """Build one valid-by-construction high-level program.

    Returns ``(modules, main_module_name)`` where ``modules`` maps a module
    name to its source text. The hierarchy is 2-4 component levels; non-main
    modules are pulled in via ``use`` imports (optional — sometimes everything
    lives in one module).
    """
    single_module = rng.random() < 0.4
    main_mod = "main"

    # Build a pool of leaf children first.
    leaves: list[CompSpec] = []
    n_leaves = rng.randint(1, 3)
    for k in range(n_leaves):
        mod = main_mod if single_module else f"leaf{k}"
        if rng.random() < 0.3:
            leaves.append(_gen_leaf_latch(rng, f"Leaf{k}", mod))
        else:
            leaves.append(_gen_leaf_comb(rng, f"Leaf{k}", mod))

    # A small chain of composite levels above the leaves (1-3 levels).
    levels = rng.randint(1, 3)
    below = leaves
    mids: list[CompSpec] = []
    for level in range(levels):
        mod = main_mod if single_module else f"mid{level}"
        comp = _gen_composite(
            rng,
            f"Mid{level}",
            mod,
            below,
            is_top=False,
            use_param=rng.random() < 0.5,
        )
        mids.append(comp)
        below = [comp]  # next level builds on this one (deeper hierarchy)

    # The top: either a composite over the highest mid, or a generator comp.
    if rng.random() < 0.3:
        top = _gen_generator_comp(rng, "Top", main_mod, is_top=True)
    else:
        top = _gen_composite(
            rng, "Top", main_mod, below, is_top=True, use_param=rng.random() < 0.5
        )

    all_comps = leaves + mids + [top]

    # Group components by module; only modules actually referenced are emitted.
    by_module: dict[str, list[CompSpec]] = {}
    for c in all_comps:
        by_module.setdefault(c.module, []).append(c)

    # Build each module's text, with imports for the components it references.
    # Imports are taken from each spec's recorded ``children`` (the exact type
    # names it instantiates) — never re-derived by scanning text, so a child
    # instantiated with a parameter arg (``u0: Mid0<N = 4>``) is never missed.
    module_of = {c.name: c.module for c in all_comps}
    modules: dict[str, str] = {}
    for mod, comps in by_module.items():
        seen: set[tuple[str, str]] = set()
        import_lines: list[str] = []
        for cspec in comps:
            for tgt in cspec.children:
                tgt_mod = module_of[tgt]
                if tgt_mod != mod and (tgt_mod, tgt) not in seen:
                    seen.add((tgt_mod, tgt))
                    import_lines.append(f"use {tgt_mod}::{{{tgt}}};")
        body = "\n".join(import_lines)
        if body:
            body += "\n\n"
        body += "\n".join(c.text for c in comps)
        modules[mod] = body

    return modules, main_mod
