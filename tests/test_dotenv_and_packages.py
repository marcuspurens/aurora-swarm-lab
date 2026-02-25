"""Tests verifying that required packages can be imported and load_dotenv is called."""

from __future__ import annotations

from unittest.mock import patch


def test_import_python_dotenv():
    """python-dotenv must be importable."""
    from dotenv import load_dotenv  # noqa: F401


def test_import_yt_dlp():
    """yt-dlp must be importable."""
    import yt_dlp  # noqa: F401


def test_import_python_docx():
    """python-docx must be importable (as 'docx')."""
    import docx  # noqa: F401


def test_load_settings_calls_load_dotenv():
    """load_settings() must call load_dotenv() before reading env vars."""
    from importlib import reload
    import app.core.config as cfg
    reload(cfg)
    with patch.object(cfg, "load_dotenv") as mock_ld:
        cfg.load_settings()
        mock_ld.assert_called()
