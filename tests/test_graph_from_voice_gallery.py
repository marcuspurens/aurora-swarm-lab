import json

from app.core.storage import artifact_path
from app.modules.graph import graph_from_voice_gallery
from app.queue.db import init_db


def test_graph_from_voice_gallery(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()
    artifacts_root.mkdir(parents=True, exist_ok=True)

    gallery = {
        "vp1": {
            "voiceprint_id": "vp1",
            "display_name": "Socialdemokraterna",
            "ebucore": {
                "@graph": [
                    {
                        "id": "urn:se:party:S",
                        "type": "ec:Organisation",
                        "ec:name": {"@value": "Socialdemokraterna", "@language": "sv"},
                        "skos:notation": "S",
                        "dct:identifier": "S",
                    }
                ]
            },
        }
    }
    gallery_path = artifacts_root / "voice_gallery.json"
    gallery_path.write_text(json.dumps(gallery, ensure_ascii=True), encoding="utf-8")

    graph_from_voice_gallery.handle_job({"source_id": "voice_gallery", "source_version": "latest", "lane": "io"})

    entities_path = artifact_path("voice_gallery", "latest", "graph/entities.jsonl")
    relations_path = artifact_path("voice_gallery", "latest", "graph/relations.jsonl")
    assert entities_path.exists()
    assert relations_path.exists()
