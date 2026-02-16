import json

from app.cli import main as cli_main
from app.modules.memory.memory_write import write_memory
from app.queue.db import init_db


def test_cli_memory_stats_outputs_json(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    write_memory(
        memory_type="working",
        text="cli stats sample",
        publish_long_term=False,
        user_id="user-1",
        project_id="proj-1",
        session_id="sess-1",
    )

    monkeypatch.setattr(
        "sys.argv",
        ["aurora", "memory-stats", "--user-id", "user-1", "--project-id", "proj-1", "--session-id", "sess-1"],
    )
    rc = cli_main.main()
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["totals"]["memory_items"] == 1
    assert payload["scope"]["user_id"] == "user-1"


def test_cli_memory_maintain_outputs_json(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    write_memory(
        memory_type="working",
        text="expired memory",
        publish_long_term=False,
        expires_at="2000-01-01T00:00:00+00:00",
        user_id="user-1",
        project_id="proj-1",
        session_id="sess-1",
    )

    monkeypatch.setattr(
        "sys.argv",
        ["aurora", "memory-maintain", "--user-id", "user-1", "--project-id", "proj-1", "--session-id", "sess-1"],
    )
    rc = cli_main.main()
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert int(payload["deleted_total"]) == 1
