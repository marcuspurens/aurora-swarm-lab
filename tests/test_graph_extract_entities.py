from app.modules.graph import extract_entities
from app.queue.db import init_db
from app.core.storage import write_artifact, read_artifact
from app.core.manifest import upsert_manifest
from app.core.models import GraphEntitiesOutput, GraphEntity, GraphClaim


def test_graph_extract_entities(tmp_path, monkeypatch):
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
        "enrich/chunks.jsonl",
        "{\"doc_id\": \"x\", \"segment_id\": \"chunk_1\", \"text\": \"hello\"}\n",
    )
    upsert_manifest(
        source_id,
        source_version,
        {"source_id": source_id, "source_version": source_version, "artifacts": {"enriched_chunks": "enrich/chunks.jsonl"}},
    )

    def fake_generate(prompt, model, schema):
        return GraphEntitiesOutput(
            entities=[GraphEntity(entity_id="e1", name="Acme", type="Org")],
            claims=[GraphClaim(claim_id="c1", claim_text="Acme exists", doc_id="x", segment_id="chunk_1")],
        )

    monkeypatch.setattr(extract_entities, "generate_json", fake_generate)

    extract_entities.handle_job({"source_id": source_id, "source_version": source_version})

    ent = read_artifact(source_id, source_version, "graph/entities.jsonl")
    clm = read_artifact(source_id, source_version, "graph/claims.jsonl")
    assert ent is not None and clm is not None
