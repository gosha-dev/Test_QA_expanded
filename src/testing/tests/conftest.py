"""Shared configuration for the ammeter test suite."""
import sys
from pathlib import Path

import matplotlib
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(PROJECT_ROOT))

matplotlib.use("Agg", force=True)

@pytest.fixture(scope="session")
def project_root():
    return PROJECT_ROOT

@pytest.fixture
def base_config(project_root):
    return project_root / "config" / "config.yaml"