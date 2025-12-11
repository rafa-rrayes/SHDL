"""
Tests for the SHDL parser and flattener.
"""

import pytest
from pathlib import Path

from SHDL import (
    parse, parse_file, Lexer, Token, TokenType,
    Flattener, flatten_file, format_base_shdl,
    Module, Component, Port, Instance, Connection, Generator
)
from SHDL.errors import LexerError, ParseError, FlattenerError


# =============================================================================
# Lexer Tests
# =============================================================================

class TestLexer:
    """Tests for the SHDL lexer."""
    
    def test_simple_tokens(self):
        """Test basic token recognition."""
        lexer = Lexer("component -> : ; , . = { } [ ] ( ) >")
        tokens = lexer.tokenize()
        
        types = [t.type for t in tokens[:-1]]  # Exclude EOF
        expected = [
            TokenType.COMPONENT, TokenType.ARROW, TokenType.COLON,
            TokenType.SEMICOLON, TokenType.COMMA, TokenType.DOT,
            TokenType.EQUALS, TokenType.LBRACE, TokenType.RBRACE,
            TokenType.LBRACKET, TokenType.RBRACKET, TokenType.LPAREN,
            TokenType.RPAREN, TokenType.GREATER
        ]
        assert types == expected
    
    def test_identifiers(self):
        """Test identifier recognition."""
        lexer = Lexer("foo bar123 _underscore CamelCase")
        tokens = lexer.tokenize()
        
        idents = [t.value for t in tokens if t.type == TokenType.IDENTIFIER]
        assert idents == ["foo", "bar123", "_underscore", "CamelCase"]
    
    def test_numbers(self):
        """Test number literal recognition."""
        lexer = Lexer("42 0xFF 0b1010 255")
        tokens = lexer.tokenize()
        
        numbers = [t.value for t in tokens if t.type == TokenType.NUMBER]
        assert numbers == [42, 255, 10, 255]
    
    def test_keywords(self):
        """Test keyword recognition."""
        lexer = Lexer("component use connect")
        tokens = lexer.tokenize()
        
        types = [t.type for t in tokens[:-1]]
        assert types == [TokenType.COMPONENT, TokenType.USE, TokenType.CONNECT]
    
    def test_double_colon(self):
        """Test :: operator recognition."""
        lexer = Lexer("module::Component")
        tokens = lexer.tokenize()
        
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[1].type == TokenType.DOUBLE_COLON
        assert tokens[2].type == TokenType.IDENTIFIER
    
    def test_comments(self):
        """Test comment stripping."""
        source = '''
        component # this is a comment
        "this is also a comment"
        use
        '''
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        types = [t.type for t in tokens[:-1]]
        assert types == [TokenType.COMPONENT, TokenType.USE]
    
    def test_line_tracking(self):
        """Test line number tracking."""
        source = "foo\nbar\nbaz"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        lines = [t.line for t in tokens[:-1]]
        assert lines == [1, 2, 3]


# =============================================================================
# Parser Tests
# =============================================================================

class TestParser:
    """Tests for the SHDL parser."""
    
    def test_simple_component(self):
        """Test parsing a simple component."""
        source = '''
        component HalfAdder(A, B) -> (Sum, Carry) {
            xor1: XOR;
            and1: AND;
            
            connect {
                A -> xor1.A;
                B -> xor1.B;
                xor1.O -> Sum;
            }
        }
        '''
        module = parse(source)
        
        assert len(module.components) == 1
        comp = module.components[0]
        assert comp.name == "HalfAdder"
        assert len(comp.inputs) == 2
        assert len(comp.outputs) == 2
        assert comp.inputs[0].name == "A"
        assert comp.outputs[0].name == "Sum"
    
    def test_multi_bit_ports(self):
        """Test parsing multi-bit port declarations."""
        source = '''
        component Adder8(A[8], B[8]) -> (Sum[8], Cout) {
            connect {}
        }
        '''
        module = parse(source)
        comp = module.components[0]
        
        assert comp.inputs[0].width == 8
        assert comp.inputs[1].width == 8
        assert comp.outputs[0].width == 8
        assert comp.outputs[1].width is None
    
    def test_imports(self):
        """Test parsing import statements."""
        source = '''
        use fullAdder::{FullAdder};
        use alu::{ALU, Shifter};
        
        component Main(A) -> (B) {
            connect {}
        }
        '''
        module = parse(source)
        
        assert len(module.imports) == 2
        assert module.imports[0].module == "fullAdder"
        assert module.imports[0].components == ["FullAdder"]
        assert module.imports[1].module == "alu"
        assert module.imports[1].components == ["ALU", "Shifter"]
    
    def test_constants(self):
        """Test parsing constant declarations."""
        source = '''
        component Test(A) -> (B) {
            FIVE = 5;
            MASK = 0xFF;
            PATTERN = 0b1010;
            
            connect {}
        }
        '''
        module = parse(source)
        comp = module.components[0]
        
        constants = [n for n in comp.instances if hasattr(n, 'value')]
        assert len(constants) == 3
        assert constants[0].name == "FIVE"
        assert constants[0].value == 5
        assert constants[1].value == 255
        assert constants[2].value == 10
    
    def test_generator(self):
        """Test parsing generator constructs."""
        source = '''
        component Test(A[8]) -> (B[8]) {
            >i[8]{
                gate{i}: AND;
            }
            
            connect {
                >i[8]{
                    A[{i}] -> gate{i}.A;
                }
            }
        }
        '''
        module = parse(source)
        comp = module.components[0]
        
        # Check instance generators
        generators = [n for n in comp.instances if isinstance(n, Generator)]
        assert len(generators) == 1
        assert generators[0].variable == "i"
    
    def test_range_formats(self):
        """Test parsing various range formats."""
        source = '''
        component Test(A) -> (B) {
            >i[8]{ g1{i}: AND; }
            >j[2:5]{ g2{j}: OR; }
            
            connect {}
        }
        '''
        module = parse(source)
        comp = module.components[0]
        
        gens = [n for n in comp.instances if isinstance(n, Generator)]
        assert len(gens) == 2


# =============================================================================
# Flattener Tests
# =============================================================================

class TestFlattener:
    """Tests for the SHDL flattener."""
    
    def test_generator_expansion(self):
        """Test generator expansion."""
        source = '''
        component Test(A[4]) -> (B[4]) {
            >i[4]{
                not{i}: NOT;
            }
            
            connect {
                >i[4]{
                    A[{i}] -> not{i}.A;
                    not{i}.O -> B[{i}];
                }
            }
        }
        '''
        flattener = Flattener()
        flattener.load_source(source)
        result = flattener.flatten("Test")
        
        # Should have 4 NOT instances
        instances = [n for n in result.instances if isinstance(n, Instance)]
        assert len(instances) == 4
        
        names = [i.name for i in instances]
        assert "not1" in names
        assert "not2" in names
        assert "not3" in names
        assert "not4" in names
    
    def test_constant_materialization(self):
        """Test constant materialization to VCC/GND."""
        source = '''
        component Test(A) -> (B) {
            THREE = 3;
            xor1: XOR;
            
            connect {
                A -> xor1.A;
                THREE[1] -> xor1.B;
                xor1.O -> B;
            }
        }
        '''
        flattener = Flattener()
        flattener.load_source(source)
        result = flattener.flatten("Test")
        
        # Should have VCC instances for bits 1 and 2 of THREE (3 = 0b11)
        instances = [n for n in result.instances if isinstance(n, Instance)]
        instance_types = {i.name: i.component_type for i in instances}
        
        assert "THREE_bit1" in instance_types
        assert "THREE_bit2" in instance_types
        assert instance_types["THREE_bit1"] == "__VCC__"
        assert instance_types["THREE_bit2"] == "__VCC__"
    
    def test_hierarchy_flattening(self):
        """Test flattening of component hierarchy."""
        source = '''
        component Inner(A, B) -> (O) {
            and1: AND;
            connect {
                A -> and1.A;
                B -> and1.B;
                and1.O -> O;
            }
        }
        
        component Outer(X, Y) -> (Z) {
            inner1: Inner;
            connect {
                X -> inner1.A;
                Y -> inner1.B;
                inner1.O -> Z;
            }
        }
        '''
        flattener = Flattener()
        flattener.load_source(source)
        result = flattener.flatten("Outer")
        
        # Inner should be inlined with prefix
        instances = [n for n in result.instances if isinstance(n, Instance)]
        names = [i.name for i in instances]
        
        # Should have inner1_and1 instead of inner1
        assert "inner1_and1" in names
        assert all(i.component_type in {"AND", "OR", "NOT", "XOR", "__VCC__", "__GND__"} 
                   for i in instances)
    
    def test_format_base_shdl(self):
        """Test Base SHDL formatting."""
        source = '''
        component Simple(A, B) -> (O) {
            and1: AND;
            connect {
                A -> and1.A;
                B -> and1.B;
                and1.O -> O;
            }
        }
        '''
        flattener = Flattener()
        flattener.load_source(source)
        result = flattener.flatten_to_base_shdl("Simple")
        
        assert "component Simple(A, B) -> (O)" in result
        assert "and1: AND;" in result
        assert "A -> and1.A;" in result


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests using example files."""
    
    @pytest.fixture
    def examples_dir(self):
        """Get the examples directory path."""
        return Path(__file__).parent.parent / "examples"
    
    def test_parse_full_adder(self, examples_dir):
        """Test parsing the fullAdder.shdl example."""
        path = examples_dir / "fullAdder.shdl"
        if path.exists():
            module = parse_file(str(path))
            assert len(module.components) == 1
            assert module.components[0].name == "FullAdder"
    
    def test_parse_or8inputs(self, examples_dir):
        """Test parsing the or8inputs.shdl example."""
        path = examples_dir / "or8inputs.shdl"
        if path.exists():
            module = parse_file(str(path))
            assert len(module.components) == 1
            comp = module.components[0]
            assert comp.name == "Or8Inputs"
            # Should have generators
            generators = [n for n in comp.instances if isinstance(n, Generator)]
            assert len(generators) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
