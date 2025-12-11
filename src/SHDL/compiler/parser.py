"""
Base SHDL Parser

Parses Base SHDL source code into an AST.
"""

from typing import Optional

from .lexer import BaseSHDLLexer, Token, TokenType, LexerError
from .ast import (
    Module, Component, Port, Instance, Connection, SignalRef,
    PrimitiveType
)


class ParseError(Exception):
    """Error during parsing."""
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Line {line}, column {column}: {message}")


class BaseSHDLParser:
    """
    Parser for Base SHDL.
    
    Grammar (EBNF):
        Module        = { Component } ;
        Component     = "component" Identifier "(" PortList ")" "->" "(" PortList ")" "{" 
                        { InstanceDecl } 
                        ConnectBlock 
                        "}" ;
        PortList      = [ Port { "," Port } ] ;
        Port          = Identifier [ "[" Number "]" ] ;
        InstanceDecl  = Identifier ":" PrimitiveType ";" ;
        PrimitiveType = "AND" | "OR" | "NOT" | "XOR" | "__VCC__" | "__GND__" ;
        ConnectBlock  = "connect" "{" { Connection } "}" ;
        Connection    = Signal "->" Signal ";" ;
        Signal        = Identifier [ "[" Number "]" ]
                      | Identifier "." Identifier ;
    """
    
    PRIMITIVE_TOKENS = {
        TokenType.AND, TokenType.OR, TokenType.NOT, TokenType.XOR,
        TokenType.VCC, TokenType.GND
    }
    
    def __init__(self, source: str):
        self.lexer = BaseSHDLLexer(source)
        self.tokens = self.lexer.tokenize()
        self.pos = 0
    
    @classmethod
    def parse(cls, source: str) -> Module:
        """Parse source code and return a Module."""
        parser = cls(source)
        return parser.parse_module()
    
    @classmethod
    def parse_file(cls, path: str) -> Module:
        """Parse a file and return a Module."""
        with open(path, 'r') as f:
            source = f.read()
        return cls.parse(source)
    
    def current(self) -> Token:
        """Get the current token."""
        if self.pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[self.pos]
    
    def peek(self, offset: int = 1) -> Token:
        """Look ahead without consuming."""
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[pos]
    
    def advance(self) -> Token:
        """Consume and return the current token."""
        token = self.current()
        if token.type != TokenType.EOF:
            self.pos += 1
        return token
    
    def check(self, token_type: TokenType) -> bool:
        """Check if the current token is of the given type."""
        return self.current().type == token_type
    
    def match(self, *token_types: TokenType) -> Optional[Token]:
        """Consume if current token matches any of the given types."""
        for tt in token_types:
            if self.check(tt):
                return self.advance()
        return None
    
    def expect(self, token_type: TokenType, message: str = None) -> Token:
        """Consume a token of the expected type, or raise an error."""
        if self.check(token_type):
            return self.advance()
        
        token = self.current()
        msg = message or f"Expected {token_type.name}, got {token.type.name}"
        raise ParseError(msg, token.line, token.column)
    
    def error(self, message: str) -> ParseError:
        """Create a parse error at the current position."""
        token = self.current()
        return ParseError(message, token.line, token.column)
    
    def parse_module(self) -> Module:
        """Parse a complete module."""
        components = []
        
        while not self.check(TokenType.EOF):
            comp = self.parse_component()
            components.append(comp)
        
        return Module(components=components)
    
    def parse_component(self) -> Component:
        """
        Parse a component definition.
        
        component Name(inputs) -> (outputs) { instances connect { connections } }
        """
        start_token = self.expect(TokenType.COMPONENT, "Expected 'component'")
        
        name_token = self.expect(TokenType.IDENTIFIER, "Expected component name")
        name = name_token.value
        
        # Input ports
        self.expect(TokenType.LPAREN, "Expected '(' after component name")
        inputs = self.parse_port_list()
        self.expect(TokenType.RPAREN, "Expected ')' after input ports")
        
        # Arrow
        self.expect(TokenType.ARROW, "Expected '->' between input and output ports")
        
        # Output ports
        self.expect(TokenType.LPAREN, "Expected '(' before output ports")
        outputs = self.parse_port_list()
        self.expect(TokenType.RPAREN, "Expected ')' after output ports")
        
        # Body
        self.expect(TokenType.LBRACE, "Expected '{' to start component body")
        
        # Parse instances
        instances = []
        while self.check(TokenType.IDENTIFIER):
            inst = self.parse_instance()
            instances.append(inst)
        
        # Parse connect block
        connections = []
        if self.check(TokenType.CONNECT):
            connections = self.parse_connect_block()
        
        self.expect(TokenType.RBRACE, "Expected '}' to end component body")
        
        return Component(
            name=name,
            inputs=inputs,
            outputs=outputs,
            instances=instances,
            connections=connections,
            line=start_token.line,
            column=start_token.column
        )
    
    def parse_port_list(self) -> list[Port]:
        """Parse a comma-separated list of port declarations."""
        ports = []
        
        # Empty list
        if self.check(TokenType.RPAREN):
            return ports
        
        # First port
        ports.append(self.parse_port())
        
        # Remaining ports
        while self.match(TokenType.COMMA):
            ports.append(self.parse_port())
        
        return ports
    
    def parse_port(self) -> Port:
        """
        Parse a port declaration: Name or Name[width]
        """
        name_token = self.expect(TokenType.IDENTIFIER, "Expected port name")
        name = name_token.value
        width = None
        
        # Optional width
        if self.match(TokenType.LBRACKET):
            width_token = self.expect(TokenType.NUMBER, "Expected port width")
            width = width_token.value
            self.expect(TokenType.RBRACKET, "Expected ']' after port width")
        
        return Port(
            name=name,
            width=width,
            line=name_token.line,
            column=name_token.column
        )
    
    def parse_instance(self) -> Instance:
        """
        Parse an instance declaration: name: PrimitiveType;
        """
        name_token = self.expect(TokenType.IDENTIFIER, "Expected instance name")
        name = name_token.value
        
        self.expect(TokenType.COLON, "Expected ':' after instance name")
        
        # Parse primitive type
        prim_token = self.current()
        if prim_token.type not in self.PRIMITIVE_TOKENS:
            raise self.error(f"Expected primitive type (AND, OR, NOT, XOR, __VCC__, __GND__), got {prim_token.value}")
        
        self.advance()
        primitive = self._token_to_primitive(prim_token)
        
        self.expect(TokenType.SEMICOLON, "Expected ';' after instance declaration")
        
        return Instance(
            name=name,
            primitive=primitive,
            line=name_token.line,
            column=name_token.column
        )
    
    def _token_to_primitive(self, token: Token) -> PrimitiveType:
        """Convert a token to a PrimitiveType."""
        mapping = {
            TokenType.AND: PrimitiveType.AND,
            TokenType.OR: PrimitiveType.OR,
            TokenType.NOT: PrimitiveType.NOT,
            TokenType.XOR: PrimitiveType.XOR,
            TokenType.VCC: PrimitiveType.VCC,
            TokenType.GND: PrimitiveType.GND,
        }
        return mapping[token.type]
    
    def parse_connect_block(self) -> list[Connection]:
        """
        Parse a connect block: connect { connections }
        """
        self.expect(TokenType.CONNECT, "Expected 'connect'")
        self.expect(TokenType.LBRACE, "Expected '{' after 'connect'")
        
        connections = []
        while not self.check(TokenType.RBRACE) and not self.check(TokenType.EOF):
            conn = self.parse_connection()
            connections.append(conn)
        
        self.expect(TokenType.RBRACE, "Expected '}' to end connect block")
        
        return connections
    
    def parse_connection(self) -> Connection:
        """
        Parse a connection: source -> destination;
        """
        source = self.parse_signal()
        
        arrow_token = self.expect(TokenType.ARROW, "Expected '->' in connection")
        
        destination = self.parse_signal()
        
        self.expect(TokenType.SEMICOLON, "Expected ';' after connection")
        
        return Connection(
            source=source,
            destination=destination,
            line=arrow_token.line,
            column=arrow_token.column
        )
    
    def parse_signal(self) -> SignalRef:
        """
        Parse a signal reference:
            - Name           (port)
            - Name[index]    (indexed port)
            - Instance.Port  (instance port)
            - Instance.Port[index] (indexed instance port)
        """
        name_token = self.expect(TokenType.IDENTIFIER, "Expected signal name")
        name = name_token.value
        
        instance = None
        
        # Check for instance.port
        if self.match(TokenType.DOT):
            instance = name
            port_token = self.expect(TokenType.IDENTIFIER, "Expected port name after '.'")
            name = port_token.value
        
        # Check for indexed port
        index = None
        if self.match(TokenType.LBRACKET):
            index_token = self.expect(TokenType.NUMBER, "Expected bit index")
            index = index_token.value
            self.expect(TokenType.RBRACKET, "Expected ']' after bit index")
        
        return SignalRef(
            name=name,
            instance=instance,
            index=index,
            line=name_token.line,
            column=name_token.column
        )


# Convenience functions
def parse(source: str) -> Module:
    """Parse Base SHDL source code."""
    return BaseSHDLParser.parse(source)


def parse_file(path: str) -> Module:
    """Parse a Base SHDL file."""
    return BaseSHDLParser.parse_file(path)
