"""
SHDL Error Types and Formatting

Provides Rust/Elm-quality error messages with:
- Unique error codes for documentation lookup
- Precise source locations with code snippets
- Helpful suggestions and fixes
- Color-coded output (when supported)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Union
import sys
import os

from .source_map import SourceSpan, SourceOrigin, SourceFile, highlight_span


# =============================================================================
# Color Support
# =============================================================================

def supports_color() -> bool:
    """Check if the terminal supports color output."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


class Color:
    """ANSI color codes for terminal output."""
    
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    
    @classmethod
    def enabled(cls) -> bool:
        return supports_color()
    
    @classmethod
    def red(cls, text: str) -> str:
        if cls.enabled():
            return f"{cls.RED}{text}{cls.RESET}"
        return text
    
    @classmethod
    def yellow(cls, text: str) -> str:
        if cls.enabled():
            return f"{cls.YELLOW}{text}{cls.RESET}"
        return text
    
    @classmethod
    def blue(cls, text: str) -> str:
        if cls.enabled():
            return f"{cls.BLUE}{text}{cls.RESET}"
        return text
    
    @classmethod
    def cyan(cls, text: str) -> str:
        if cls.enabled():
            return f"{cls.CYAN}{text}{cls.RESET}"
        return text
    
    @classmethod
    def green(cls, text: str) -> str:
        if cls.enabled():
            return f"{cls.GREEN}{text}{cls.RESET}"
        return text
    
    @classmethod
    def bold(cls, text: str) -> str:
        if cls.enabled():
            return f"{cls.BOLD}{text}{cls.RESET}"
        return text
    
    @classmethod
    def dim(cls, text: str) -> str:
        if cls.enabled():
            return f"{cls.DIM}{text}{cls.RESET}"
        return text


# =============================================================================
# Error Codes
# =============================================================================

class ErrorCode(Enum):
    """
    Unique error codes for all SHDL errors.
    
    Code ranges:
        E01xx - Lexer errors
        E02xx - Parse errors  
        E03xx - Name resolution errors
        E04xx - Type/width errors
        E05xx - Connection errors
        E06xx - Generator errors
        E07xx - Import errors
        E08xx - Constant errors
        W01xx - Warnings
    """
    
    # E01xx - Lexer Errors
    E0101 = "Invalid character"
    E0102 = "Unterminated string"
    E0103 = "Invalid number literal"
    E0104 = "Unterminated triple-quoted comment"
    E0105 = "Invalid hexadecimal number"
    E0106 = "Invalid binary number"
    
    # E02xx - Parse Errors
    E0201 = "Unexpected token"
    E0202 = "Missing semicolon"
    E0203 = "Missing closing brace"
    E0204 = "Missing closing bracket"
    E0205 = "Missing closing parenthesis"
    E0206 = "Expected identifier"
    E0207 = "Expected component name"
    E0208 = "Expected port declaration"
    E0209 = "Invalid port width"
    E0210 = "Expected '->' between inputs and outputs"
    E0211 = "Expected connect block"
    E0212 = "Invalid connection syntax"
    E0213 = "Expected expression"
    E0214 = "Invalid generator syntax"
    E0215 = "Expected 'component' or 'use'"
    
    # E03xx - Name Resolution Errors
    E0301 = "Unknown component type"
    E0302 = "Undefined signal"
    E0303 = "Undefined instance"
    E0304 = "Unknown port"
    E0305 = "Duplicate instance name"
    E0306 = "Duplicate constant name"
    E0307 = "Duplicate component name"
    E0308 = "Undefined generator variable"
    E0309 = "Signal name shadows port"
    E0310 = "Instance name shadows port"
    
    # E04xx - Type/Width Errors
    E0401 = "Port width mismatch"
    E0402 = "Invalid bit subscript"
    E0403 = "Subscript out of range"
    E0404 = "Slice width mismatch"
    E0405 = "Cannot subscript single-bit signal"
    E0406 = "Invalid slice range"
    E0407 = "Incompatible signal types"
    
    # E05xx - Connection Errors
    E0501 = "Missing input connection"
    E0502 = "Missing output driver"
    E0503 = "Multiply driven signal"
    E0504 = "Unconnected instance output"
    E0505 = "Combinational loop detected"
    E0506 = "Invalid connection target"
    E0507 = "Cannot connect to input port"
    E0508 = "Cannot read from output port"
    
    # E06xx - Generator Errors
    E0601 = "Invalid generator range"
    E0602 = "Generator name collision"
    E0603 = "Invalid generator expression"
    E0604 = "Division by zero in generator"
    E0605 = "Empty generator range"
    E0606 = "Generator variable shadows outer variable"
    
    # E07xx - Import Errors
    E0701 = "Module not found"
    E0702 = "Component not found in module"
    E0703 = "Circular import detected"
    E0704 = "Invalid import path"
    E0705 = "Duplicate import"
    
    # E08xx - Constant Errors
    E0801 = "Constant value overflow"
    E0802 = "Invalid constant expression"
    E0803 = "Negative constant value"
    E0804 = "Constant width too small"
    
    # W01xx - Warnings
    W0101 = "Unused signal"
    W0102 = "Unused instance"
    W0103 = "Unused constant"
    W0104 = "Unused import"
    W0105 = "Redundant connection"
    W0106 = "Suspicious constant value"
    W0107 = "Instance output not connected"
    
    @property
    def code(self) -> str:
        """Get the error code string (e.g., 'E0301')."""
        return self.name
    
    @property
    def is_warning(self) -> bool:
        """Check if this is a warning rather than an error."""
        return self.name.startswith("W")
    
    @property
    def is_error(self) -> bool:
        """Check if this is an error (not a warning)."""
        return self.name.startswith("E")


# =============================================================================
# Diagnostic Severity
# =============================================================================

class Severity(Enum):
    """Severity level for diagnostics."""
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"
    HELP = "help"


# =============================================================================
# Code Annotations
# =============================================================================

@dataclass
class Annotation:
    """
    An annotation on a span of source code.
    
    Used to highlight and label parts of code in error messages.
    """
    span: SourceSpan
    label: str
    is_primary: bool = True  # Primary annotations get ^^^ under them
    
    def format(self, source_file: SourceFile) -> List[str]:
        """Format this annotation for display."""
        lines = []
        
        line_content = source_file.get_line(self.span.start_line)
        if line_content is None:
            return []
        
        # Line number gutter
        line_num = str(self.span.start_line)
        gutter_width = len(line_num) + 1
        
        # Source line
        lines.append(f" {line_num} | {line_content}")
        
        # Underline
        char = "^" if self.is_primary else "-"
        underline = highlight_span(
            line_content,
            self.span.start_col,
            self.span.end_col,
            char
        )
        
        gutter = " " * gutter_width + "|"
        lines.append(f"{gutter} {underline} {self.label}")
        
        return lines


# =============================================================================
# Suggestion / Help
# =============================================================================

@dataclass
class Suggestion:
    """
    A suggested fix for an error.
    
    Can include a code snippet showing the suggested change.
    """
    message: str
    span: Optional[SourceSpan] = None
    replacement: Optional[str] = None  # Suggested replacement text
    
    def format(self, source_file: Optional[SourceFile] = None) -> List[str]:
        """Format this suggestion for display."""
        lines = []
        
        label = Color.cyan("help")
        lines.append(f"{label}: {self.message}")
        
        if self.span and self.replacement and source_file:
            line_num = str(self.span.start_line)
            gutter_width = len(line_num) + 1
            gutter = " " * gutter_width + "|"
            
            lines.append(gutter)
            lines.append(f" {line_num} | {self.replacement}")
            lines.append(gutter)
        
        return lines


# =============================================================================
# Related Information
# =============================================================================

@dataclass
class RelatedInfo:
    """
    Related information for an error.
    
    Points to other relevant code locations.
    """
    span: SourceSpan
    message: str
    
    def format(self, source_file: SourceFile) -> List[str]:
        """Format this related info for display."""
        lines = []
        
        # Location header
        loc = f"--> {self.span}"
        lines.append(f"  {loc}")
        
        # Source line
        line_content = source_file.get_line(self.span.start_line)
        if line_content:
            line_num = str(self.span.start_line)
            gutter = " " * (len(line_num) + 1) + "|"
            
            lines.append(f"   {gutter}")
            lines.append(f" {line_num} | {line_content}")
            
            # Underline with label
            underline = highlight_span(line_content, self.span.start_col, self.span.end_col, "-")
            lines.append(f"   {gutter} {underline} {self.message}")
        
        return lines


# =============================================================================
# Diagnostic
# =============================================================================

@dataclass
class Diagnostic:
    """
    A complete diagnostic message (error, warning, or note).
    
    Contains all information needed to display a rich error message
    with source context, related locations, and suggestions.
    """
    code: ErrorCode
    message: str
    span: SourceSpan
    severity: Severity = field(default=None)
    annotations: List[Annotation] = field(default_factory=list)
    related: List[RelatedInfo] = field(default_factory=list)
    suggestions: List[Suggestion] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    origin: Optional[SourceOrigin] = None
    
    def __post_init__(self):
        if self.severity is None:
            self.severity = Severity.WARNING if self.code.is_warning else Severity.ERROR
    
    def format(self, use_color: bool = True) -> str:
        """
        Format this diagnostic as a complete error message.
        
        Returns a multi-line string suitable for display.
        """
        lines = []
        
        # Header: error[E0301]: Unknown component type
        if self.severity == Severity.ERROR:
            prefix = Color.bold(Color.red(f"error[{self.code.code}]"))
        elif self.severity == Severity.WARNING:
            prefix = Color.bold(Color.yellow(f"warning[{self.code.code}]"))
        else:
            prefix = Color.bold(f"{self.severity.value}[{self.code.code}]")
        
        header = f"{prefix}: {Color.bold(self.message)}"
        lines.append(header)
        
        # Primary location: --> file.shdl:10:5
        loc = f"  --> {self.span}"
        lines.append(loc)
        
        # Source context
        source_file = SourceFile.get(self.span.file_path)
        
        line_content = source_file.get_line(self.span.start_line)
        if line_content:
            line_num = str(self.span.start_line)
            gutter_width = len(line_num) + 1
            gutter = " " * gutter_width + "|"
            
            lines.append(f"   {gutter}")
            lines.append(f" {line_num} | {line_content}")
            
            # Primary underline
            underline = highlight_span(line_content, self.span.start_col, self.span.end_col)
            primary_label = self.annotations[0].label if self.annotations else ""
            lines.append(f"   {gutter} {Color.red(underline)} {Color.red(primary_label)}")
        
        # Secondary annotations
        for ann in self.annotations[1:]:
            ann_lines = ann.format(source_file)
            lines.extend(["   " + line for line in ann_lines])
        
        # Related info
        for rel in self.related:
            lines.append("   |")
            rel_file = SourceFile.get(rel.span.file_path)
            rel_lines = rel.format(rel_file)
            lines.extend(rel_lines)
        
        # Suggestions
        for sug in self.suggestions:
            lines.append("   |")
            sug_lines = sug.format(source_file)
            lines.extend(sug_lines)
        
        # Notes
        for note in self.notes:
            lines.append(f"   = {Color.bold('note')}: {note}")
        
        # Generator context (if applicable)
        if self.origin and self.origin.generator_contexts:
            ctx_parts = [str(c) for c in self.origin.generator_contexts]
            lines.append(f"   = {Color.bold('note')}: in generator expansion with {', '.join(ctx_parts)}")
        
        # Inlining chain
        if self.origin and self.origin.inlined_from:
            current = self.origin.inlined_from
            while current:
                lines.append(f"   = {Color.bold('note')}: while inlining from {current.span}")
                current = current.inlined_from
        
        lines.append("")  # Blank line after diagnostic
        
        return "\n".join(lines)
    
    def __str__(self) -> str:
        return self.format()


# =============================================================================
# Exception Classes
# =============================================================================

class SHDLError(Exception):
    """
    Base exception for all SHDL errors.
    
    Carries a Diagnostic for rich error reporting.
    """
    
    def __init__(
        self,
        message: str,
        code: ErrorCode = None,
        span: SourceSpan = None,
        diagnostic: Diagnostic = None
    ):
        self.message = message
        self._code = code
        self._span = span
        self._diagnostic = diagnostic
        
        # Format the full error message
        if diagnostic:
            super().__init__(diagnostic.format())
        elif span:
            super().__init__(f"{span}: {message}")
        else:
            super().__init__(message)
    
    @property
    def diagnostic(self) -> Optional[Diagnostic]:
        """Get the associated diagnostic, if any."""
        return self._diagnostic
    
    @property
    def span(self) -> Optional[SourceSpan]:
        """Get the source span, if any."""
        if self._diagnostic:
            return self._diagnostic.span
        return self._span
    
    @property
    def code(self) -> Optional[ErrorCode]:
        """Get the error code, if any."""
        if self._diagnostic:
            return self._diagnostic.code
        return self._code


class LexerError(SHDLError):
    """Raised when the lexer encounters an invalid token."""
    
    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int = 0,
        file_path: str = "<string>",
        code: ErrorCode = ErrorCode.E0101
    ):
        self.line = line
        self.column = column
        
        span = SourceSpan(
            file_path=file_path,
            start_line=line,
            start_col=column,
            end_line=line,
            end_col=column
        )
        
        diagnostic = Diagnostic(
            code=code,
            message=message,
            span=span,
            annotations=[Annotation(span=span, label=code.value)]
        )
        
        super().__init__(message, code=code, span=span, diagnostic=diagnostic)


class ParseError(SHDLError):
    """Raised when the parser encounters invalid syntax."""
    
    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int = 0,
        file_path: str = "<string>",
        code: ErrorCode = ErrorCode.E0201,
        span: SourceSpan = None,
        suggestions: List[Suggestion] = None,
        notes: List[str] = None
    ):
        self.line = line
        self.column = column
        
        if span is None:
            span = SourceSpan(
                file_path=file_path,
                start_line=line,
                start_col=column,
                end_line=line,
                end_col=column
            )
        
        diagnostic = Diagnostic(
            code=code,
            message=message,
            span=span,
            annotations=[Annotation(span=span, label="")],
            suggestions=suggestions or [],
            notes=notes or []
        )
        
        super().__init__(message, code=code, span=span, diagnostic=diagnostic)


class FlattenerError(SHDLError):
    """Raised when flattening encounters an error."""
    
    def __init__(
        self,
        message: str,
        span: SourceSpan = None,
        code: ErrorCode = None,
        origin: SourceOrigin = None
    ):
        diagnostic = None
        if span:
            diagnostic = Diagnostic(
                code=code or ErrorCode.E0301,
                message=message,
                span=span,
                origin=origin
            )
        
        super().__init__(message, code=code, span=span, diagnostic=diagnostic)


class ValidationError(SHDLError):
    """Raised when validation fails."""
    
    def __init__(
        self,
        message: str,
        span: SourceSpan = None,
        code: ErrorCode = None,
        diagnostic: Diagnostic = None
    ):
        super().__init__(message, code=code, span=span, diagnostic=diagnostic)


class SemanticError(SHDLError):
    """Raised during semantic analysis."""
    
    def __init__(self, diagnostic: Diagnostic):
        super().__init__(
            diagnostic.message,
            code=diagnostic.code,
            span=diagnostic.span,
            diagnostic=diagnostic
        )


class ImportError_(SHDLError):
    """Raised when an import fails."""
    
    def __init__(
        self,
        message: str,
        span: SourceSpan = None,
        code: ErrorCode = ErrorCode.E0701,
        searched_paths: List[str] = None
    ):
        notes = []
        if searched_paths:
            notes.append("searched in: " + ", ".join(searched_paths))
        
        diagnostic = None
        if span:
            diagnostic = Diagnostic(
                code=code,
                message=message,
                span=span,
                notes=notes
            )
        
        super().__init__(message, code=code, span=span, diagnostic=diagnostic)


# =============================================================================
# Diagnostic Collection
# =============================================================================

class DiagnosticCollection:
    """
    Collects multiple diagnostics during compilation.
    
    Allows error recovery - the compiler can report multiple errors
    instead of stopping at the first one.
    """
    
    def __init__(self):
        self._diagnostics: List[Diagnostic] = []
        self._error_count: int = 0
        self._warning_count: int = 0
    
    def add(self, diagnostic: Diagnostic) -> None:
        """Add a diagnostic to the collection."""
        self._diagnostics.append(diagnostic)
        if diagnostic.severity == Severity.ERROR:
            self._error_count += 1
        elif diagnostic.severity == Severity.WARNING:
            self._warning_count += 1
    
    def error(
        self,
        code: ErrorCode,
        message: str,
        span: SourceSpan,
        **kwargs
    ) -> None:
        """Add an error diagnostic."""
        self.add(Diagnostic(
            code=code,
            message=message,
            span=span,
            severity=Severity.ERROR,
            **kwargs
        ))
    
    def warning(
        self,
        code: ErrorCode,
        message: str,
        span: SourceSpan,
        **kwargs
    ) -> None:
        """Add a warning diagnostic."""
        self.add(Diagnostic(
            code=code,
            message=message,
            span=span,
            severity=Severity.WARNING,
            **kwargs
        ))
    
    def has_errors(self) -> bool:
        """Check if any errors have been reported."""
        return self._error_count > 0
    
    def has_warnings(self) -> bool:
        """Check if any warnings have been reported."""
        return self._warning_count > 0
    
    @property
    def error_count(self) -> int:
        return self._error_count
    
    @property
    def warning_count(self) -> int:
        return self._warning_count
    
    @property
    def diagnostics(self) -> List[Diagnostic]:
        return list(self._diagnostics)
    
    def clear(self) -> None:
        """Clear all diagnostics."""
        self._diagnostics.clear()
        self._error_count = 0
        self._warning_count = 0
    
    def format_all(self) -> str:
        """Format all diagnostics for display."""
        if not self._diagnostics:
            return ""
        
        lines = [d.format() for d in self._diagnostics]
        
        # Summary
        summary_parts = []
        if self._error_count:
            summary_parts.append(Color.bold(Color.red(f"{self._error_count} error(s)")))
        if self._warning_count:
            summary_parts.append(Color.bold(Color.yellow(f"{self._warning_count} warning(s)")))
        
        if summary_parts:
            lines.append(" ".join(summary_parts) + " emitted")
        
        return "\n".join(lines)
    
    def raise_if_errors(self) -> None:
        """Raise a ValidationError if there are any errors."""
        if self.has_errors():
            raise ValidationError(
                f"Compilation failed with {self._error_count} error(s)",
                diagnostic=self._diagnostics[0] if self._diagnostics else None
            )
    
    def print_all(self, file=None) -> None:
        """Print all diagnostics to stderr (or specified file)."""
        import sys
        output = self.format_all()
        if output:
            print(output, file=file or sys.stderr)


# =============================================================================
# Helper Functions
# =============================================================================

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def find_similar(name: str, candidates: List[str], max_distance: int = 3) -> List[str]:
    """Find candidates similar to the given name using Levenshtein distance."""
    similar = []
    for candidate in candidates:
        distance = levenshtein_distance(name.lower(), candidate.lower())
        if distance <= max_distance:
            similar.append((distance, candidate))
    
    # Sort by distance and return just the names
    similar.sort(key=lambda x: x[0])
    return [name for _, name in similar]


def suggest_component(name: str, available: List[str]) -> Optional[str]:
    """Suggest a component name if the given one is similar to an available one."""
    similar = find_similar(name, available, max_distance=2)
    return similar[0] if similar else None
