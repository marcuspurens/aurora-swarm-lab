import json

from app.modules.graph import publish_graph
from app.queue.db import init_db
from app.core.storage import write_artifact, read_artifact
from app.core.manifest import upsert_manifest


def test_graph_publish_builds_receipt(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v1"

    write_artifact(source_id, source_version, "graph/entities.jsonl", "{\"entity_id\":\"e1\",\"name\":\"Acme\",\"type\":\"Org\"}\n")
    write_artifact(source_id, source_version, "graph/relations.jsonl", "{\"rel_id\":\"r1\",\"subj_entity_id\":\"e1\",\"predicate\":\"related_to\",\"obj_entity_id\":\"e1\",\"doc_id\":\"d\",\"segment_id\":\"s\"}\n")
    write_artifact(source_id, source_version, "graph/claims.jsonl", "{\"claim_id\":\"c1\",\"claim_text\":\"Acme exists\",\"doc_id\":\"d\",\"segment_id\":\"s\"}\n")
    write_artifact(source_id, source_version, "graph/ontology.json", json.dumps([{"predicate": "mentions", "domain_type": "Document", "range_type": "Entity", "description": "x"}]))

    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {
                "graph_entities": "graph/entities.jsonl",
                "graph_relations": "graph/relations.jsonl",
                "graph_claims": "graph/claims.jsonl",
                "ontology": "graph/ontology.json",
            },
        },
    )

    class FakeClient:
        def execute_sql(self, sql: str) -> None:
            return None

    monkeypatch.setattr(publish_graph, "SnowflakeClient", lambda: FakeClient())

    publish_graph.handle_job({"source_id": source_id, "source_version": source_version})

    receipt = read_artifact(source_id, source_version, "graph/publish_receipt.json")
    assert receipt is not None
