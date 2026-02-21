import pytest

from app.core.models import RouteOutput, SynthesizeOutput
from app.core.manifest import get_manifest
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
    memory_maintain_tool = next((tool for tool in resp["tools"] if tool.get("name") == "memory_maintain"), {})
    dashboard_open_tool = next((tool for tool in resp["tools"] if tool.get("name") == "dashboard_open"), {})
    ingest_auto_tool = next((tool for tool in resp["tools"] if tool.get("name") == "ingest_auto"), {})
    properties = ask_tool.get("input_schema", {}).get("properties", {})
    memory_write_properties = next(
        (tool for tool in resp["tools"] if tool.get("name") == "memory_write"),
        {},
    ).get("input_schema", {}).get("properties", {})
    assert "session_id" in properties
    assert "user_id" in properties
    assert "project_id" in properties
    assert "intent" in properties
    assert "intent" in memory_write_properties
    assert memory_stats_tool.get("name") == "memory_stats"
    assert memory_maintain_tool.get("name") == "memory_maintain"
    assert dashboard_open_tool.get("name") == "dashboard_open"
    assert properties["question"]["minLength"] == 1
    assert properties["question"]["maxLength"] == 2400
    assert properties["session_id"]["maxLength"] == 120
    assert "inputSchema" in ask_tool
    ingest_props = ingest_auto_tool.get("input_schema", {}).get("properties", {})
    assert "tags" in ingest_props
    assert "context" in ingest_props
    assert "speaker" in ingest_props
    assert "organization" in ingest_props
    assert "event_date" in ingest_props
    assert "source_metadata" in ingest_props


def test_mcp_initialize_response():
    resp = server_main.handle_request({"method": "initialize", "params": {}})
    assert resp["protocolVersion"]
    assert "capabilities" in resp
    assert resp["serverInfo"]["name"] == "aurora-swarm-lab"


def test_mcp_memory_write_and_recall(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    write_resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "memory_write", "arguments": {"type": "working", "text": "hello", "intent": "write"}},
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
                    "intent": "write",
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


def test_mcp_memory_maintain(tmp_path, monkeypatch):
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
                    "text": "expired",
                    "intent": "write",
                    "expires_at": "2000-01-01T00:00:00+00:00",
                    "user_id": "user-1",
                    "project_id": "proj-1",
                    "session_id": "sess-1",
                },
            },
        }
    )

    maintain_resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "memory_maintain",
                "arguments": {"user_id": "user-1", "project_id": "proj-1", "session_id": "sess-1"},
            },
        }
    )
    assert maintain_resp["enqueued"] is False
    assert int(maintain_resp["deleted_total"]) == 1


def test_mcp_memory_maintain_enqueue(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "memory_maintain", "arguments": {"enqueue": True}},
        }
    )
    assert resp["enqueued"] is True
    assert resp["job_id"]


def test_mcp_ingest_doc(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
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
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "ingest_auto",
                "arguments": {"text": str(doc), "tags": ["alpha", "beta"], "context": "Known project note"},
            },
        }
    )
    result = resp["items"][0]["result"]
    assert result["job_id"]
    manifest = get_manifest(result["source_id"], result["source_version"])
    assert manifest is not None
    intake = ((manifest.get("metadata") or {}).get("intake") or {})
    assert intake.get("tags") == ["alpha", "beta"]
    assert intake.get("context") == "Known project note"


def test_mcp_ingest_auto_doc_with_structured_metadata(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST", str(tmp_path))
    init_db()

    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "ingest_auto",
                "arguments": {
                    "text": str(doc),
                    "speaker": "Philipp Roth",
                    "organization": "ORF",
                    "event_date": "2025-06-24",
                    "source_metadata": {"organization_uri": "https://en.wikipedia.org/wiki/ORF_(broadcaster)"},
                },
            },
        }
    )
    result = resp["items"][0]["result"]
    manifest = get_manifest(result["source_id"], result["source_version"])
    assert manifest is not None
    metadata = manifest.get("metadata") or {}
    intake = metadata.get("intake") or {}
    source_metadata = intake.get("source_metadata") or {}
    assert source_metadata.get("speaker") == "Philipp Roth"
    assert source_metadata.get("organization") == "ORF"
    assert source_metadata.get("event_date") == "2025-06-24"

    ebucore_plus = metadata.get("ebucore_plus") or {}
    assert (ebucore_plus.get("speaker") or {}).get("name") == "Philipp Roth"
    assert (ebucore_plus.get("organization") or {}).get("name") == "ORF"


def test_mcp_obsidian_tools_list_and_enqueue(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "Aurora Inbox" / "daily.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        """---
aurora_auto: true
---
Some pasted note content.
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    init_db()

    status_resp = server_main.handle_request(
        {"method": "tools/call", "params": {"name": "obsidian_watch_status", "arguments": {}}}
    )
    assert status_resp["configured"] is True
    assert status_resp["vault_exists"] is True

    list_resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "obsidian_list_notes", "arguments": {"folder": "Aurora Inbox", "limit": 10}},
        }
    )
    assert list_resp["count"] >= 1
    assert any(item["path"] == "Aurora Inbox/daily.md" for item in list_resp["notes"])

    enqueue_resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "obsidian_enqueue_note", "arguments": {"note_path": "Aurora Inbox/daily.md"}},
        }
    )
    assert enqueue_resp["note_rel_path"] == "Aurora Inbox/daily.md"
    assert enqueue_resp["result"]["job_type"] == "ingest_doc"


def test_mcp_obsidian_enqueue_rejects_path_outside_vault(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    outside_note = tmp_path / "outside.md"
    outside_note.write_text("# outside", encoding="utf-8")

    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    init_db()

    with pytest.raises(PermissionError, match="outside configured Obsidian vault"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "obsidian_enqueue_note", "arguments": {"note_path": str(outside_note)}},
            }
        )


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


def test_mcp_intake_ui_has_action_buttons_and_explanations(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    resp = server_main.handle_request(
        {
            "method": "resources/get",
            "params": {"uri": "ui://intake"},
        }
    )
    html = str(resp.get("content") or "")
    assert "Importera" in html
    assert "Fraga" in html
    assert "Kom ihag" in html
    assert "TODO" in html
    assert "What the buttons mean" in html
    assert ".action-btn.selected" in html
    assert "markSelected" in html


def test_mcp_dashboard_ui_resource(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    resp = server_main.handle_request(
        {
            "method": "resources/get",
            "params": {"uri": "ui://dashboard"},
        }
    )
    html = str(resp.get("content") or "")
    assert "Aurora Dashboard" in html
    assert "dashboard_timeseries" in html
    assert "dashboard_alerts" in html
    assert "dashboard_models" in html


def test_mcp_dashboard_open_tool():
    resp = server_main.handle_request({"method": "tools/call", "params": {"name": "dashboard_open", "arguments": {}}})
    assert resp["resource_uri"] == "ui://dashboard"


def test_mcp_resources_read_alias_returns_mcp_content_shape(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    resp = server_main.handle_request(
        {
            "method": "resources/read",
            "params": {"uri": "ui://intake"},
        }
    )
    contents = resp.get("contents") or []
    assert contents
    assert contents[0]["uri"] == "ui://intake"
    assert contents[0]["mimeType"] == "text/html"
    assert "<title>Aurora Intake</title>" in contents[0]["text"]


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
            "params": {
                "name": "ask",
                "arguments": {"question": "remember this: my favorite color is blue", "intent": "remember"},
            },
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


def test_mcp_ask_uses_default_scope_from_env(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("AURORA_DEFAULT_USER_ID", "default-user")
    monkeypatch.setenv("AURORA_DEFAULT_PROJECT_ID", "default-project")
    monkeypatch.setenv("AURORA_DEFAULT_SESSION_ID", "default-session")
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
                },
            },
        }
    )
    assert resp["answer_text"] == "ok"
    assert captured["filters"]["user_id"] == "default-user"
    assert captured["filters"]["project_id"] == "default-project"
    assert captured["filters"]["session_id"] == "default-session"
    assert captured["feedback"]["session_id"] == "default-session"


def test_mcp_memory_write_requires_explicit_intent(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MCP_REQUIRE_EXPLICIT_INTENT", "1")
    init_db()

    with pytest.raises(ValueError, match="memory_write.intent is required"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "memory_write", "arguments": {"type": "working", "text": "hello"}},
            }
        )


def test_mcp_ask_remember_requires_explicit_intent(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MCP_REQUIRE_EXPLICIT_INTENT", "1")
    init_db()

    with pytest.raises(ValueError, match="ask.intent is required"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"question": "remember this: project alpha uses zsh"}},
            }
        )


def test_mcp_ingest_doc_blocks_without_allowlist(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.delenv("AURORA_INGEST_PATH_ALLOWLIST", raising=False)
    monkeypatch.setenv("AURORA_INGEST_PATH_ALLOWLIST_ENFORCED", "1")
    init_db()

    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")

    with pytest.raises(PermissionError, match="allowlist"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "ingest_doc", "arguments": {"path": str(doc)}},
            }
        )


def test_mcp_tool_allowlist_by_client_filters_and_blocks(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MCP_TOOL_ALLOWLIST_BY_CLIENT", "codex=ask,memory_recall")
    init_db()

    listed = server_main.handle_request({"method": "tools/list", "params": {"client_id": "codex"}})
    names = {tool.get("name") for tool in listed["tools"]}
    assert names == {"ask", "memory_recall"}

    with pytest.raises(PermissionError, match="not allowed"):
        server_main.handle_request(
            {
                "method": "tools/call",
                "params": {"client_id": "codex", "name": "status", "arguments": {}},
            }
        )


def test_mcp_dashboard_stats_returns_progress_and_counts(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "memory_write",
                "arguments": {"type": "working", "text": "dashboard memory", "intent": "write"},
            },
        }
    )

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "dashboard_stats",
                "arguments": {"target_docs": 10, "target_vectors": 100, "target_memory": 5},
            },
        }
    )
    assert "counts" in resp
    assert "progress" in resp
    assert resp["targets"]["docs"] == 10
    assert resp["targets"]["vectors"] == 100
    assert resp["targets"]["memory"] == 5
    assert resp["counts"]["memory_total"] >= 1
    assert resp["progress"]["memory_percent"] >= 0


def test_mcp_dashboard_timeseries_returns_buckets(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {
                "name": "dashboard_timeseries",
                "arguments": {"window_hours": 6, "bucket_minutes": 30},
            },
        }
    )
    assert resp["window_hours"] == 6
    assert resp["bucket_minutes"] == 30
    assert isinstance(resp["buckets"], list)
    assert resp["buckets"]
    first = resp["buckets"][0]
    assert "docs_ingested" in first
    assert "vectors_built" in first
    assert "memory_written" in first


def test_mcp_dashboard_alerts_returns_summary_and_alerts(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "dashboard_alerts", "arguments": {"stale_running_minutes": 5, "error_window_hours": 12}},
        }
    )
    assert "summary" in resp
    assert "alerts" in resp
    assert isinstance(resp["alerts"], list)
    assert resp["alerts"]


def test_mcp_dashboard_models_returns_summary(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

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
    monkeypatch.setattr(server_main, "synthesize", lambda *_args, **_kwargs: SynthesizeOutput(answer_text="ok", citations=[]))

    server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"question": "test model stats"}},
        }
    )

    resp = server_main.handle_request(
        {
            "method": "tools/call",
            "params": {"name": "dashboard_models", "arguments": {"window_hours": 24}},
        }
    )
    assert "summary" in resp
    assert "models" in resp
    assert "codex_usage" in resp
    assert resp["summary"]["requests"] >= 0
