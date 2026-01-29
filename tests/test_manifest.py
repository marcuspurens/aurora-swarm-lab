from app.queue.db import init_db
from app.core.manifest import upsert_manifest, get_manifest


def test_manifest_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    upsert_manifest("url:https://example.com", "v1", {"a": 1})
    data = get_manifest("url:https://example.com", "v1")
    assert data["a"] == 1
