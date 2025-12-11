"""
Base SHDL AST

Simplified AST for Base SHDL which only contains:
- Primitive gate instances (AND, OR, NOT, XOR, __VCC__, __GND__)
- Direct signal connections
- No generators, constants, or hierarchy
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class PrimitiveType(Enum):
    """Primitive gate types."""
    AND = auto()
    OR = auto()
    NOT = auto()
    XOR = auto()
    VCC = auto()  # __VCC__
    GND = auto()  # __GND__
    
    @classmethod
    def from_string(cls, s: str) -> "PrimitiveType":
        """Convert a string to a PrimitiveType."""
        mapping = {
            "AND": cls.AND,
            "OR": cls.OR,
            "NOT": cls.NOT,
            "XOR": cls.XOR,
            "__VCC__": cls.VCC,
            "__GND__": cls.GND,
        }
        if s not in mapping:
            raise ValueError(f"Unknown primitive type: {s}")
        return mapping[s]
    
    def to_string(self) -> str:
        """Convert back to string representation."""
        mapping = {
            self.AND: "AND",
            self.OR: "OR",
            self.NOT: "NOT",
            self.XOR: "XOR",
            self.VCC: "__VCC__",
            self.GND: "__GND__",
        }
        return mapping[self]
    
    @property
    def input_ports(self) -> list[str]:
        """Get the input port names for this primitive."""
        if self == PrimitiveType.NOT:
            return ["A"]
        elif self in (PrimitiveType.VCC, PrimitiveType.GND):
            return []
        else:
            return ["A", "B"]
    
    @property
    def output_ports(self) -> list[str]:
        """Get the output port names for this primitive."""
        return ["O"]
    
    @property
    def c_operator(self) -> str:
        """Get the C bitwise operator for this primitive."""
        mapping = {
            self.AND: "&",
            self.OR: "|",
            self.NOT: "~",
            self.XOR: "^",
        }
        return mapping.get(self, "")


@dataclass
class Port:
    """
    A port declaration in a component header.
    
    Examples:
        - A           (single-bit, width=None)
        - Data[8]     (8-bit vector, width=8)
    """
    name: str
    width: Optional[int] = None  # None means single-bit
    line: int = 0
    column: int = 0
    
    @property
    def is_vector(self) -> bool:
        """Check if this is a multi-bit port."""
        return self.width is not None
    
    @property
    def bit_count(self) -> int:
        """Get the number of bits (1 for single-bit)."""
        return self.width if self.width else 1


@dataclass
class Instance:
    """
    A primitive gate instance declaration.
    
    Examples:
        - x1: XOR;
        - fa1_a2: AND;
        - vcc_bit: __VCC__;
    """
    name: str
    primitive: PrimitiveType
    line: int = 0
    column: int = 0


@dataclass
class SignalRef:
    """
    A reference to a signal.
    
    Can be:
        - Component port: A, B, Cin
        - Indexed port: A[1], Sum[8]
        - Instance port: x1.A, x1.O
    
    Note: Instance ports are never indexed in Base SHDL.
    """
    name: str
    instance: Optional[str] = None  # If accessing instance.port
    index: Optional[int] = None     # 1-based bit index for component ports
    line: int = 0
    column: int = 0
    
    @property
    def is_port(self) -> bool:
        """Check if this is a component port reference."""
        return self.instance is None
    
    @property
    def is_instance_port(self) -> bool:
        """Check if this is an instance port reference."""
        return self.instance is not None
    
    def __str__(self) -> str:
        """Format as SHDL signal reference."""
        if self.instance:
            return f"{self.instance}.{self.name}"
        elif self.index is not None:
            return f"{self.name}[{self.index}]"
        else:
            return self.name


@dataclass
class Connection:
    """
    A connection between two signals.
    
    Example:
        A -> x1.A;
        x1.O -> Sum[1];
    """
    source: SignalRef
    destination: SignalRef
    line: int = 0
    column: int = 0


@dataclass
class Component:
    """
    A complete Base SHDL component definition.
    
    Example:
        component Add100(A[8]) -> (Sum[8], Cout) {
            fa1_x1: XOR;
            fa1_a1: AND;
            ...
            
            connect {
                A[1] -> fa1_x1.A;
                ...
            }
        }
    """
    name: str
    inputs: list[Port] = field(default_factory=list)
    outputs: list[Port] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    line: int = 0
    column: int = 0
    
    @property
    def all_ports(self) -> list[Port]:
        """Get all ports (inputs + outputs)."""
        return self.inputs + self.outputs
    
    def get_port(self, name: str) -> Optional[Port]:
        """Get a port by name."""
        for port in self.all_ports:
            if port.name == name:
                return port
        return None
    
    def get_instance(self, name: str) -> Optional[Instance]:
        """Get an instance by name."""
        for inst in self.instances:
            if inst.name == name:
                return inst
        return None
    
    def instances_by_type(self, ptype: PrimitiveType) -> list[Instance]:
        """Get all instances of a given primitive type."""
        return [inst for inst in self.instances if inst.primitive == ptype]


@dataclass
class Module:
    """
    A Base SHDL module (file) containing one or more components.
    """
    components: list[Component] = field(default_factory=list)
    
    def get_component(self, name: str) -> Optional[Component]:
        """Get a component by name."""
        for comp in self.components:
            if comp.name == name:
                return comp
        return None
