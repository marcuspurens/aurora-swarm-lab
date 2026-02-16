import pytest

from app.core.models import RouteOutput, SynthesizeOutput
from app.modules.mcp import server_main
from app.modules.memory.memory_recall import recall
from app.queue.db import init_db


def test_mcp_tools_list(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    resp = server_main.handle_request({"method": "tools/list", "params": {}})
    assert "tools" in resp
    ask_tool = next((tool for tool in resp["tools"] if tool.get("name") == "ask"), {})
    memory_stats_tool = next((tool for tool in resp["tools"] if tool.get("name") == "memory_stats"), {})
    properties = ask_tool.get("input_schema", {}).get("properties", {})
    assert "session_id" in properties
    assert "user_id" in properties
    assert "project_id" in properties
    assert memory_stats_tool.get("name") == "memory_stats"
    assert properties["question"]["minLength"] == 1
    assert properties["question"]["maxLength"] == 2400
    assert properties["session_id"]["maxLength"] == 120


def test_mcp_memory_write_and_recall(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    write_resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "memory_write", "arguments": {"type": "working", "text": "hello"}},
        }
    )
    assert write_resp["memory_id"]

    recall_resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "memory_recall", "arguments": {"query": "hello"}},
        }
    )
    assert len(recall_resp) == 1


def test_mcp_memory_stats(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "memory_write",
                "arguments": {
                    "type": "working",
                    "text": "hello stats",
                    "user_id": "user-1",
                    "project_id": "proj-1",
                    "session_id": "sess-1",
                },
            },
        }
    )
    stats_resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "memory_stats",
                "arguments": {"user_id": "user-1", "project_id": "proj-1", "session_id": "sess-1"},
            },
        }
    )
    assert stats_resp["totals"]["memory_items"] == 1
    assert "supersede_rate" in stats_resp["supersede"]
    assert "hit_rate" in stats_resp["retrieval_feedback"]


def test_mcp_ingest_doc(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    doc = tmp_path / "doc.txt"
    doc.write_text("hi", encoding="utf-8")

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "ingest_doc", "arguments": {"path": str(doc)}},
        }
    )
    assert resp["job_id"]


def test_mcp_voice_gallery_tools(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    init_db()

    resp = server_main.handle_request({"method": "tools/call", "params": {"name": "voice_gallery_list", "arguments": {}}})
    assert isinstance(resp, list)

    update = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "voice_gallery_update", "arguments": {"voiceprint_id": "vp1", "given_name": "Anna"}},
        }
    )
    assert update["voiceprint_id"] == "vp1"


def test_mcp_ingest_auto_doc(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "ingest_auto", "arguments": {"text": str(doc)}},
        }
    )
    assert resp["items"][0]["result"]["job_id"]


def test_mcp_context_handoff(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    init_db()

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "context_handoff", "arguments": {}},
        }
    )
    assert "path" in resp
    assert "Aurora Auto Handoff" in resp["text"]


def test_mcp_ask_rejects_empty_question():
    with pytest.raises(ValueError, match="non-empty string"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"question": "   "}},
            }
        )


def test_mcp_ask_rejects_non_string_question():
    with pytest.raises(ValueError, match="must be a string"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"question": 123}},
            }
        )


def test_mcp_ask_rejects_non_string_session_id():
    with pytest.raises(ValueError, match="session_id must be a string"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"question": "ok", "session_id": 7}},
            }
        )


def test_mcp_ask_rejects_unknown_argument():
    with pytest.raises(ValueError, match="unknown argument"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"question": "ok", "extra": "x"}},
            }
        )


def test_mcp_ask_normalizes_nfkc_question(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    captured = {}

    monkeypatch.setattr(
        server_main,
        "route_question",
        lambda q: RouteOutput(intent="ask", filters={}, retrieve_top_k=2, need_strong_model=False, reason="ok"),
    )
    monkeypatch.setattr(
        server_main,
        "retrieve",
        lambda question, limit=10, filters=None: [
            {"doc_id": "d1", "segment_id": "s1", "text_snippet": "a"},
            {"doc_id": "d2", "segment_id": "s2", "text_snippet": "b"},
        ],
    )
    monkeypatch.setattr(server_main, "graph_retrieve", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(server_main, "record_turn_and_refresh", lambda **_kwargs: None)

    def fake_synthesize(question, evidence, analysis=None, use_strong_model=False):
        captured["question"] = question
        return SynthesizeOutput(answer_text="ok", citations=[])

    monkeypatch.setattr(server_main, "synthesize", fake_synthesize)
    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"question": "ＡＢＣ　１２３\n\n\tｘ"}},
        }
    )
    assert resp["answer_text"] == "ok"
    assert captured["question"] == "ABC 123 x"


def test_mcp_ask_explicit_remember_short_circuits_swarm(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    monkeypatch.setattr(server_main, "route_question", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("should not route")))

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"question": "remember this: my favorite color is blue"}},
        }
    )
    assert "Saved memory" in resp["answer_text"]

    recalled = recall("favorite color", limit=5, memory_type="working")
    assert recalled
    assert recalled[0].get("memory_kind") == "semantic"


def test_mcp_ask_records_retrieval_feedback(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    captured = {}
    monkeypatch.setattr(
        server_main,
        "route_question",
        lambda q: RouteOutput(intent="ask", filters={}, retrieve_top_k=2, need_strong_model=False, reason="ok"),
    )
    monkeypatch.setattr(
        server_main,
        "retrieve",
        lambda question, limit=10, filters=None: [
            {"doc_id": "d1", "segment_id": "s1", "text_snippet": "a"},
            {"doc_id": "d2", "segment_id": "s2", "text_snippet": "b"},
        ],
    )
    monkeypatch.setattr(server_main, "graph_retrieve", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(server_main, "record_turn_and_refresh", lambda **_kwargs: None)
    monkeypatch.setattr(
        server_main,
        "record_retrieval_feedback",
        lambda **kwargs: captured.setdefault("feedback", kwargs),
    )
    monkeypatch.setattr(server_main, "synthesize", lambda *_args, **_kwargs: SynthesizeOutput(answer_text="ok", citations=[]))

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"question": "What's new?"}},
        }
    )
    assert resp["answer_text"] == "ok"
    assert "feedback" in captured
    assert captured["feedback"]["question"] == "What's new?"


def test_mcp_ask_passes_scope_to_retrieve_and_feedback(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    captured = {}
    monkeypatch.setattr(
        server_main,
        "route_question",
        lambda q: RouteOutput(intent="ask", filters={}, retrieve_top_k=2, need_strong_model=False, reason="ok"),
    )

    def fake_retrieve(question, limit=10, filters=None):
        captured["filters"] = dict(filters or {})
        return [{"doc_id": "d1", "segment_id": "s1", "text_snippet": "a"}]

    monkeypatch.setattr(server_main, "retrieve", fake_retrieve)
    monkeypatch.setattr(server_main, "graph_retrieve", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(server_main, "record_turn_and_refresh", lambda **_kwargs: None)
    monkeypatch.setattr(server_main, "synthesize", lambda *_args, **_kwargs: SynthesizeOutput(answer_text="ok", citations=[]))
    monkeypatch.setattr(server_main, "record_retrieval_feedback", lambda **kwargs: captured.setdefault("feedback", kwargs))

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "ask",
                "arguments": {
                    "question": "What's new?",
                    "user_id": "user-7",
                    "project_id": "proj-7",
                    "session_id": "session-7",
                },
            },
        }
    )
    assert resp["answer_text"] == "ok"
    assert captured["filters"]["user_id"] == "user-7"
    assert captured["filters"]["project_id"] == "proj-7"
    assert captured["filters"]["session_id"] == "session-7"
    assert captured["feedback"]["session_id"] == "session-7"
