"""SHDL conformance suite: the versioned ground-truth corpus for the toolchain.

This package holds two things:

- the *corpus* — ``MANIFEST.json`` plus ``cases/<name>/`` directories of
  plain-text/JSON golden artifacts (see ``conformance.md``); and
- the *runner* — ``conformance.runner``, the reference checker invoked as
  ``shdl-conformance``.

The corpus is the product. It is designed to outlive every implementation
that consumes it: all artifacts are readable without Python, and every
golden value traces back to the BaseEval reference oracle or to the specs
(never to the C implementation under test).
"""
