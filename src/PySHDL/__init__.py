"""shdl library."""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

from .circuit import Circuit
from .shdlc import Component, Instance, Port, SHDLParser, generate_c_code

__all__ = [
    "Circuit",
    "Component",
    "Instance",
    "Port",
    "SHDLParser",
    "generate_c_code",
    "__version__",
]
try:
    __version__ = version("shdl")
except PackageNotFoundError:
    __version__ = "0.0.0"