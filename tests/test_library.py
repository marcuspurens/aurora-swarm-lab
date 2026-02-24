"""Tests for the library module (list_sources and delete_source)."""

import json


from app.queue.db import get_conn
from app.modules.library.list_sources import list_sources
from app.modules.library.delete_source import delete_source


def _insert_source(source_id: str, source_version: str, steps: dict | None = None) -> None:
    """Helper: insert a manifest and some embeddings for testing."""
    manifest = {
        "steps": steps or {
            "ingest_url": {"status": "done"},
            "chunk_text": {"status": "done"},
            "embed_chunks": {"status": "done"},
        },
    }
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO manifests (source_id, source_version, manifest_json, updated_at) "
            "VALUES (?, ?, ?, '2025-01-01T00:00:00')",
            (source_id, source_version, json.dumps(manifest)),
        )
        cur.execute(
            "INSERT INTO embeddings (doc_id, segment_id, source_id, source_version, "
            "text, text_hash, embedding, updated_at) VALUES (?, ?, ?, ?, 'test', 'abc', '[]', '2025-01-01')",
            (f"{source_id}:0", "seg0", source_id, source_version),
        )
        cur.execute(
            "INSERT INTO embeddings (doc_id, segment_id, source_id, source_version, "
            "text, text_hash, embedding, updated_at) VALUES (?, ?, ?, ?, 'test2', 'def', '[]', '2025-01-01')",
            (f"{source_id}:1", "seg1", source_id, source_version),
        )
        cur.execute(
            "INSERT INTO jobs (job_id, job_type, lane, status, source_id, source_version, "
            "attempts, created_at, updated_at) VALUES (?, 'ingest_url', 'io', 'done', ?, ?, 1, "
            "'2025-01-01', '2025-01-01')",
            (f"job-{source_id}", source_id, source_version),
        )
        conn.commit()


class TestListSources:
    """Tests for list_sources function."""

    def test_empty_db(self, db: object) -> None:
        result = list_sources()
        assert result == []

    def test_single_source(self, db: object) -> None:
        _insert_source("url:https://example.com", "v1")
        result = list_sources()
        assert len(result) == 1
        assert result[0]["source_id"] == "url:https://example.com"
        assert result[0]["embeddings"] == 2
        assert result[0]["status"] == "embeddings done"

    def test_multiple_sources(self, db: object) -> None:
        _insert_source("url:https://example.com", "v1")
        _insert_source("url:https://other.com", "v2")
        result = list_sources()
        assert len(result) == 2

    def test_partial_status(self, db: object) -> None:
        _insert_source(
            "url:https://example.com",
            "v1",
            steps={"ingest_url": {"status": "done"}},
        )
        result = list_sources()
        assert result[0]["status"] == "ingest done"


class TestDeleteSource:
    """Tests for delete_source function."""

    def test_delete_existing(self, db: object, artifact_root: object) -> None:
        _insert_source("url:https://example.com", "v1")
        # Create artifact directory
        art_dir = artifact_root / "url_https___example.com" / "v1" / "chunks"
        art_dir.mkdir(parents=True)
        (art_dir / "chunk.jsonl").write_text("test")

        result = delete_source("url:https://example.com")
        assert result["embeddings_deleted"] == 2
        assert result["jobs_deleted"] == 1
        assert result["manifests_deleted"] == 1
        assert result["artifacts_removed"] is True

        # Verify gone
        sources = list_sources()
        assert sources == []

    def test_delete_nonexistent(self, db: object, artifact_root: object) -> None:
        result = delete_source("url:https://nope.com")
        assert result["embeddings_deleted"] == 0
        assert result["jobs_deleted"] == 0
        assert result["manifests_deleted"] == 0
        assert result["artifacts_removed"] is False

    def test_delete_does_not_affect_other_sources(self, db: object, artifact_root: object) -> None:
        _insert_source("url:https://keep.com", "v1")
        _insert_source("url:https://remove.com", "v2")
        delete_source("url:https://remove.com")
        sources = list_sources()
        assert len(sources) == 1
        assert sources[0]["source_id"] == "url:https://keep.com"
