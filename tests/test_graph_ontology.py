from app.modules.graph import ontology
from app.queue.db import init_db
from app.core.storage import read_artifact
from app.core.manifest import upsert_manifest


def test_graph_ontology_seed(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v1"
    upsert_manifest(source_id, source_version, {"source_id": source_id, "source_version": source_version})

    ontology.handle_job({"source_id": source_id, "source_version": source_version})
    text = read_artifact(source_id, source_version, "graph/ontology.json")
    assert text is not None
