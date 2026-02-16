"""Minimal MCP-style JSON-RPC server over stdio."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from app.core.ids import make_source_id, sha256_file
from app.core.logging import configure_logging
from app.core.textnorm import normalize_identifier, normalize_user_text
from app.modules.graph.graph_retrieve import retrieve as graph_retrieve
from app.modules.retrieve.retrieve_snowflake import retrieve
from app.modules.swarm.analyze import analyze
from app.modules.swarm.route import route_question
from app.modules.swarm.synthesize import synthesize
from app.modules.intake.intake_url import compute_source_version as compute_url_version
from app.modules.intake.intake_youtube import compute_source_version as compute_youtube_version
from app.clients.youtube_client import get_video_info
from app.queue.jobs import enqueue_job
from app.queue.db import init_db, get_conn
from app.modules.memory.memory_write import write_memory
from app.modules.memory.memory_recall import recall as recall_memory
from app.modules.memory.memory_stats import get_memory_stats
from app.modules.memory.router import parse_explicit_remember, route_memory
from app.modules.memory.retrieval_feedback import record_retrieval_feedback
from app.modules.memory.context_handoff import (
    get_handoff,
    inject_session_resume_evidence,
    record_turn_and_refresh,
    start_background_checkpoint,
    stop_background_checkpoint,
)
from app.modules.voiceprint.gallery import list_voiceprints, upsert_person
from app.modules.intake.ingest_auto import extract_items, enqueue_items


TOOLS = [
    {
        "name": "ingest_url",
        "description": "Enqueue URL for ingest",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "ingest_doc",
        "description": "Enqueue document for ingest",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "ingest_youtube",
        "description": "Enqueue YouTube URL for ingest",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "ask",
        "description": "Ask question via swarm pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 2400},
                "remember": {"type": "boolean"},
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_write",
        "description": "Write memory item",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "text": {"type": "string"},
                "topics": {"type": "array"},
                "entities": {"type": "array"},
                "source_refs": {"type": "object"},
                "importance": {"type": "number"},
                "confidence": {"type": "number"},
                "expires_at": {"type": "string"},
                "pinned_until": {"type": "string"},
                "publish_long_term": {"type": "boolean"},
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "required": ["type", "text"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Recall memory items",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "type": {"type": "string"},
                "include_long_term": {"type": "boolean"},
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_stats",
        "description": "Memory observability stats",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
        },
    },
    {
        "name": "context_handoff",
        "description": "Get the latest automatic context handoff snapshot",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "status",
        "description": "Queue job status counts",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "voice_gallery_list",
        "description": "List voiceprints for voice gallery",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "voice_gallery_update",
        "description": "Update voice gallery entry with EBUCore+ fields",
        "input_schema": {
            "type": "object",
            "properties": {
                "voiceprint_id": {"type": "string"},
                "given_name": {"type": "string"},
                "family_name": {"type": "string"},
                "title": {"type": "string"},
                "role": {"type": "string"},
                "affiliation": {"type": "string"},
                "aliases": {"type": "array"},
                "tags": {"type": "array"},
                "notes": {"type": "string"},
                "person_id": {"type": "string"},
            },
            "required": ["voiceprint_id"],
        },
    },
    {
        "name": "voice_gallery_open",
        "description": "Open voice gallery UI",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ingest_auto",
        "description": "Enqueue links for ingest (auto-detect YouTube, URL, or local file paths)",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "items": {"type": "array"},
                "dedupe": {"type": "boolean"},
            },
        },
    },
    {
        "name": "intake_open",
        "description": "Open intake UI for paste-and-ingest",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _status() -> Dict[str, int]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        rows = cur.fetchall()
    return {row[0]: int(row[1]) for row in rows}


def _tool_ingest_url(args: Dict[str, Any]) -> Dict[str, Any]:
    url = str(args["url"])
    source_id = make_source_id("url", url)
    source_version = compute_url_version(url)
    job_id = enqueue_job("ingest_url", "io", source_id, source_version)
    return {"job_id": job_id, "source_id": source_id, "source_version": source_version}


def _tool_ingest_doc(args: Dict[str, Any]) -> Dict[str, Any]:
    from pathlib import Path
    path = Path(str(args["path"])).resolve()
    source_id = make_source_id("file", str(path))
    source_version = sha256_file(path)
    job_id = enqueue_job("ingest_doc", "io", source_id, source_version)
    return {"job_id": job_id, "source_id": source_id, "source_version": source_version}


def _tool_ingest_youtube(args: Dict[str, Any]) -> Dict[str, Any]:
    url = str(args["url"])
    info = get_video_info(url)
    video_id = str(info.get("id") or "unknown")
    source_id = make_source_id("youtube", video_id)
    source_version = compute_youtube_version(url)
    job_id = enqueue_job("ingest_youtube", "io", source_id, source_version)
    return {"job_id": job_id, "source_id": source_id, "source_version": source_version}


def _tool_ask(args: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"question", "remember", "user_id", "project_id", "session_id"}
    unknown = sorted(str(k) for k in args.keys() if k not in allowed)
    if unknown:
        raise ValueError(f"ask received unknown argument(s): {', '.join(unknown)}")

    question_raw = args.get("question")
    if not isinstance(question_raw, str):
        raise ValueError("ask.question must be a string")
    question = normalize_user_text(question_raw, max_len=2400)
    if not question:
        raise ValueError("ask.question must be a non-empty string")
    remember = _parse_bool(args.get("remember", False))
    scope = _parse_scope_arguments(args, error_prefix="ask")
    session_id = scope.get("session_id")
    remember_directive = parse_explicit_remember(question)
    if remember_directive and remember_directive.get("text"):
        receipt = _write_routed_ask_memory(
            memory_text=str(remember_directive.get("text") or ""),
            question=question,
            trigger="explicit_remember",
            preferred_kind=remember_directive.get("memory_kind"),
            user_id=scope.get("user_id"),
            project_id=scope.get("project_id"),
            session_id=session_id,
        )
        kind = str(receipt.get("memory_kind") or "semantic")
        superseded = int(receipt.get("superseded_count") or 0)
        extra = f" superseded={superseded}" if superseded > 0 else ""
        return {"answer_text": f"Saved memory [{kind}] id={receipt['memory_id']}.{extra}".strip(), "citations": []}

    plan = route_question(question)
    plan_filters = dict(plan.filters or {})
    plan_filters.update(scope)
    evidence = retrieve(question, limit=plan.retrieve_top_k, filters=plan_filters)
    graph_evidence = []
    try:
        graph_evidence = graph_retrieve(question, limit=plan.retrieve_top_k, hops=1)
    except Exception:
        graph_evidence = []
    combined = evidence + (graph_evidence or [])
    try:
        inject_session_resume_evidence(combined, session_id=str(session_id) if session_id else None)
    except Exception:
        pass
    need_strong = plan.need_strong_model or len(combined) < 2
    analysis = analyze(question, combined) if need_strong else None
    result = synthesize(question, combined, analysis=analysis, use_strong_model=need_strong)
    payload = result.model_dump()
    try:
        record_retrieval_feedback(
            question=question,
            evidence=combined,
            citations=payload.get("citations") or [],
            answer_text=str(payload.get("answer_text") or ""),
            user_id=scope.get("user_id"),
            project_id=scope.get("project_id"),
            session_id=session_id,
        )
    except Exception:
        pass
    try:
        record_turn_and_refresh(
            question=question,
            answer_text=str(payload.get("answer_text") or ""),
            citations=payload.get("citations") or [],
        )
    except Exception:
        pass
    if remember:
        _write_routed_ask_memory(
            memory_text=f"Q: {question}\nA: {payload.get('answer_text','')}",
            question=question,
            trigger="remember_flag",
            user_id=scope.get("user_id"),
            project_id=scope.get("project_id"),
            session_id=session_id,
        )
    return payload


def _write_routed_ask_memory(
    memory_text: str,
    question: str,
    trigger: str,
    preferred_kind: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    route = route_memory(memory_text, preferred_kind=preferred_kind)
    importance = 0.8 if str(route.get("memory_kind")) != "episodic" else 0.68
    return write_memory(
        memory_type=str(route.get("memory_type") or "working"),
        text=memory_text,
        topics=["ask", "remember"],
        entities=[],
        source_refs={"kind": "ask_memory", "trigger": trigger, "question": question},
        importance=importance,
        confidence=float(route.get("confidence") or 0.7),
        publish_long_term=False,
        memory_kind=str(route.get("memory_kind") or "semantic"),
        memory_slot=str(route.get("memory_slot") or "") or None,
        memory_value=str(route.get("memory_value") or "") or None,
        overwrite_conflicts=True,
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
    )


def _tool_memory_write(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = _parse_scope_arguments(args, error_prefix="memory_write")
    return write_memory(
        memory_type=str(args["type"]),
        text=str(args["text"]),
        topics=args.get("topics") or [],
        entities=args.get("entities") or [],
        source_refs=args.get("source_refs") or {},
        importance=args.get("importance", 0.5),
        confidence=args.get("confidence", 0.7),
        expires_at=args.get("expires_at"),
        pinned_until=args.get("pinned_until"),
        publish_long_term=bool(args.get("publish_long_term", False)),
        user_id=scope.get("user_id"),
        project_id=scope.get("project_id"),
        session_id=scope.get("session_id"),
    )


def _tool_context_handoff(_args: Dict[str, Any]) -> Dict[str, Any]:
    return get_handoff()


def _tool_memory_recall(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    scope = _parse_scope_arguments(args, error_prefix="memory_recall")
    return recall_memory(
        query=str(args["query"]),
        limit=int(args.get("limit", 10)),
        memory_type=args.get("type"),
        user_id=scope.get("user_id"),
        project_id=scope.get("project_id"),
        session_id=scope.get("session_id"),
        include_long_term=bool(args.get("include_long_term", False)),
    )


def _tool_memory_stats(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = _parse_scope_arguments(args, error_prefix="memory_stats")
    return get_memory_stats(
        user_id=scope.get("user_id"),
        project_id=scope.get("project_id"),
        session_id=scope.get("session_id"),
    )


def _tool_voice_gallery_list(_args: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list_voiceprints()


def _tool_voice_gallery_update(args: Dict[str, Any]) -> Dict[str, Any]:
    vp_id = str(args["voiceprint_id"])
    fields = {k: v for k, v in args.items() if k != "voiceprint_id"}
    return upsert_person(vp_id, fields)


def _tool_voice_gallery_open(_args: Dict[str, Any]) -> Dict[str, Any]:
    return {"resource_uri": "ui://voice-gallery"}


def _tool_ingest_auto(args: Dict[str, Any]) -> Dict[str, Any]:
    items = extract_items(
        text=str(args.get("text") or ""),
        items=args.get("items"),
        base_dir=None,
        dedupe=bool(args.get("dedupe", True)),
    )
    return {"items": enqueue_items(items)}


def _tool_intake_open(_args: Dict[str, Any]) -> Dict[str, Any]:
    return {"resource_uri": "ui://intake"}


def _parse_scope_arguments(args: Dict[str, Any], error_prefix: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key in ("user_id", "project_id", "session_id"):
        value = args.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"{error_prefix}.{key} must be a string when provided")
        normalized = normalize_identifier(value, max_len=120)
        if normalized:
            out[key] = normalized
    return out


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return False


def handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method")
    params = req.get("params") or {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "ingest_url":
            return _tool_ingest_url(args)
        if name == "ingest_doc":
            return _tool_ingest_doc(args)
        if name == "ingest_youtube":
            return _tool_ingest_youtube(args)
        if name == "ask":
            return _tool_ask(args)
        if name == "memory_write":
            return _tool_memory_write(args)
        if name == "memory_recall":
            return _tool_memory_recall(args)
        if name == "memory_stats":
            return _tool_memory_stats(args)
        if name == "context_handoff":
            return _tool_context_handoff(args)
        if name == "status":
            return _status()
        if name == "voice_gallery_list":
            return _tool_voice_gallery_list(args)
        if name == "voice_gallery_update":
            return _tool_voice_gallery_update(args)
        if name == "voice_gallery_open":
            return _tool_voice_gallery_open(args)
        if name == "ingest_auto":
            return _tool_ingest_auto(args)
        if name == "intake_open":
            return _tool_intake_open(args)
        raise ValueError(f"Unknown tool: {name}")
    if method == "resources/list":
        return {
            "resources": [
                {"uri": "ui://voice-gallery", "mime_type": "text/html"},
                {"uri": "ui://intake", "mime_type": "text/html"},
            ]
        }
    if method == "resources/get":
        uri = params.get("uri")
        if uri == "ui://voice-gallery":
            html = _voice_gallery_html()
            return {"uri": uri, "mime_type": "text/html", "content": html}
        if uri == "ui://intake":
            html = _intake_html()
            return {"uri": uri, "mime_type": "text/html", "content": html}
        raise ValueError(f"Unknown resource: {uri}")
    raise ValueError(f"Unknown method: {method}")


def _voice_gallery_html() -> str:
    # Minimal UI scaffold; editing is via voice_gallery_update tool.
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Voice Gallery</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 16px; }
    h1 { margin: 0 0 12px; }
    pre { background: #f4f4f4; padding: 12px; }
  </style>
</head>
<body>
  <h1>Voice Gallery (EBUCore+)</h1>
  <p>Use MCP tools <code>voice_gallery_list</code> and <code>voice_gallery_update</code> to view/edit entries.</p>
  <p>Example update payload:</p>
  <pre>{
  "voiceprint_id": "...",
  "given_name": "",
  "family_name": "",
  "title": "",
  "role": "",
  "affiliation": "",
  "aliases": [],
  "tags": [],
  "notes": ""
}</pre>
</body>
</html>
"""


def _intake_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Aurora Intake</title>
  <style>
    :root {
      --bg-1: #f4f1eb;
      --bg-2: #efe4d0;
      --ink: #1b1b1b;
      --muted: #5a554f;
      --accent: #1f6f5b;
      --accent-2: #d77a3d;
      --card: #fffaf0;
      --border: #e0d6c7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Gill Sans", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background: radial-gradient(1200px 600px at 10% 0%, #fff3d6 0%, transparent 60%),
                  radial-gradient(1000px 500px at 90% 20%, #f6e7d4 0%, transparent 55%),
                  linear-gradient(160deg, var(--bg-1), var(--bg-2));
      padding: 28px;
    }
    .wrap {
      max-width: 860px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
      animation: rise 0.6s ease-out;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.08);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0.4px;
    }
    p { margin: 0; color: var(--muted); }
    textarea {
      width: 100%;
      min-height: 140px;
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 12px;
      font-size: 15px;
      font-family: "Courier New", monospace;
      background: #fff;
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    button {
      border: 0;
      border-radius: 12px;
      padding: 10px 16px;
      font-weight: 600;
      cursor: pointer;
      background: var(--accent);
      color: #fff;
    }
    button.secondary {
      background: transparent;
      color: var(--accent);
      border: 1px solid var(--accent);
    }
    .status {
      margin-top: 12px;
      color: var(--muted);
      font-size: 14px;
    }
    pre {
      margin: 0;
      background: #f7efe1;
      padding: 12px;
      border-radius: 12px;
      overflow: auto;
      font-size: 13px;
    }
    .grid {
      display: grid;
      gap: 12px;
    }
    .badge {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: #f1dac5;
      color: #5a4030;
      font-size: 12px;
      margin-left: 8px;
    }
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(20, 16, 10, 0.45);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal.active { display: flex; }
    .modal-card {
      background: #fffaf0;
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px;
      width: min(420px, 100%);
      box-shadow: 0 16px 40px rgba(0,0,0,0.2);
      display: grid;
      gap: 10px;
    }
    .modal-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Paste links to ingest</h1>
      <p>YouTube links auto-transcribe. Other URLs ingest as readable text. Local file paths also work.</p>
    </div>
    <div class="card grid">
      <textarea id="input" placeholder="https://youtu.be/...&#10;https://example.com/article&#10;/Users/name/Documents/report.pdf"></textarea>
      <div class="actions">
        <button id="submit">Ingest (auto)</button>
        <button id="ask" class="secondary">Ask</button>
        <button id="clear" class="secondary">Clear</button>
      </div>
      <div class="status" id="status">Ready.</div>
    </div>
    <div class="card grid">
      <div>
        <strong>Results</strong>
        <span class="badge">ingest_auto</span>
      </div>
      <pre id="output">{}</pre>
    </div>
  </div>
  <div class="modal" id="prompt">
    <div class="modal-card">
      <strong>What do you want to do?</strong>
      <p>Choose how to process the pasted text.</p>
      <div class="modal-actions">
        <button id="prompt-ingest">Ingest (auto)</button>
        <button id="prompt-ask" class="secondary">Ask</button>
        <button id="prompt-cancel" class="secondary">Cancel</button>
      </div>
    </div>
  </div>
  <script>
    const statusEl = document.getElementById("status");
    const outputEl = document.getElementById("output");
    const inputEl = document.getElementById("input");
    const submitBtn = document.getElementById("submit");
    const askBtn = document.getElementById("ask");
    const clearBtn = document.getElementById("clear");
    const promptEl = document.getElementById("prompt");
    const promptIngest = document.getElementById("prompt-ingest");
    const promptAsk = document.getElementById("prompt-ask");
    const promptCancel = document.getElementById("prompt-cancel");

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function setOutput(data) {
      outputEl.textContent = JSON.stringify(data, null, 2);
    }

    async function callTool(name, args) {
      if (window.mcp && window.mcp.tools && window.mcp.tools.call) {
        return window.mcp.tools.call(name, args);
      }
      if (window.mcp && window.mcp.callTool) {
        return window.mcp.callTool({ name: name, arguments: args });
      }
      throw new Error("MCP tool bridge not available.");
    }

    async function doIngest() {
      const text = inputEl.value.trim();
      if (!text) {
        setStatus("Paste one or more links first.");
        return;
      }
      setStatus("Enqueuing...");
      try {
        const result = await callTool("ingest_auto", { text: text });
        setOutput(result);
        setStatus("Queued. You can close this window.");
      } catch (err) {
        setOutput({ error: String(err) });
        setStatus("Unable to call MCP tool. Use ingest_auto manually.");
      }
    }

    async function doAsk() {
      const text = inputEl.value.trim();
      if (!text) {
        setStatus("Paste a question first.");
        return;
      }
      setStatus("Asking...");
      try {
        const result = await callTool("ask", { question: text });
        setOutput(result);
        setStatus("Done.");
      } catch (err) {
        setOutput({ error: String(err) });
        setStatus("Unable to call MCP tool.");
      }
    }

    function openPrompt() {
      promptEl.classList.add("active");
    }

    function closePrompt() {
      promptEl.classList.remove("active");
    }

    inputEl.addEventListener("paste", () => {
      setTimeout(() => {
        if (inputEl.value.trim()) {
          openPrompt();
        }
      }, 0);
    });

    submitBtn.addEventListener("click", doIngest);
    askBtn.addEventListener("click", doAsk);
    promptIngest.addEventListener("click", async () => {
      closePrompt();
      await doIngest();
    });
    promptAsk.addEventListener("click", async () => {
      closePrompt();
      await doAsk();
    });
    promptCancel.addEventListener("click", closePrompt);

    clearBtn.addEventListener("click", () => {
      inputEl.value = "";
      setOutput({});
      setStatus("Cleared.");
    });
  </script>
</body>
</html>
"""


def main() -> None:
    configure_logging()
    init_db()
    background_handle = start_background_checkpoint()
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                req_id = req.get("id")
                result = handle_request(req)
                resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            except Exception as exc:
                resp = {"jsonrpc": "2.0", "id": req.get("id") if "req" in locals() else None, "error": str(exc)}
            sys.stdout.write(json.dumps(resp, ensure_ascii=True) + "\n")
            sys.stdout.flush()
    finally:
        stop_background_checkpoint(background_handle)
