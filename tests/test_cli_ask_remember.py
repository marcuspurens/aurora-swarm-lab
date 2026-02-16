from types import SimpleNamespace

from app.cli import main as cli_main
from app.core.models import RouteOutput, SynthesizeOutput
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


def test_cli_ask_records_retrieval_feedback(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    captured = {}
    retrieve_capture = {}
    monkeypatch.setattr(
        cli_main,
        "route_question",
        lambda q: RouteOutput(intent="ask", filters={}, retrieve_top_k=2, need_strong_model=False, reason="ok"),
    )

    def fake_retrieve(question, limit=10, filters=None):
        retrieve_capture["filters"] = dict(filters or {})
        return [{"doc_id": "d1", "segment_id": "s1", "text_snippet": "x"}]

    monkeypatch.setattr(cli_main, "retrieve", fake_retrieve)
    monkeypatch.setattr(cli_main, "graph_retrieve", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli_main, "analyze", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_main, "synthesize", lambda *_args, **_kwargs: SynthesizeOutput(answer_text="ok", citations=[]))
    monkeypatch.setattr(cli_main, "record_turn_and_refresh", lambda **_kwargs: None)
    monkeypatch.setattr(
        cli_main,
        "record_retrieval_feedback",
        lambda **kwargs: captured.setdefault("feedback", kwargs),
    )

    args = SimpleNamespace(
        question="How is roadmap?",
        session_id="session-7",
        user_id="user-1",
        project_id="proj-1",
        remember=False,
    )
    cli_main.cmd_ask(args)
    assert "feedback" in captured
    assert captured["feedback"]["question"] == "How is roadmap?"
    assert captured["feedback"]["session_id"] == "session-7"
    assert retrieve_capture["filters"]["user_id"] == "user-1"
    assert retrieve_capture["filters"]["project_id"] == "proj-1"
    assert retrieve_capture["filters"]["session_id"] == "session-7"
