import json

from app.core.manifest import upsert_manifest, get_manifest
from app.core.storage import write_artifact, read_artifact
from app.queue.db import init_db
from app.modules.enrich import enrich_doc
from app.core.models import EnrichDocOutput


def test_enrich_doc_handle_job(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "file:/tmp/a.txt"
    source_version = "v1"
    write_artifact(source_id, source_version, "text/canonical.txt", "Hello world")
    upsert_manifest(
        source_id,
        source_version,
        {"source_id": source_id, "source_version": source_version, "artifacts": {"canonical_text": "text/canonical.txt"}},
    )

    def fake_generate(text):
        return EnrichDocOutput(summary_short="s", summary_long="l", topics=["t"], entities=["e"])

    monkeypatch.setattr(enrich_doc, "enrich", fake_generate)

    enrich_doc.handle_job({"source_id": source_id, "source_version": source_version})

    payload = read_artifact(source_id, source_version, "enrich/doc_summary.json")
    assert payload is not None
    data = json.loads(payload)
    assert data["summary_short"] == "s"

    manifest = get_manifest(source_id, source_version)
    assert manifest.get("steps", {}).get("enrich_doc", {}).get("status") == "done"
