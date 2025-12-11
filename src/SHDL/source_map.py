"""
SHDL Source Mapping

Provides source location tracking for AST nodes and error reporting.
Supports tracking through generator expansion and component inlining.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path


@dataclass(frozen=True)
class SourceSpan:
    """
    Represents a span of source code.
    
    Tracks the exact location of a source element including file path
    and start/end positions. Used for error reporting.
    
    Attributes:
        file_path: Path to the source file (or "<string>" for inline code)
        start_line: 1-based line number where the span starts
        start_col: 1-based column number where the span starts
        end_line: 1-based line number where the span ends
        end_col: 1-based column number where the span ends
    """
    file_path: str = "<unknown>"
    start_line: int = 1
    start_col: int = 1
    end_line: int = 1
    end_col: int = 1
    
    @classmethod
    def from_token(cls, token: "Token", file_path: str = "<string>") -> "SourceSpan":
        """Create a SourceSpan from a token."""
        # Tokens typically only have start position; estimate end from value
        value_len = len(str(token.value)) if token.value is not None else 1
        return cls(
            file_path=file_path,
            start_line=token.line,
            start_col=token.column,
            end_line=token.line,
            end_col=token.column + value_len - 1
        )
    
    @classmethod
    def from_positions(
        cls,
        file_path: str,
        start_line: int,
        start_col: int,
        end_line: int = None,
        end_col: int = None
    ) -> "SourceSpan":
        """Create a SourceSpan from explicit positions."""
        return cls(
            file_path=file_path,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line if end_line is not None else start_line,
            end_col=end_col if end_col is not None else start_col
        )
    
    @classmethod
    def merge(cls, start: "SourceSpan", end: "SourceSpan") -> "SourceSpan":
        """
        Merge two spans into one that covers both.
        
        Useful for creating a span that covers an entire construct
        from its first token to its last.
        """
        if start.file_path != end.file_path:
            # If files differ, prefer the start span
            return start
        
        return cls(
            file_path=start.file_path,
            start_line=start.start_line,
            start_col=start.start_col,
            end_line=end.end_line,
            end_col=end.end_col
        )
    
    def __str__(self) -> str:
        """Format as file:line:col for error messages."""
        if self.start_line == self.end_line:
            if self.start_col == self.end_col:
                return f"{self.file_path}:{self.start_line}:{self.start_col}"
            else:
                return f"{self.file_path}:{self.start_line}:{self.start_col}-{self.end_col}"
        else:
            return f"{self.file_path}:{self.start_line}:{self.start_col}-{self.end_line}:{self.end_col}"
    
    def short_location(self) -> str:
        """Return a short location string (just line:col)."""
        return f"{self.start_line}:{self.start_col}"
    
    @property
    def filename(self) -> str:
        """Get just the filename without the full path."""
        return Path(self.file_path).name if self.file_path != "<unknown>" else self.file_path


@dataclass
class GeneratorContext:
    """
    Context for a generator expansion.
    
    Tracks the variable name, current value, and original span
    of the generator construct.
    """
    variable: str  # e.g., "i"
    value: int     # e.g., 3
    span: SourceSpan  # Where the generator was defined
    
    def __str__(self) -> str:
        return f"{self.variable}={self.value}"


@dataclass
class SourceOrigin:
    """
    Represents the origin of a piece of generated/expanded code.
    
    This tracks how code was derived through generator expansion
    and component inlining, allowing error messages to trace back
    to the original source location.
    
    Example:
        A signal "fa3.A" might have an origin like:
        - Primary span: adder8.shdl:5:9 (where the connection was written)
        - Generator context: [i=3] (from >i[8]{ ... })
        - Inlined from: cpu.shdl:45 (where Adder8 was instantiated)
    """
    # Primary source location
    span: SourceSpan
    
    # If this came from a generator, what were the variable values?
    generator_contexts: List[GeneratorContext] = field(default_factory=list)
    
    # If this was inlined from another component
    inlined_from: Optional["SourceOrigin"] = None
    
    # Human-readable explanation of the origin
    description: Optional[str] = None
    
    @classmethod
    def simple(cls, span: SourceSpan) -> "SourceOrigin":
        """Create a simple origin from just a span."""
        return cls(span=span)
    
    @classmethod
    def from_generator(
        cls,
        span: SourceSpan,
        variable: str,
        value: int,
        generator_span: SourceSpan
    ) -> "SourceOrigin":
        """Create an origin for generator-expanded code."""
        ctx = GeneratorContext(variable=variable, value=value, span=generator_span)
        return cls(span=span, generator_contexts=[ctx])
    
    def add_generator_context(self, variable: str, value: int, span: SourceSpan) -> "SourceOrigin":
        """Add a generator context (for nested generators)."""
        ctx = GeneratorContext(variable=variable, value=value, span=span)
        new_contexts = self.generator_contexts + [ctx]
        return SourceOrigin(
            span=self.span,
            generator_contexts=new_contexts,
            inlined_from=self.inlined_from,
            description=self.description
        )
    
    def with_inline_parent(self, parent: "SourceOrigin") -> "SourceOrigin":
        """Mark this origin as inlined from a parent origin."""
        return SourceOrigin(
            span=self.span,
            generator_contexts=self.generator_contexts,
            inlined_from=parent,
            description=self.description
        )
    
    def format_location(self) -> str:
        """Format the primary location for error messages."""
        loc = str(self.span)
        if self.generator_contexts:
            ctx_str = ", ".join(str(ctx) for ctx in self.generator_contexts)
            loc = f"{loc} (in generator with {ctx_str})"
        return loc
    
    def format_chain(self) -> List[str]:
        """
        Format the full origin chain for detailed error messages.
        
        Returns a list of strings, each describing one step in the chain.
        """
        result = [self.format_location()]
        
        if self.inlined_from:
            current = self.inlined_from
            while current:
                result.append(f"  inlined from {current.format_location()}")
                current = current.inlined_from
        
        return result


class SourceFile:
    """
    Represents a source file for error reporting.
    
    Caches file contents for displaying source snippets in error messages.
    """
    
    _cache: dict[str, "SourceFile"] = {}
    
    def __init__(self, path: str, content: Optional[str] = None):
        self.path = path
        self._content = content
        self._lines: Optional[List[str]] = None
    
    @classmethod
    def get(cls, path: str, content: Optional[str] = None) -> "SourceFile":
        """Get or create a SourceFile for the given path."""
        if path not in cls._cache:
            cls._cache[path] = cls(path, content)
        elif content is not None:
            # Update content if provided
            cls._cache[path]._content = content
            cls._cache[path]._lines = None
        return cls._cache[path]
    
    @classmethod
    def register(cls, path: str, content: str) -> "SourceFile":
        """Register a source file with its content."""
        sf = cls(path, content)
        cls._cache[path] = sf
        return sf
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear the source file cache."""
        cls._cache.clear()
    
    @property
    def lines(self) -> List[str]:
        """Get the lines of the file (loading if necessary)."""
        if self._lines is None:
            if self._content is not None:
                self._lines = self._content.splitlines()
            else:
                try:
                    with open(self.path, 'r') as f:
                        self._lines = f.read().splitlines()
                except (FileNotFoundError, IOError):
                    self._lines = []
        return self._lines
    
    def get_line(self, line_number: int) -> Optional[str]:
        """Get a specific line (1-based)."""
        idx = line_number - 1
        if 0 <= idx < len(self.lines):
            return self.lines[idx]
        return None
    
    def get_lines(self, start_line: int, end_line: int) -> List[str]:
        """Get a range of lines (1-based, inclusive)."""
        start_idx = max(0, start_line - 1)
        end_idx = min(len(self.lines), end_line)
        return self.lines[start_idx:end_idx]
    
    def get_snippet(self, span: SourceSpan, context_lines: int = 2) -> List[tuple[int, str]]:
        """
        Get a code snippet around the given span.
        
        Returns a list of (line_number, line_content) tuples.
        """
        start = max(1, span.start_line - context_lines)
        end = min(len(self.lines), span.end_line + context_lines)
        
        return [(i, self.lines[i - 1]) for i in range(start, end + 1)]


def highlight_span(line: str, start_col: int, end_col: int, char: str = "^") -> str:
    """
    Create an underline string highlighting part of a line.
    
    Args:
        line: The source line
        start_col: 1-based start column
        end_col: 1-based end column
        char: Character to use for highlighting
    
    Returns:
        A string of spaces and highlight characters
    """
    # Adjust for 1-based columns
    start = start_col - 1
    end = end_col
    
    # Build the highlight line
    prefix = " " * start
    highlight = char * max(1, end - start)
    
    return prefix + highlight
