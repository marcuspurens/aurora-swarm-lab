from app.core.ids import sha256_text
from app.core.manifest import get_manifest
from app.core.storage import read_artifact
from app.queue.db import init_db
from app.modules.intake import intake_url


def test_ingest_url_writes_artifacts_and_manifest(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    html = "<html><body><h1>Title</h1><p>Hello world</p><script>x</script></body></html>"
    monkeypatch.setattr(intake_url, "scrape", lambda url: html)
    monkeypatch.setattr(intake_url, "extract", lambda h: "Title Hello world")

    source_id = "url:https://example.com"
    source_version = sha256_text("Title Hello world")
    manifest = intake_url.ingest_url("https://example.com", source_id, source_version)

    assert manifest["source_id"] == source_id
    stored = get_manifest(source_id, source_version)
    assert stored is not None

    text = read_artifact(source_id, source_version, "text/canonical.txt")
    assert text == "Title Hello world"
