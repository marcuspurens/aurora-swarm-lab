import json

from app.core.manifest import upsert_manifest, get_manifest
from app.core.storage import write_artifact, read_artifact
from app.queue.db import init_db
from app.modules.publish import publish_snowflake


def test_publish_handle_job_writes_receipt(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v1"

    write_artifact(
        source_id,
        source_version,
        "enrich/doc_summary.json",
        json.dumps({"summary_short": "s", "summary_long": "l", "topics": [], "entities": []}),
    )
    chunks = [
        {
            "doc_id": source_id,
            "segment_id": "chunk_1",
            "text": "Hello",
            "topics": ["t"],
            "entities": ["e"],
            "source_refs": {"chunk_index": 1},
        }
    ]
    write_artifact(
        source_id,
        source_version,
        "enrich/chunks.jsonl",
        "\n".join(json.dumps(c, ensure_ascii=True) for c in chunks),
    )

    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "source_type": "url",
            "source_uri": "https://example.com",
            "artifacts": {
                "doc_summary": "enrich/doc_summary.json",
                "enriched_chunks": "enrich/chunks.jsonl",
            },
        },
    )

    class FakeClient:
        def execute_sql(self, sql: str) -> None:
            return None

    monkeypatch.setattr(publish_snowflake, "SnowflakeClient", lambda: FakeClient())

    publish_snowflake.handle_job({"source_id": source_id, "source_version": source_version, "lane": "io"})

    receipt = read_artifact(source_id, source_version, "publish/snowflake_receipt.json")
    assert receipt is not None
    data = json.loads(receipt)
    assert "doc_sql" in data and "segments_sql" in data

    manifest = get_manifest(source_id, source_version)
    assert manifest.get("steps", {}).get("publish_snowflake", {}).get("status") in {"done", "failed"}
