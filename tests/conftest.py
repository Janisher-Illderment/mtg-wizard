"""Shared pytest fixtures and path setup for the wizard test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the src/ layout importable without installing the package.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture()
def fixtures_dir() -> Path:
    """Path to the tests/fixtures directory."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def sample_collection_csv(fixtures_dir: Path) -> Path:
    """Path to the bundled sample ManaBox CSV fixture."""
    return fixtures_dir / "sample_collection.csv"
