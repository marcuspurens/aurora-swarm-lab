"""Integration tests for the URL intake pipeline: enqueue -> ingest -> chunk -> verify."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from app.core.ids import sha256_text
from app.core.storage import read_artifact
from app.modules.chunk.chunk_text import CHUNKS_REL_PATH, handle_job as chunk_handle_job
from app.modules.intake import intake_url
from app.modules.intake.intake_url import enqueue, ingest_url
from app.queue.db import init_db


SAMPLE_HTML = "<html><body><h1>Hello</h1><p>This is a long enough paragraph for testing purposes. We need enough words to produce at least one chunk when the text goes through the chunking pipeline.</p></body></html>"
SAMPLE_TEXT = "Hello This is a long enough paragraph for testing purposes. We need enough words to produce at least one chunk when the text goes through the chunking pipeline."


def _setup_env(tmp_path, monkeypatch):
    """Common setup: SQLite DB + artifact root + disable summaries."""
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("CHUNK_SUMMARIES_ENABLED", "0")
    init_db()


def test_full_url_pipeline_produces_chunks(tmp_path, monkeypatch):
    """Verify: enqueue -> ingest_url -> chunk_text -> chunks.jsonl with text_to_embed."""
    _setup_env(tmp_path, monkeypatch)

    url = "https://example.com/article"
    monkeypatch.setattr(intake_url, "scrape", lambda _url: SAMPLE_HTML)

    source_id = "url:" + url
    source_version = sha256_text(SAMPLE_TEXT)

    manifest = ingest_url(url, source_id, source_version)
    assert manifest["source_id"] == source_id
    assert manifest["artifacts"]["canonical_text"] == "text/canonical.txt"

    # Now run chunk_text on the same source
    chunk_job = {
        "source_id": source_id,
        "source_version": source_version,
        "lane": "oss20b",
    }
    chunk_handle_job(chunk_job)

    # Verify chunks.jsonl exists and has text_to_embed
    raw = read_artifact(source_id, source_version, CHUNKS_REL_PATH)
    assert raw is not None
    lines = [line for line in raw.strip().split("\n") if line.strip()]
    assert len(lines) >= 1
    first_chunk = json.loads(lines[0])
    assert "text_to_embed" in first_chunk
    assert len(first_chunk["text_to_embed"]) > 0


def test_enqueue_rejects_invalid_url():
    """enqueue() should raise ValueError for invalid URLs."""
    with pytest.raises(ValueError, match="Invalid URL"):
        enqueue("not-a-url")

    with pytest.raises(ValueError, match="Invalid URL"):
        enqueue("")

    with pytest.raises(ValueError, match="Invalid URL"):
        enqueue("just-some-text")


def test_enqueue_rejects_non_http_scheme():
    """enqueue() should reject ftp:// and file:// schemes."""
    with pytest.raises(ValueError, match="Invalid URL"):
        enqueue("ftp://example.com/file.txt")

    with pytest.raises(ValueError, match="Invalid URL"):
        enqueue("file:///etc/passwd")


def test_http_client_sends_user_agent():
    """Verify that http_client.fetch_text sends a User-Agent header."""
    import urllib.request

    captured_requests = []

    def mock_urlopen(req, **kwargs):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>ok</html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        return mock_resp

    with patch.object(urllib.request, "urlopen", mock_urlopen):
        from app.clients.http_client import fetch_text
        fetch_text("https://example.com")

    assert len(captured_requests) == 1
    req = captured_requests[0]
    ua = req.get_header("User-agent")
    assert ua is not None
    assert "AuroraBot" in ua


def test_duplicate_url_is_skipped(tmp_path, monkeypatch):
    """Second ingest of same URL+version should return existing manifest without re-scraping."""
    _setup_env(tmp_path, monkeypatch)

    url = "https://example.com/article"
    monkeypatch.setattr(intake_url, "scrape", lambda _url: SAMPLE_HTML)

    source_id = "url:" + url
    source_version = sha256_text(SAMPLE_TEXT)

    # First ingest
    manifest1 = ingest_url(url, source_id, source_version)
    assert manifest1["source_id"] == source_id

    # Second ingest - scrape should NOT be called since artifacts exist
    scrape_called = []

    def tracked_scrape(_url):
        scrape_called.append(_url)
        return SAMPLE_HTML

    monkeypatch.setattr(intake_url, "scrape", tracked_scrape)
    manifest2 = ingest_url(url, source_id, source_version)

    # The second call should return the existing manifest (dedup)
    assert manifest2["source_id"] == source_id
    assert len(scrape_called) == 0
