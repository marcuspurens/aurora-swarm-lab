"""Aurora Swarm Lab CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import load_settings
from app.core.ids import make_source_id, sha256_file, sha256_text
from app.core.logging import configure_logging
from app.queue.db import init_db
from app.queue.jobs import enqueue_job
from app.queue.worker import run_worker
from app.clients.snowflake_client import SnowflakeClient
from app.modules.publish.publish_snowflake import publish_documents, publish_segments
from app.modules.retrieve.retrieve_snowflake import retrieve
from app.modules.swarm.route import route_question
from app.modules.swarm.synthesize import synthesize


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
    source_version = sha256_text(args.url)
    enqueue_job("ingest_url", "io", source_id, source_version)
    print(f"Enqueued url: {args.url}")


def cmd_enqueue_doc(args) -> None:
    path = Path(args.path).resolve()
    source_id = make_source_id("file", str(path))
    source_version = sha256_file(path)
    enqueue_job("ingest_doc", "io", source_id, source_version)
    print(f"Enqueued doc: {path}")


def cmd_enqueue_youtube(args) -> None:
    source_id = make_source_id("youtube", args.url)
    source_version = sha256_text(args.url)
    enqueue_job("ingest_youtube", "transcribe", source_id, source_version)
    print(f"Enqueued youtube: {args.url}")


def cmd_worker(args) -> None:
    def noop_handler(job):
        print(f"[worker] handled {job['job_type']} {job['job_id']}")

    handlers = {
        "ingest_url": noop_handler,
        "ingest_doc": noop_handler,
        "ingest_youtube": noop_handler,
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
    plan = route_question(args.question)
    evidence = retrieve(args.question, limit=plan.retrieve_top_k)
    result = synthesize(args.question, evidence)
    print(result.answer_text)
    if result.citations:
        print("Citations:")
        for c in result.citations:
            print(f"- {c.doc_id}:{c.segment_id}")


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
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
