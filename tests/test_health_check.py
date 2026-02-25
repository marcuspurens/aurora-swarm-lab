"""Tests for scripts/health_check.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HEALTH_PATH = PROJECT_ROOT / "data" / "health.json"


@pytest.fixture(scope="module", autouse=True)
def _run_health_check() -> None:
    """Run the health-check script once before all tests in this module."""
    result = subprocess.run(
        [sys.executable, "scripts/health_check.py"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"health_check.py failed:\n{result.stderr}"


def test_health_check_runs_without_error() -> None:
    """Script exits with code 0 (already verified by fixture)."""
    assert HEALTH_PATH.exists(), "data/health.json not found after running script"


def test_health_json_has_required_keys() -> None:
    """health.json contains the expected top-level keys."""
    data = json.loads(HEALTH_PATH.read_text())
    for key in ("timestamp", "status", "tests", "components"):
        assert key in data, f"Missing key: {key}"


def test_status_value_is_valid() -> None:
    """status must be ok, degraded, or error."""
    data = json.loads(HEALTH_PATH.read_text())
    assert data["status"] in ("ok", "degraded", "error")


def test_components_are_dicts() -> None:
    """Each component value should be a dict with an 'ok' key."""
    data = json.loads(HEALTH_PATH.read_text())
    for name, info in data["components"].items():
        assert isinstance(info, dict), f"{name} is not a dict"
        assert "ok" in info, f"{name} missing 'ok' key"


def test_data_dir_present() -> None:
    """data_dir stats should be present."""
    data = json.loads(HEALTH_PATH.read_text())
    assert "data_dir" in data
    dd = data["data_dir"]
    assert "manifests_count" in dd or "sources_count" in dd
