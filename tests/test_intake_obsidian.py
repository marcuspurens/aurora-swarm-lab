from pathlib import Path

from app.modules.intake import intake_obsidian
from app.queue.db import init_db


def test_enqueue_obsidian_command(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    note = tmp_path / "note.md"
    note.write_text(
        """---
aurora_command: ingest_doc
path: ./dummy.txt
---
""",
        encoding="utf-8",
    )
    dummy = tmp_path / "dummy.txt"
    dummy.write_text("hi", encoding="utf-8")

    result = intake_obsidian.enqueue(str(note))
    assert result["job_type"] == "ingest_doc"


def test_enqueue_obsidian_auto_note(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    note = tmp_path / "auto.md"
    note.write_text(
        """---
aurora_auto: true
---
Some pasted text.
""",
        encoding="utf-8",
    )

    result = intake_obsidian.enqueue(str(note))
    assert result["job_type"] == "ingest_doc"
