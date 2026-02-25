from unittest.mock import patch

import pytest

from app.queue.db import init_db


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """Prevent load_dotenv() from loading .env during tests."""
    with patch("app.core.config.load_dotenv"):
        yield


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Initierad SQLite-databas för tester. Ersätter POSTGRES_DSN."""
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()
    yield db_path


@pytest.fixture
def artifact_root(tmp_path, monkeypatch):
    """Sätter ARTIFACT_ROOT till en temporär katalog under tmp_path."""
    root = tmp_path / "artifacts"
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    yield root


@pytest.fixture
def ingest_allowlist(tmp_path, monkeypatch):
    """Sätter AURORA_INGEST_PATH_ALLOWLIST till tmp_path."""
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    yield tmp_path


@pytest.fixture
def memory_enabled(monkeypatch):
    """Aktiverar MEMORY_ENABLED och RETRIEVAL_FEEDBACK_ENABLED."""
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
