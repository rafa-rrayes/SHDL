"""
SHDL Parser

Parses a stream of tokens into an Abstract Syntax Tree.
"""

from dataclasses import dataclass, field
from typing import Optional, List

from .tokens import Token, TokenType
from .lexer import Lexer
from .ast import (
    Module, Component, Port, Instance, Constant, Connection,
    Signal, IndexExpr, ArithmeticExpr, NumberLiteral, VariableRef, BinaryOp,
    Generator, RangeSpec, SimpleRange, StartEndRange, MultiRange,
    Import, ConnectBlock, Node
)
from ..errors import ParseError as ParseErrorBase, ErrorCode, Suggestion
from ..source_map import SourceSpan, SourceFile


class ParseError(ParseErrorBase):
    """Raised when the parser encounters invalid syntax."""
    
    def __init__(
        self,
        message: str,
        token: Token,
        code: ErrorCode = ErrorCode.E0201,
        suggestions: List[Suggestion] = None,
        notes: List[str] = None
    ):
        self.token = token
        super().__init__(
            message,
            line=token.line,
            column=token.column,
            file_path=token.file_path,
            code=code,
            span=token.span,
            suggestions=suggestions,
            notes=notes
        )


@dataclass
class Parser:
    """Parses SHDL tokens into an AST."""
    
    tokens: list[Token]
    file_path: str = "<string>"
    
    def __post_init__(self) -> None:
        self._pos: int = 0
    
    @classmethod
    def from_source(cls, source: str, file_path: str = "<string>") -> "Parser":
        """Create a parser from source code."""
        # Register source for error reporting
        SourceFile.register(file_path, source)
        lexer = Lexer(source, file_path=file_path)
        return cls(lexer.tokenize(), file_path=file_path)
    
    @property
    def _current(self) -> Token:
        """Get the current token."""
        if self._pos >= len(self.tokens):
            return self.tokens[-1]  # Return EOF
        return self.tokens[self._pos]
    
    @property
    def _peek(self) -> Token:
        """Peek at the next token."""
        if self._pos + 1 >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self._pos + 1]
    
    def _advance(self) -> Token:
        """Advance to the next token and return the current one."""
        token = self._current
        self._pos += 1
        return token
    
    def _check(self, *types: TokenType) -> bool:
        """Check if current token is one of the given types."""
        return self._current.type in types
    
    def _match(self, *types: TokenType) -> Optional[Token]:
        """If current token matches, advance and return it. Otherwise return None."""
        if self._check(*types):
            return self._advance()
        return None
    
    def _expect(self, token_type: TokenType, message: str = "", code: ErrorCode = None) -> Token:
        """Expect a specific token type, raise error if not found."""
        if self._current.type != token_type:
            msg = message or f"Expected {token_type.name}, got {self._current.type.name}"
            raise ParseError(msg, self._current, code=code or ErrorCode.E0201)
        return self._advance()
    
    def _set_node_location(self, node: Node, start: Token, end: Token = None) -> Node:
        """Set location information on a node from tokens."""
        if end is None:
            end = self.tokens[self._pos - 1] if self._pos > 0 else start
        
        node.line = start.line
        node.column = start.column
        node.end_line = end.end_line
        node.end_column = end.end_column
        node.file_path = start.file_path
        return node
    
    def _make_node(self, node: Node) -> Node:
        """Set line/column info on a node (legacy method)."""
        node.line = self._current.line
        node.column = self._current.column
        node.file_path = self.file_path
        return node
    
    # =========================================================================
    # Top-Level Parsing
    # =========================================================================
    
    def parse(self) -> Module:
        """Parse a complete SHDL module."""
        imports: list[Import] = []
        components: list[Component] = []
        
        while not self._check(TokenType.EOF):
            if self._check(TokenType.USE):
                imports.append(self._parse_import())
            elif self._check(TokenType.COMPONENT):
                components.append(self._parse_component())
            else:
                raise ParseError(
                    f"Expected 'use' or 'component', got {self._current.type.name}",
                    self._current
                )
        
        return Module(imports=imports, components=components)
    
    def _parse_import(self) -> Import:
        """Parse an import statement: use module::{Component1, Component2};"""
        start = self._current
        self._expect(TokenType.USE)
        
        module_name = self._expect(TokenType.IDENTIFIER, "Expected module name").value
        self._expect(TokenType.DOUBLE_COLON, "Expected '::'")
        self._expect(TokenType.LBRACE, "Expected '{'")
        
        components: list[str] = []
        components.append(self._expect(TokenType.IDENTIFIER, "Expected component name").value)
        
        while self._match(TokenType.COMMA):
            components.append(self._expect(TokenType.IDENTIFIER, "Expected component name").value)
        
        self._expect(TokenType.RBRACE, "Expected '}'")
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        
        return Import(module=module_name, components=components, line=start.line, column=start.column)
    
    def _parse_component(self) -> Component:
        """Parse a component definition."""
        start = self._current
        self._expect(TokenType.COMPONENT)
        
        name = self._expect(TokenType.IDENTIFIER, "Expected component name").value
        
        # Input ports
        self._expect(TokenType.LPAREN, "Expected '('")
        inputs = self._parse_port_list()
        self._expect(TokenType.RPAREN, "Expected ')'")
        
        # Arrow
        self._expect(TokenType.ARROW, "Expected '->'")
        
        # Output ports
        self._expect(TokenType.LPAREN, "Expected '('")
        outputs = self._parse_port_list()
        self._expect(TokenType.RPAREN, "Expected ')'")
        
        # Component body
        self._expect(TokenType.LBRACE, "Expected '{'")
        
        instances: list[Node] = []
        connect_block: Optional[ConnectBlock] = None
        
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.CONNECT):
                connect_block = self._parse_connect_block()
            elif self._check(TokenType.GREATER):
                instances.append(self._parse_generator(in_connect=False))
            elif self._check(TokenType.IDENTIFIER):
                # Could be instance or constant
                # Look ahead to determine:
                # - IDENTIFIER COLON -> instance declaration
                # - IDENTIFIER EQUALS -> constant without width
                # - IDENTIFIER LBRACKET -> constant with width annotation
                if self._peek.type == TokenType.COLON:
                    instances.append(self._parse_instance())
                elif self._peek.type == TokenType.EQUALS or self._peek.type == TokenType.LBRACKET:
                    instances.append(self._parse_constant())
                else:
                    raise ParseError(
                        f"Expected ':', '=' or '[' after identifier",
                        self._peek
                    )
            else:
                raise ParseError(
                    f"Unexpected token in component body: {self._current.type.name}",
                    self._current
                )
        
        self._expect(TokenType.RBRACE, "Expected '}'")
        
        return Component(
            name=name,
            inputs=inputs,
            outputs=outputs,
            instances=instances,
            connect_block=connect_block,
            line=start.line,
            column=start.column
        )
    
    def _parse_port_list(self) -> list[Port]:
        """Parse a comma-separated list of ports."""
        ports: list[Port] = []
        
        if self._check(TokenType.RPAREN):
            return ports
        
        ports.append(self._parse_port())
        
        while self._match(TokenType.COMMA):
            ports.append(self._parse_port())
        
        return ports
    
    def _parse_port(self) -> Port:
        """Parse a single port declaration: Name or Name[width]"""
        start = self._current
        name = self._expect(TokenType.IDENTIFIER, "Expected port name").value
        width: Optional[int] = None
        
        if self._match(TokenType.LBRACKET):
            width = self._expect(TokenType.NUMBER, "Expected port width").value
            self._expect(TokenType.RBRACKET, "Expected ']'")
        
        return Port(name=name, width=width, line=start.line, column=start.column)
    
    def _parse_instance(self) -> Instance:
        """Parse an instance declaration: name: Type;"""
        start = self._current
        name = self._expect(TokenType.IDENTIFIER, "Expected instance name").value
        self._expect(TokenType.COLON, "Expected ':'")
        component_type = self._expect(TokenType.IDENTIFIER, "Expected component type").value
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        
        return Instance(name=name, component_type=component_type, line=start.line, column=start.column)
    
    def _parse_generator_instance(self) -> Instance:
        """Parse an instance declaration inside a generator: name{i}: Type;"""
        start = self._current
        # Use the same template name parsing as signals
        name = self._parse_template_name()
        self._expect(TokenType.COLON, "Expected ':'")
        component_type = self._expect(TokenType.IDENTIFIER, "Expected component type").value
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        
        return Instance(
            name=name,
            component_type=component_type,
            line=start.line,
            column=start.column
        )
    
    def _parse_constant(self) -> Constant:
        """Parse a constant declaration: NAME = value; or NAME[width] = value;"""
        start = self._current
        name = self._expect(TokenType.IDENTIFIER, "Expected constant name").value
        
        # Check for optional width annotation
        width: Optional[int] = None
        if self._match(TokenType.LBRACKET):
            width = self._expect(TokenType.NUMBER, "Expected bit width").value
            self._expect(TokenType.RBRACKET, "Expected ']'")
        
        self._expect(TokenType.EQUALS, "Expected '='")
        value = self._expect(TokenType.NUMBER, "Expected numeric value").value
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        
        return Constant(name=name, value=value, width=width, line=start.line, column=start.column)
    
    def _parse_connect_block(self) -> ConnectBlock:
        """Parse a connect block."""
        start = self._current
        self._expect(TokenType.CONNECT)
        self._expect(TokenType.LBRACE, "Expected '{'")
        
        statements: list[Node] = []
        
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.GREATER):
                statements.append(self._parse_generator(in_connect=True))
            else:
                statements.append(self._parse_connection())
        
        self._expect(TokenType.RBRACE, "Expected '}'")
        
        return ConnectBlock(statements=statements, line=start.line, column=start.column)
    
    def _parse_connection(self) -> Connection:
        """Parse a connection: source -> destination;"""
        start = self._current
        source = self._parse_signal()
        self._expect(TokenType.ARROW, "Expected '->'")
        destination = self._parse_signal()
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        
        return Connection(source=source, destination=destination, line=start.line, column=start.column)
    
    def _parse_template_name(self) -> str:
        """
        Parse a name that may contain {expr} template parts.
        
        Returns the raw string with {expr} preserved for later eval.
        Examples: "gate", "gate{i}", "cell{i+1}_{j}"
        """
        name = self._expect(TokenType.IDENTIFIER, "Expected identifier").value
        
        # Collect any {expr} parts
        while self._check(TokenType.LBRACE):
            self._advance()  # consume {
            # Collect tokens until matching }
            expr_parts = []
            while not self._check(TokenType.RBRACE, TokenType.EOF):
                token = self._advance()
                expr_parts.append(str(token.value))
            self._expect(TokenType.RBRACE, "Expected '}'")
            name += "{" + "".join(expr_parts) + "}"
            
            # Check for trailing identifier part (like _suffix)
            if self._check(TokenType.IDENTIFIER):
                name += self._advance().value
        
        return name
    
    def _parse_signal(self) -> Signal:
        """
        Parse a signal reference.
        
        Possibilities:
            - Name
            - Name[index]
            - Name[start:end]
            - instance.Port
            - instance.Port[index]
            - Name{i} (template)
            - instance{i}.Port
        """
        start = self._current
        first_name = self._parse_template_name()
        
        instance: Optional[str] = None
        port_name: str = first_name
        
        # Check for instance.port
        if self._match(TokenType.DOT):
            instance = first_name
            port_name = self._parse_template_name()
        
        # Check for index
        index: Optional[IndexExpr] = None
        if self._match(TokenType.LBRACKET):
            index = self._parse_index_expr()
            self._expect(TokenType.RBRACKET, "Expected ']'")
        
        return Signal(name=port_name, instance=instance, index=index, line=start.line, column=start.column)
    
    def _parse_index_expr(self) -> IndexExpr:
        """
        Parse an index expression inside brackets.
        
        Possibilities:
            - [5]           single index
            - [{i}]         variable index
            - [{i+1}]       arithmetic index
            - [:4]          slice from start
            - [5:]          slice to end
            - [2:7]         slice range
        """
        start = self._current
        
        # Check for leading colon (slice from start)
        if self._match(TokenType.COLON):
            # [:end]
            end = self._parse_arithmetic_expr()
            return IndexExpr(start=None, end=end, is_slice=True, line=start.line, column=start.column)
        
        # Parse first expression
        first = self._parse_arithmetic_expr()
        
        # Check for colon (slice)
        if self._match(TokenType.COLON):
            # Could be [start:] or [start:end]
            if self._check(TokenType.RBRACKET):
                # [start:]
                return IndexExpr(start=first, end=None, is_slice=True, line=start.line, column=start.column)
            else:
                # [start:end]
                end = self._parse_arithmetic_expr()
                return IndexExpr(start=first, end=end, is_slice=True, line=start.line, column=start.column)
        
        # Single index
        return IndexExpr(start=first, end=None, is_slice=False, line=start.line, column=start.column)
    
    def _parse_arithmetic_expr(self) -> ArithmeticExpr:
        """
        Parse an arithmetic expression.
        
        Examples: 5, {i}, {i+1}, {i*2-1}
        """
        return self._parse_additive_expr()
    
    def _parse_additive_expr(self) -> ArithmeticExpr:
        """Parse addition/subtraction: term (('+' | '-') term)*"""
        left = self._parse_multiplicative_expr()
        
        while self._check(TokenType.PLUS, TokenType.MINUS):
            op = self._advance().value
            right = self._parse_multiplicative_expr()
            left = BinaryOp(left=left, operator=op, right=right, line=left.line, column=left.column)
        
        return left
    
    def _parse_multiplicative_expr(self) -> ArithmeticExpr:
        """Parse multiplication/division: primary (('*' | '/') primary)*"""
        left = self._parse_primary_expr()
        
        while self._check(TokenType.STAR, TokenType.SLASH):
            op = self._advance().value
            right = self._parse_primary_expr()
            left = BinaryOp(left=left, operator=op, right=right, line=left.line, column=left.column)
        
        return left
    
    def _parse_primary_expr(self) -> ArithmeticExpr:
        """Parse primary expression: number, variable, or {expression}."""
        start = self._current
        
        if self._match(TokenType.NUMBER):
            return NumberLiteral(value=start.value, line=start.line, column=start.column)
        
        if self._match(TokenType.IDENTIFIER):
            return VariableRef(name=start.value, line=start.line, column=start.column)
        
        if self._match(TokenType.LBRACE):
            # {expression} - parse expression and expect closing brace
            expr = self._parse_additive_expr()
            self._expect(TokenType.RBRACE, "Expected '}'")
            return expr
        
        raise ParseError("Expected number, variable, or {expression}", self._current)
    
    def _parse_generator(self, in_connect: bool) -> Generator:
        """
        Parse a generator construct.
        
        Example:
            >i[8]{
                gate{i}: AND;
            }
        """
        start = self._current
        self._expect(TokenType.GREATER, "Expected '>'")
        
        variable = self._expect(TokenType.IDENTIFIER, "Expected generator variable").value
        
        self._expect(TokenType.LBRACKET, "Expected '['")
        range_spec = self._parse_range_spec()
        self._expect(TokenType.RBRACKET, "Expected ']'")
        
        self._expect(TokenType.LBRACE, "Expected '{'")
        
        body: list[Node] = []
        
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.GREATER):
                body.append(self._parse_generator(in_connect=in_connect))
            elif in_connect:
                body.append(self._parse_connection())
            else:
                # Instance or constant - need to look ahead to determine which
                # For constants, it's IDENTIFIER EQUALS
                # For instances, it's IDENTIFIER (possibly with {expr}) COLON
                if self._check(TokenType.IDENTIFIER):
                    if self._peek.type == TokenType.EQUALS:
                        body.append(self._parse_constant())
                    else:
                        # Could be simple instance (name:) or template instance (name{i}:)
                        body.append(self._parse_generator_instance())
                else:
                    raise ParseError("Expected instance or constant declaration", self._current)
        
        self._expect(TokenType.RBRACE, "Expected '}'")
        
        return Generator(
            variable=variable,
            range_spec=range_spec,
            body=body,
            line=start.line,
            column=start.column
        )
    
    def _parse_range_spec(self) -> RangeSpec:
        """
        Parse a range specification.
        
        Examples:
            [8]           -> SimpleRange(8)
            [4:10]        -> StartEndRange(4, 10)
            [5:]          -> StartEndRange(5, None)
            [1:4, 8, 12:] -> MultiRange([...])
        """
        ranges: list[RangeSpec] = []
        ranges.append(self._parse_single_range())
        
        while self._match(TokenType.COMMA):
            ranges.append(self._parse_single_range())
        
        if len(ranges) == 1:
            return ranges[0]
        return MultiRange(ranges=ranges, line=ranges[0].line, column=ranges[0].column)
    
    def _parse_single_range(self) -> RangeSpec:
        """Parse a single range item."""
        start = self._current
        
        # Check for [:end] (leading colon)
        if self._match(TokenType.COLON):
            end = self._expect(TokenType.NUMBER, "Expected number").value
            return StartEndRange(start=None, end=end, line=start.line, column=start.column)
        
        first_num = self._expect(TokenType.NUMBER, "Expected number").value
        
        if self._match(TokenType.COLON):
            # [start:] or [start:end]
            if self._check(TokenType.NUMBER):
                end_num = self._advance().value
                return StartEndRange(start=first_num, end=end_num, line=start.line, column=start.column)
            else:
                # Open-ended
                return StartEndRange(start=first_num, end=None, line=start.line, column=start.column)
        
        # Simple range [N] means 1 to N
        return SimpleRange(end=first_num, line=start.line, column=start.column)


def parse(source: str, file_path: str = "<string>") -> Module:
    """Parse SHDL source code into an AST."""
    parser = Parser.from_source(source, file_path=file_path)
    return parser.parse()


def parse_file(path: str) -> Module:
    """Parse an SHDL file into an AST."""
    with open(path, "r") as f:
        source = f.read()
    # Register source and parse with file path for error reporting
    return parse(source, file_path=path)
