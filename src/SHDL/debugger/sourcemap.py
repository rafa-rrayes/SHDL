"""
Source Mapping

Maps between SHDL source locations and flattened gates.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .debuginfo import DebugInfo, GateInfo


@dataclass
class SourceLocation:
    """A location in source code."""
    file: str
    line: int
    column: int = 0
    
    def __str__(self) -> str:
        if self.column:
            return f"{self.file}:{self.line}:{self.column}"
        return f"{self.file}:{self.line}"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SourceLocation):
            return False
        return self.file == other.file and self.line == other.line
    
    def __hash__(self) -> int:
        return hash((self.file, self.line))


@dataclass  
class SourceLine:
    """A line of source code with metadata."""
    file: str
    line_number: int
    content: str
    gates: list[str]  # Gate names that originated from this line
    
    @property
    def has_gates(self) -> bool:
        return len(self.gates) > 0


class SourceMap:
    """
    Bidirectional mapping between source locations and gates.
    
    Provides:
    - Source location for a gate
    - Gates originating from a source line
    - Source file reading and caching
    """
    
    def __init__(self, debug_info: DebugInfo, source_paths: Optional[list[Path]] = None):
        self.debug_info = debug_info
        self.source_paths = source_paths or []
        
        # Cache for source file contents
        self._source_cache: dict[str, list[str]] = {}
        
        # Build reverse mapping: gate -> source location
        self._gate_to_source: dict[str, SourceLocation] = {}
        for gate_name, gate_info in debug_info.gates.items():
            if gate_info.source:
                self._gate_to_source[gate_name] = SourceLocation(
                    file=gate_info.source.file,
                    line=gate_info.source.line,
                    column=gate_info.source.column,
                )
    
    def get_source_location(self, gate_name: str) -> Optional[SourceLocation]:
        """Get the source location for a gate."""
        return self._gate_to_source.get(gate_name)
    
    def get_gates_at_location(self, file: str, line: int) -> list[str]:
        """Get all gates that originated from a source line."""
        return self.debug_info.get_gates_at_line(file, line)
    
    def get_gates_in_file(self, file: str) -> dict[int, list[str]]:
        """Get all gates organized by line number for a file."""
        return self.debug_info.source_map.get(file, {})
    
    def get_source_line(self, file: str, line: int) -> Optional[SourceLine]:
        """
        Get a source line with its content and associated gates.
        """
        content = self._read_line(file, line)
        if content is None:
            return None
        
        gates = self.get_gates_at_location(file, line)
        return SourceLine(
            file=file,
            line_number=line,
            content=content,
            gates=gates,
        )
    
    def get_source_context(
        self, 
        file: str, 
        line: int, 
        context_lines: int = 3
    ) -> list[SourceLine]:
        """
        Get source lines around a location with context.
        
        Args:
            file: Source file path
            line: Center line number
            context_lines: Number of lines before and after
        
        Returns:
            List of SourceLine objects
        """
        lines = self._load_source(file)
        if not lines:
            return []
        
        start = max(1, line - context_lines)
        end = min(len(lines), line + context_lines)
        
        result = []
        for i in range(start, end + 1):
            content = lines[i - 1] if i <= len(lines) else ""
            gates = self.get_gates_at_location(file, i)
            result.append(SourceLine(
                file=file,
                line_number=i,
                content=content,
                gates=gates,
            ))
        
        return result
    
    def format_source_context(
        self,
        file: str,
        line: int,
        context_lines: int = 3,
        show_gates: bool = True,
    ) -> str:
        """
        Format source context for display.
        
        Returns a formatted string with line numbers and gate annotations.
        """
        source_lines = self.get_source_context(file, line, context_lines)
        if not source_lines:
            return f"  (source not available: {file})"
        
        # Calculate line number width
        max_line = max(sl.line_number for sl in source_lines)
        line_width = len(str(max_line))
        
        lines = []
        for sl in source_lines:
            marker = ">" if sl.line_number == line else " "
            line_num = str(sl.line_number).rjust(line_width)
            content = sl.content.rstrip()
            
            line_str = f"{marker} {line_num} | {content}"
            lines.append(line_str)
            
            # Add gate annotations
            if show_gates and sl.gates:
                gate_str = ", ".join(sl.gates[:5])
                if len(sl.gates) > 5:
                    gate_str += f", ... (+{len(sl.gates) - 5} more)"
                indent = " " * (line_width + 4)
                lines.append(f"{indent}  └─ gates: {gate_str}")
        
        return "\n".join(lines)
    
    def _load_source(self, file: str) -> list[str]:
        """Load and cache a source file."""
        if file in self._source_cache:
            return self._source_cache[file]
        
        # Try to find the file
        file_path = self._find_source_file(file)
        if not file_path:
            return []
        
        try:
            with open(file_path) as f:
                lines = f.readlines()
            self._source_cache[file] = lines
            return lines
        except Exception:
            return []
    
    def _read_line(self, file: str, line: int) -> Optional[str]:
        """Read a specific line from a source file."""
        lines = self._load_source(file)
        if 0 < line <= len(lines):
            return lines[line - 1].rstrip()
        return None
    
    def _find_source_file(self, file: str) -> Optional[Path]:
        """Find a source file in the search paths."""
        # Try as absolute path first
        path = Path(file)
        if path.exists():
            return path
        
        # Try relative to search paths
        for search_path in self.source_paths:
            candidate = search_path / file
            if candidate.exists():
                return candidate
        
        # Try just the filename in search paths
        filename = Path(file).name
        for search_path in self.source_paths:
            candidate = search_path / filename
            if candidate.exists():
                return candidate
        
        return None
    
    def get_all_source_files(self) -> list[str]:
        """Get list of all source files referenced in debug info."""
        files = set()
        files.add(self.debug_info.source_file)
        
        for gate_info in self.debug_info.gates.values():
            if gate_info.source:
                files.add(gate_info.source.file)
        
        return sorted(files)
