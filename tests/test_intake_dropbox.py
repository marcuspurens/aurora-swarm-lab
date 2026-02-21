from pathlib import Path

from app.modules.intake.intake_dropbox import configured_dropbox_roots, enqueue_file_if_needed, scan_dropboxes_once
from app.queue.db import get_conn, init_db


def test_configured_dropbox_roots_parses_list(tmp_path, monkeypatch):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir(parents=True, exist_ok=True)
    second.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AURORA_DROPBOX_PATHS", f"{first}, {second}")

    roots = configured_dropbox_roots()
    assert roots == [first.resolve(), second.resolve()]


def test_enqueue_file_if_needed_dedupes_pending_jobs(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    doc = tmp_path / "doc.md"
    doc.write_text("hello", encoding="utf-8")

    first = enqueue_file_if_needed(doc)
    second = enqueue_file_if_needed(doc)

    assert first["status"] == "queued"
    assert second["status"] == "skipped"
    assert second["reason"] == "already_queued"


def test_enqueue_file_if_needed_skips_manifested_version(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    doc = tmp_path / "doc.md"
    doc.write_text("hello", encoding="utf-8")

    first = enqueue_file_if_needed(doc)
    assert first["status"] == "queued"

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO manifests (source_id, source_version, manifest_json, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (first["source_id"], first["source_version"], "{}"),
        )
        conn.commit()

    second = enqueue_file_if_needed(doc)
    assert second["status"] == "skipped"
    assert second["reason"] == "already_manifested"


def test_scan_dropboxes_once_enqueues_files(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    root = tmp_path / "dropbox"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")

    summary = scan_dropboxes_once(roots=[root], recursive=False)
    assert summary["queued"] == 2
