"""
Pytest configuration and shared fixtures for SHDL tests.
"""

import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def test_circuits_dir() -> Path:
    """Return the path to the test circuits directory."""
    return Path(__file__).parent / "circuits"


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the path to the project root directory."""
    return Path(__file__).parent.parent
