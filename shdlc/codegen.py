"""C code generation from a validated :class:`~shdlc.model.Circuit`.

``generate_c`` is pure and byte-deterministic: the same Circuit always yields
the same C source, with no timestamps, paths, or versions embedded.
"""

from __future__ import annotations

from .model import Circuit


def generate_c(circuit: Circuit) -> str:
    """Render ``circuit`` as a complete, self-contained C translation unit.

    The generated file implements the unit-delay two-buffer simulation model
    (shdl.md §11) and exports exactly the release ABI ``reset``/``poke``/
    ``peek``/``step`` (shdlc_goals.md §2); everything else is static.
    """
    raise NotImplementedError
