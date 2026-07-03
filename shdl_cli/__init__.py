"""shdl_cli: the ``shdl`` command — SHDL project manager and build driver.

``shdl`` owns the project workflow the toolchain's lower layers deliberately
do not: ``shdl.toml`` (the project manifest), ``shdl.lock`` (the pinned
resolution), ``shdl_modules/`` (vendored registry packages), and the unified
``build``/``test``/``run`` driver over :class:`SHDL.Circuit`. The package
index it resolves against is specified by CCircus's ``INDEX_FORMAT.md``.

Stdlib-only by design, like the rest of the toolchain.
"""
