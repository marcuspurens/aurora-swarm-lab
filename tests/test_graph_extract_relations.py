from app.modules.graph import extract_relations
from app.queue.db import init_db
from app.core.storage import write_artifact, read_artifact
from app.core.manifest import upsert_manifest
from app.core.models import GraphRelationsOutput, GraphRelation


def test_graph_extract_relations(tmp_path, monkeypatch):
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
    write_artifact(
        source_id,
        source_version,
        "graph/entities.jsonl",
        "{\"entity_id\": \"e1\", \"name\": \"Acme\", \"type\": \"Org\"}\n",
    )
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {"enriched_chunks": "enrich/chunks.jsonl", "graph_entities": "graph/entities.jsonl"},
        },
    )

    def fake_generate(prompt, model, schema):
        return GraphRelationsOutput(
            relations=[
                GraphRelation(
                    rel_id="r1",
                    subj_entity_id="e1",
                    predicate="related_to",
                    obj_entity_id="e1",
                    doc_id="x",
                    segment_id="chunk_1",
                    confidence=0.6,
                )
            ]
        )

    monkeypatch.setattr(extract_relations, "generate_json", fake_generate)

    extract_relations.handle_job({"source_id": source_id, "source_version": source_version})

    rel = read_artifact(source_id, source_version, "graph/relations.jsonl")
    assert rel is not None
