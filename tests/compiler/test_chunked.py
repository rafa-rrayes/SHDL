"""Differential + warning-freeness test for the chunked tick() path.

A >1024-gate netlist is string-built (no .shdl fixture) so the build crosses
the ``_TICK_CHUNK`` boundary: the STRICT_CFLAGS build (-Werror) proves the
SHDLC_NOINLINE/restrict chunk emission compiles warning-free, and the
lockstep run proves chunked tick() semantics match BaseEval exactly.
"""

from __future__ import annotations

import random

from shdlc.codegen import _TICK_CHUNK
from shdlc.compile import compile_text

from .harness import random_drive

#: Just past the chunk threshold (2 chunks) so the -O2 build stays fast.
N_GATES = 1100


def _chain_text(n: int) -> str:
    """Base SHDL NOT/XOR chain: g0 = NOT(a); then alternating
    gi = XOR(g(i-1), b) / gi = NOT(g(i-1)); y = the last gate."""
    decls = [f"    g{i}: {'XOR' if i % 2 else 'NOT'};" for i in range(n)]
    conns = ["        a -> g0.A;"]
    for i in range(1, n):
        conns.append(f"        g{i - 1}.O -> g{i}.A;")
        if i % 2:
            conns.append(f"        b -> g{i}.B;")
    conns.append(f"        g{n - 1}.O -> y;")
    return "\n".join(
        ["component ChunkChain(a, b) -> (y) {", *decls, "    connect {", *conns, "    }", "}"]
    ) + "\n"


def test_chunked_build_is_warning_free_and_matches_oracle(builds):
    text = _chain_text(N_GATES)
    circuit, c_src = compile_text(text)
    assert len(circuit.gates) == N_GATES > _TICK_CHUNK
    assert "tick_chunk_1(" in c_src  # the chunked emission is what gets built
    # builds.* compiles with STRICT_CFLAGS (-Wall -Wextra -Werror -pedantic).
    dual = builds.dual_from_text("chunked-chain", text, seed=N_GATES)
    dual.compare_all()  # power-on state must already agree
    random_drive(dual, random.Random(N_GATES), 50)


def _input_only_text(n: int) -> str:
    """N gates that each read ONLY input wires (no gate-output reads), so the
    chunk functions take the ``n``-only signature. Each gi = XOR(a, b) (i even)
    or NOT(a) (i odd); y is the last gate, depth 1 -- a pure combinational fan."""
    decls = [f"    g{i}: {'NOT' if i % 2 else 'XOR'};" for i in range(n)]
    conns = []
    for i in range(n):
        conns.append(f"        a -> g{i}.A;")
        if i % 2 == 0:
            conns.append(f"        b -> g{i}.B;")
    conns.append(f"        g{n - 1}.O -> y;")
    return (
        "\n".join(
            ["component InputFan(a, b) -> (y) {", *decls, "    connect {", *conns, "    }", "}"]
        )
        + "\n"
    )


def test_n_only_chunk_signature_builds_and_matches_oracle(builds):
    # CCT-17: a >1024-gate circuit whose chunks read no gate outputs emits the
    # `n`-only `tick_chunk_k(uint8_t *restrict n)` signature. Build it under
    # STRICT_CFLAGS (-Werror would reject an unused `c` parameter) and lockstep
    # it against BaseEval -- the first test that ever BUILDS this variant.
    text = _input_only_text(N_GATES)
    circuit, c_src = compile_text(text)
    assert len(circuit.gates) == N_GATES > _TICK_CHUNK
    # Proof we are exercising the n-only path, not the (c, n) path.
    assert "static void tick_chunk_0(uint8_t *restrict n)" in c_src
    assert "restrict c" not in c_src
    assert "tick_chunk_1(nxt);" in c_src
    dual = builds.dual_from_text("chunked-input-fan", text, seed=N_GATES + 1)
    dual.compare_all()  # power-on state agrees
    random_drive(dual, random.Random(N_GATES + 1), 50)
