"""
SHDL Abstract Syntax Tree

Defines all AST node types for representing SHDL programs.
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from abc import ABC

if TYPE_CHECKING:
    from ..source_map import SourceSpan


# =============================================================================
# Base Classes
# =============================================================================

@dataclass
class Node(ABC):
    """
    Base class for all AST nodes.
    
    Includes source location tracking for error reporting.
    """
    line: int = 0
    column: int = 0
    end_line: int = 0
    end_column: int = 0
    file_path: str = "<string>"
    
    @property
    def span(self) -> "SourceSpan":
        """Get the source span for this node."""
        from ..source_map import SourceSpan
        return SourceSpan(
            file_path=self.file_path,
            start_line=self.line,
            start_col=self.column,
            end_line=self.end_line if self.end_line > 0 else self.line,
            end_col=self.end_column if self.end_column > 0 else self.column
        )
    
    def with_span(self, span: "SourceSpan") -> "Node":
        """Set the span from a SourceSpan object."""
        self.line = span.start_line
        self.column = span.start_col
        self.end_line = span.end_line
        self.end_column = span.end_col
        self.file_path = span.file_path
        return self
    
    def with_location(
        self,
        line: int,
        column: int,
        end_line: int = None,
        end_column: int = None,
        file_path: str = None
    ) -> "Node":
        """Set location information."""
        self.line = line
        self.column = column
        self.end_line = end_line if end_line is not None else line
        self.end_column = end_column if end_column is not None else column
        if file_path is not None:
            self.file_path = file_path
        return self


@dataclass
class Expression(Node):
    """Base class for expression nodes."""
    pass


# =============================================================================
# Signal References
# =============================================================================

@dataclass
class Signal(Node):
    """
    A signal reference (port or instance port).
    
    Examples:
        - A                 (simple port)
        - A[1]              (indexed port)
        - gate1.O           (instance port)
        - gate1.Out[3]      (indexed instance port)
        - A[:4]             (slice - start omitted)
        - A[5:]             (slice - end omitted)
        - A[2:7]            (slice - both specified)
    """
    name: str = ""
    instance: Optional[str] = None  # If accessing an instance's port
    index: Optional["IndexExpr"] = None  # Single index or slice


@dataclass
class IndexExpr(Node):
    """
    An index expression - either a single index or a slice.
    
    For single index: start is the index, end is None, is_slice is False
    For slice: start and end define the range, is_slice is True
    """
    start: Optional["ArithmeticExpr"] = None  # None means "from beginning" in slice
    end: Optional["ArithmeticExpr"] = None    # None means "to end" in slice
    is_slice: bool = False


@dataclass
class ArithmeticExpr(Node):
    """
    An arithmetic expression used in generator variable substitutions.
    
    Can be:
        - A literal number
        - A variable reference (e.g., {i})
        - A binary operation (e.g., {i+1}, {i*2})
    """
    pass


@dataclass
class NumberLiteral(ArithmeticExpr):
    """A numeric literal."""
    value: int = 0


@dataclass 
class VariableRef(ArithmeticExpr):
    """A reference to a generator variable."""
    name: str = ""


@dataclass
class BinaryOp(ArithmeticExpr):
    """A binary arithmetic operation."""
    left: ArithmeticExpr = field(default_factory=lambda: NumberLiteral(value=0))
    operator: str = "+"  # +, -, *, /
    right: ArithmeticExpr = field(default_factory=lambda: NumberLiteral(value=0))


@dataclass
class TemplateString(Node):
    """
    A template string that can include variable substitutions.
    
    Used for instance names and signal names inside generators.
    
    Examples:
        - gate{i}           -> parts = ["gate", VariableRef("i")]
        - not{i+1}          -> parts = ["not", BinaryOp(...)]
        - stage{i}_gate{j}  -> parts = ["stage", VariableRef("i"), "_gate", VariableRef("j")]
    """
    parts: list = field(default_factory=list)  # list of str | ArithmeticExpr
    
    def is_simple(self) -> bool:
        """Check if this is just a plain string with no substitutions."""
        return len(self.parts) == 1 and isinstance(self.parts[0], str)
    
    def simple_value(self) -> str:
        """Get the simple string value if is_simple() is True."""
        if self.is_simple():
            return self.parts[0]
        raise ValueError("TemplateString is not simple")


# =============================================================================
# Declarations
# =============================================================================

@dataclass
class Port(Node):
    """
    A port declaration.
    
    Examples:
        - A           (single-bit)
        - Data[8]     (8-bit vector)
    """
    name: str = ""
    width: Optional[int] = None  # None means single-bit


@dataclass
class Instance(Node):
    """
    An instance declaration.
    
    Examples:
        - gate1: AND;
        - fa1: FullAdder;
        - gate{i}: AND;  (in generator context, name contains template)
    """
    name: str = ""  # May contain {expr} templates for generators
    component_type: str = ""


@dataclass
class Constant(Node):
    """
    A constant declaration.
    
    Examples:
        - FIVE = 5;
        - MASK = 0xFF;
        - PATTERN = 0b1010;
        - DATA[8] = 100;      # Explicit 8-bit width
    """
    name: str = ""
    value: int = 0
    width: Optional[int] = None  # Explicit bit width, None means infer from value


@dataclass
class Connection(Node):
    """
    A connection between signals.
    
    Example:
        - A -> gate1.A;
        - gate1.O -> Out[1];
    """
    source: Signal = field(default_factory=lambda: Signal(name=""))
    destination: Signal = field(default_factory=lambda: Signal(name=""))


# =============================================================================
# Generators
# =============================================================================

@dataclass
class RangeSpec(Node):
    """
    A range specification in a generator.
    
    Examples:
        - [8]           -> 1 to 8
        - [4:10]        -> 4 to 10
        - [5:]          -> 5 to end (context-dependent)
        - [1:4, 8, 12:] -> multiple ranges
    """
    pass


@dataclass
class SimpleRange(RangeSpec):
    """A simple range: [N] means 1 to N."""
    end: int = 0


@dataclass
class StartEndRange(RangeSpec):
    """A start:end range: [A:B] or [A:] or [:B]."""
    start: Optional[int] = None
    end: Optional[int] = None  # None means open-ended


@dataclass
class MultiRange(RangeSpec):
    """Multiple comma-separated ranges."""
    ranges: list[RangeSpec] = field(default_factory=list)


@dataclass
class Generator(Node):
    """
    A generator construct.
    
    Example:
        >i[8]{
            gate{i}: AND;
        }
    """
    variable: str = ""
    range_spec: RangeSpec = field(default_factory=lambda: SimpleRange(end=1))
    body: list[Node] = field(default_factory=list)  # Can contain instances, connections, or nested generators


# =============================================================================
# Imports
# =============================================================================

@dataclass
class Import(Node):
    """
    An import statement.
    
    Example:
        use fullAdder::{FullAdder, HalfAdder};
    """
    module: str = ""
    components: list[str] = field(default_factory=list)


# =============================================================================
# Top-Level
# =============================================================================

@dataclass
class ConnectBlock(Node):
    """The connect block containing all connections."""
    statements: list[Node] = field(default_factory=list)  # Connections and generators


@dataclass
class Component(Node):
    """
    A component definition.
    
    Example:
        component FullAdder(A, B, Cin) -> (Sum, Cout) {
            ...
        }
    """
    name: str = ""
    inputs: list[Port] = field(default_factory=list)
    outputs: list[Port] = field(default_factory=list)
    instances: list[Node] = field(default_factory=list)  # Instances, constants, generators
    connect_block: Optional[ConnectBlock] = None


@dataclass
class Module(Node):
    """
    A complete SHDL module (file).
    
    Contains imports and component definitions.
    """
    imports: list[Import] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
