"""
PySHDL Exceptions

Custom exception types for the SHDL driver.
"""


class SHDLDriverError(Exception):
    """Base exception for all SHDL driver errors."""
    pass


class CompilationError(SHDLDriverError):
    """Raised when circuit compilation fails."""
    
    def __init__(self, message: str, errors: list[str] = None):
        self.errors = errors or []
        super().__init__(message)


class SimulationError(SHDLDriverError):
    """Raised when simulation encounters an error."""
    pass


class SignalNotFoundError(SHDLDriverError):
    """Raised when accessing a non-existent signal."""
    
    def __init__(self, signal_name: str):
        self.signal_name = signal_name
        super().__init__(f"Signal '{signal_name}' not found")
