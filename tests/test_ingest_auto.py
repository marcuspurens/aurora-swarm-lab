from pathlib import Path

from app.modules.intake.ingest_auto import enqueue_items, extract_items
from app.queue.db import init_db


def test_extract_items_supports_file_uri_and_url(tmp_path):
    doc = tmp_path / "note.txt"
    doc.write_text("hello", encoding="utf-8")
    text = f"https://example.com/story).\nfile://{doc}\n"

    out = extract_items(text=text)
    assert "https://example.com/story" in out
    assert str(doc.resolve()) in out


def test_enqueue_items_ingests_file_uri(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    doc = tmp_path / "brief.md"
    doc.write_text("content", encoding="utf-8")
    items = [f"file://{doc}"]
    out = enqueue_items(items)

    assert len(out) == 1
    assert out[0]["kind"] == "doc"
    assert out[0]["result"]["job_id"]
