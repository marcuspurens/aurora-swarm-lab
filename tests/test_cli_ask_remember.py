from types import SimpleNamespace

from app.cli import main as cli_main
from app.modules.memory.memory_recall import recall
from app.queue.db import init_db


def test_cli_ask_explicit_remember_short_circuits_swarm(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    monkeypatch.setattr(cli_main, "route_question", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("should not route")))

    args = SimpleNamespace(
        question="remember this: my favorite shell is zsh",
        session_id=None,
        remember=False,
    )
    cli_main.cmd_ask(args)
    out = capsys.readouterr().out
    assert "Saved memory" in out

    recalled = recall("favorite shell", limit=5, memory_type="working")
    assert recalled
    assert recalled[0].get("memory_kind") == "semantic"
