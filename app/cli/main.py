"""Aurora Swarm Lab CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import load_settings
from app.core.ids import make_source_id, sha256_file
from app.core.logging import configure_logging
from app.core.textnorm import normalize_identifier, normalize_user_text
from app.queue.db import init_db
from app.queue.jobs import enqueue_job
from app.queue.worker import run_worker
from app.clients.snowflake_client import SnowflakeClient
from app.modules.publish.publish_snowflake import publish_documents, publish_segments
from app.modules.retrieve.retrieve_snowflake import retrieve
from app.modules.swarm.route import route_question
from app.modules.swarm.synthesize import synthesize
from app.modules.swarm.analyze import analyze
from app.modules.graph.graph_retrieve import retrieve as graph_retrieve
from app.modules.memory.memory_write import write_memory
from app.modules.memory.memory_recall import recall as recall_memory
from app.modules.memory.router import parse_explicit_remember, route_memory
from app.modules.memory.retrieval_feedback import record_retrieval_feedback
from app.modules.memory.context_handoff import (
    get_handoff,
    inject_session_resume_evidence,
    record_turn_and_refresh,
)
from app.modules.intake.intake_obsidian import watch_vault
from app.modules.initiatives.pipeline import run_pipeline_from_json
from app.modules.intake.intake_url import compute_source_version as compute_url_version
from app.modules.intake.intake_url import handle_job as handle_url_job
from app.modules.intake.intake_doc import handle_job as handle_doc_job
from app.modules.intake.intake_youtube import compute_source_version as compute_youtube_version
from app.clients.youtube_client import get_video_info
from app.modules.intake.intake_youtube import handle_job as handle_youtube_job
from app.modules.transcribe.transcribe_whisper_cli import handle_job as handle_transcribe_job
from app.modules.chunk.chunk_text import handle_job as handle_chunk_text
from app.modules.chunk.chunk_transcript import handle_job as handle_chunk_transcript
from app.modules.embeddings.embed_chunks import handle_job as handle_embed_chunks
from app.modules.embeddings.embed_voice_gallery import handle_job as handle_embed_voice_gallery
from app.modules.enrich.enrich_doc import handle_job as handle_enrich_doc
from app.modules.enrich.enrich_chunks import handle_job as handle_enrich_chunks
from app.modules.publish.publish_snowflake import handle_job as handle_publish_snowflake
from app.modules.graph.extract_entities import handle_job as handle_graph_entities
from app.modules.graph.extract_relations import handle_job as handle_graph_relations
from app.modules.graph.ontology import handle_job as handle_graph_ontology
from app.modules.graph.publish_graph import handle_job as handle_graph_publish
from app.modules.graph.graph_from_voice_gallery import handle_job as handle_graph_from_voice_gallery
from app.modules.mcp.server_main import main as mcp_server_main
from app.modules.voiceprint.diarize import handle_job as handle_diarize
from app.modules.voiceprint.enroll import handle_job as handle_voiceprint_enroll
from app.modules.voiceprint.match import handle_job as handle_voiceprint_match
from app.modules.voiceprint.review import handle_job as handle_voiceprint_review
from app.modules.audio.denoise_audio import handle_job as handle_denoise_audio


def cmd_bootstrap_postgres(_args) -> None:
    init_db()
    print("Postgres queue initialized.")


def cmd_bootstrap_snowflake(_args) -> None:
    sql_path = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_snowflake.sql"
    sql = sql_path.read_text(encoding="utf-8")
    client = SnowflakeClient()
    try:
        client.execute_sql(sql)
        print("Snowflake bootstrap executed.")
    except Exception as exc:
        print(f"Snowflake bootstrap SQL (dry-run):\n{sql}\nError: {exc}")


def cmd_enqueue_url(args) -> None:
    source_id = make_source_id("url", args.url)
    source_version = compute_url_version(args.url)
    enqueue_job("ingest_url", "io", source_id, source_version)
    print(f"Enqueued url: {args.url}")


def cmd_enqueue_doc(args) -> None:
    path = Path(args.path).resolve()
    source_id = make_source_id("file", str(path))
    source_version = sha256_file(path)
    enqueue_job("ingest_doc", "io", source_id, source_version)
    print(f"Enqueued doc: {path}")


def cmd_enqueue_youtube(args) -> None:
    info = get_video_info(args.url)
    video_id = str(info.get("id") or "unknown")
    source_id = make_source_id("youtube", video_id)
    source_version = compute_youtube_version(args.url)
    enqueue_job("ingest_youtube", "io", source_id, source_version)
    print(f"Enqueued youtube: {args.url}")


def cmd_worker(args) -> None:
    def noop_handler(job):
        print(f"[worker] handled {job['job_type']} {job['job_id']}")

    handlers = {
        "ingest_url": handle_url_job,
        "ingest_doc": handle_doc_job,
        "ingest_youtube": handle_youtube_job,
        "transcribe_whisper": handle_transcribe_job,
        "chunk_text": handle_chunk_text,
        "chunk_transcript": handle_chunk_transcript,
        "embed_chunks": handle_embed_chunks,
        "embed_voice_gallery": handle_embed_voice_gallery,
        "enrich_doc": handle_enrich_doc,
        "enrich_chunks": handle_enrich_chunks,
        "publish_snowflake": handle_publish_snowflake,
        "graph_extract_entities": handle_graph_entities,
        "graph_extract_relations": handle_graph_relations,
        "graph_ontology_seed": handle_graph_ontology,
        "graph_publish": handle_graph_publish,
        "graph_from_voice_gallery": handle_graph_from_voice_gallery,
        "diarize_audio": handle_diarize,
        "denoise_audio": handle_denoise_audio,
        "voiceprint_enroll": handle_voiceprint_enroll,
        "voiceprint_match": handle_voiceprint_match,
        "voiceprint_review": handle_voiceprint_review,
    }
    run_worker(args.lane, handlers)


def cmd_status(_args) -> None:
    from app.queue.db import get_conn

    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        else:
            cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        rows = cur.fetchall()
    print("Job status:")
    for status, count in rows:
        print(f"- {status}: {count}")


def cmd_ask(args) -> None:
    question = normalize_user_text(args.question, max_len=2400)
    if not question:
        raise SystemExit("Error: question must be a non-empty string.")
    session_id = normalize_identifier(args.session_id, max_len=120) or None
    remember_directive = parse_explicit_remember(question)
    if remember_directive and remember_directive.get("text"):
        receipt = _write_routed_ask_memory(
            memory_text=str(remember_directive.get("text") or ""),
            question=question,
            trigger="explicit_remember",
            preferred_kind=remember_directive.get("memory_kind"),
        )
        memory_kind = str(receipt.get("memory_kind") or "semantic")
        print(f"Saved memory [{memory_kind}] id={receipt['memory_id']}")
        superseded = int(receipt.get("superseded_count") or 0)
        if superseded > 0:
            print(f"Superseded {superseded} conflicting memory item(s).")
        return

    plan = route_question(question)
    evidence = retrieve(question, limit=plan.retrieve_top_k, filters=plan.filters)
    graph_evidence = []
    try:
        graph_evidence = graph_retrieve(question, limit=plan.retrieve_top_k, hops=1)
    except Exception:
        graph_evidence = []
    combined_evidence = evidence + (graph_evidence or [])
    try:
        inject_session_resume_evidence(combined_evidence, session_id=session_id)
    except Exception:
        pass
    need_strong = plan.need_strong_model or len(combined_evidence) < 2
    analysis = analyze(question, combined_evidence) if need_strong else None
    result = synthesize(question, combined_evidence, analysis=analysis, use_strong_model=need_strong)
    try:
        record_retrieval_feedback(
            question=question,
            evidence=combined_evidence,
            citations=[c.model_dump() for c in result.citations],
            answer_text=result.answer_text,
        )
    except Exception:
        pass
    try:
        record_turn_and_refresh(
            question=question,
            answer_text=result.answer_text,
            citations=[c.model_dump() for c in result.citations],
        )
    except Exception:
        pass
    if bool(getattr(args, "remember", False)):
        try:
            _write_routed_ask_memory(
                memory_text=f"Q: {question}\nA: {result.answer_text}",
                question=question,
                trigger="remember_flag",
            )
        except Exception:
            pass
    print(result.answer_text)
    if result.citations:
        print("Citations:")
        for c in result.citations:
            print(f"- {c.doc_id}:{c.segment_id}")


def _write_routed_ask_memory(
    memory_text: str,
    question: str,
    trigger: str,
    preferred_kind: object = None,
) -> dict:
    route = route_memory(memory_text, preferred_kind=str(preferred_kind or "") or None)
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
    )


def main() -> int:
    configure_logging()
    settings = load_settings()

    parser = argparse.ArgumentParser(prog="aurora")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("bootstrap-postgres")
    sub.add_parser("bootstrap-snowflake")

    p_url = sub.add_parser("enqueue-url")
    p_url.add_argument("url")

    p_doc = sub.add_parser("enqueue-doc")
    p_doc.add_argument("path")

    p_yt = sub.add_parser("enqueue-youtube")
    p_yt.add_argument("url")

    p_worker = sub.add_parser("worker")
    p_worker.add_argument("--lane", required=True)

    sub.add_parser("status")

    p_ask = sub.add_parser("ask")
    p_ask.add_argument("question")
    p_ask.add_argument("--session-id", default=None)
    p_ask.add_argument("--remember", action="store_true")

    p_mem_write = sub.add_parser("memory-write")
    p_mem_write.add_argument("--type", required=True, dest="memory_type")
    p_mem_write.add_argument("--text", required=True)
    p_mem_write.add_argument("--topic", action="append", default=[])
    p_mem_write.add_argument("--entity", action="append", default=[])
    p_mem_write.add_argument("--source-refs", default="{}")
    p_mem_write.add_argument("--importance", type=float, default=0.5)
    p_mem_write.add_argument("--confidence", type=float, default=0.7)
    p_mem_write.add_argument("--expires-at", default=None)
    p_mem_write.add_argument("--pinned-until", default=None)
    p_mem_write.add_argument("--publish-long-term", action="store_true")

    p_mem_recall = sub.add_parser("memory-recall")
    p_mem_recall.add_argument("--query", required=True)
    p_mem_recall.add_argument("--type", dest="memory_type")
    p_mem_recall.add_argument("--limit", type=int, default=10)
    p_mem_recall.add_argument("--include-long-term", action="store_true")

    sub.add_parser("context-handoff")

    sub.add_parser("obsidian-watch")

    p_initiatives = sub.add_parser("score-initiatives")
    p_initiatives.add_argument("--input", required=True, help="Path to JSON list of initiatives")

    sub.add_parser("mcp-server")

    args = parser.parse_args()

    if args.cmd == "bootstrap-postgres":
        cmd_bootstrap_postgres(args)
    elif args.cmd == "bootstrap-snowflake":
        cmd_bootstrap_snowflake(args)
    elif args.cmd == "enqueue-url":
        cmd_enqueue_url(args)
    elif args.cmd == "enqueue-doc":
        cmd_enqueue_doc(args)
    elif args.cmd == "enqueue-youtube":
        cmd_enqueue_youtube(args)
    elif args.cmd == "worker":
        cmd_worker(args)
    elif args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "ask":
        cmd_ask(args)
    elif args.cmd == "memory-write":
        source_refs = {}
        try:
            import json as _json
            source_refs = _json.loads(args.source_refs)
        except Exception:
            source_refs = {}
        receipt = write_memory(
            memory_type=args.memory_type,
            text=args.text,
            topics=args.topic,
            entities=args.entity,
            source_refs=source_refs,
            importance=args.importance,
            confidence=args.confidence,
            expires_at=args.expires_at,
            pinned_until=args.pinned_until,
            publish_long_term=args.publish_long_term,
        )
        print(f"memory_id={receipt['memory_id']} published={receipt['published']} error={receipt['error']}")
    elif args.cmd == "memory-recall":
        results = recall_memory(
            query=args.query,
            limit=args.limit,
            memory_type=args.memory_type,
            include_long_term=args.include_long_term,
        )
        for item in results:
            print(f"- {item['memory_id']} [{item['memory_type']}] {item['text']}")
    elif args.cmd == "context-handoff":
        handoff = get_handoff()
        print(handoff["text"])
    elif args.cmd == "obsidian-watch":
        watch_vault()
    elif args.cmd == "score-initiatives":
        result = run_pipeline_from_json(args.input)
        print(f"scored={len(result['scores'])} published={result['receipt'].get('error') is None}")
    elif args.cmd == "mcp-server":
        mcp_server_main()
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
