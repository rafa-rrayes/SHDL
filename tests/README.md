# Test Suite for SHDL

This directory contains the comprehensive test suite for the SHDL (Simple Hardware Description Language) project.

## Test Files

- **`test_shdl.py`**: Core language tests (lexer, parser, flattener)
- **`test_shdl_comprehensive.py`**: End-to-end integration tests
- **`test_debugger.py`**: Debugger functionality tests (SHDB)
- **`test_errors.py`**: Error handling and diagnostic tests
- **`TEST_REPORT.md`**: Detailed test coverage report

## Test Circuits

The `circuits/` directory contains `.shdl` files used for testing:
- Basic gates and logic components
- Adders (half, full, 4-bit, 8-bit)
- Multiplexers and decoders
- Bitwise operations
- Generators and constants

## Running Tests

### Run all tests
```bash
uv run pytest tests/
```

### Run specific test file
```bash
uv run pytest tests/test_shdl.py
```

### Run with coverage
```bash
uv run pytest tests/ --cov=SHDL --cov-report=html
```

### Run specific test class or function
```bash
uv run pytest tests/test_shdl.py::TestLexer
uv run pytest tests/test_errors.py::TestLexerErrors::test_E0101_invalid_character
```

### Run in verbose mode
```bash
uv run pytest tests/ -v
```

### Skip slow tests
```bash
uv run pytest tests/ -m "not slow"
```

## Requirements

Tests require the following packages:
- pytest >= 8.0.0
- pytest-cov >= 5.0.0

Install with:
```bash
uv pip install -e ".[dev]"
```

## CI/CD

Tests run automatically on:
- Every push to `main`, `master`, or `develop` branches
- Every pull request
- Python versions: 3.9, 3.10, 3.11, 3.12, 3.13
- Operating systems: Ubuntu, macOS

See `.github/workflows/test.yml` for details.
