from app.modules.graph.graph_retrieve import retrieve
from app.core.storage import write_artifact
from app.queue.db import init_db


class FakeClient:
    def __init__(self):
        self.calls = []

    def execute_query(self, sql: str):
        self.calls.append(sql)
        if "FROM ENTITIES" in sql and "ILIKE" in sql:
            return [{"entity_id": "e1", "name": "Acme", "type": "Org"}]
        if "FROM RELATIONS" in sql:
            return [{"rel_id": "r1", "subj_entity_id": "e1", "obj_entity_id": "e2", "predicate": "related_to"}]
        if "WHERE ENTITY_ID IN" in sql:
            return [{"entity_id": "e2", "name": "Beta", "type": "Org"}]
        return []


def test_graph_retrieve():
    results = retrieve("Acme", client=FakeClient(), hops=1)
    assert results[0]["entities"][0]["entity_id"] == "e1"


def test_graph_retrieve_local(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    init_db()

    source_id = "voice_gallery"
    source_version = "latest"
    write_artifact(
        source_id,
        source_version,
        "graph/entities.jsonl",
        (
            "{\"entity_id\":\"e1\",\"name\":\"Socialdemokraterna\",\"type\":\"Org\"}\n"
            "{\"entity_id\":\"e2\",\"name\":\"S\",\"type\":\"Org\"}\n"
        ),
    )
    write_artifact(
        source_id,
        source_version,
        "graph/relations.jsonl",
        "{\"rel_id\":\"r1\",\"subj_entity_id\":\"e1\",\"predicate\":\"describes\",\"obj_entity_id\":\"e2\"}\n",
    )

    results = retrieve("socialdemokr", client=None, hops=1)
    assert results[0]["entities"][0]["entity_id"] == "e1"
