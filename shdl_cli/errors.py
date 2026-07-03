"""The one exception type the CLI surfaces to users."""

from __future__ import annotations


class CliError(Exception):
    """A diagnosed failure: ``main()`` prints ``shdl: error: <this>`` and exits 1."""
