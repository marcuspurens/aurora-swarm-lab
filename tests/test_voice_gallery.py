from app.modules.voiceprint.gallery import list_voiceprints, suggest_person, upsert_person
from app.core.storage import write_artifact
from app.queue.db import init_db


def test_voice_gallery_list_and_update(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "youtube:abc"
    source_version = "v1"
    write_artifact(
        source_id,
        source_version,
        "voiceprint/voiceprints.jsonl",
        "{\"voiceprint_id\":\"vp1\",\"speaker_local_id\":\"S1\",\"segment_count\":1,\"source_id\":\"youtube:abc\"}\n",
    )

    items = list_voiceprints()
    assert items[0]["voiceprint_id"] == "vp1"

    updated = upsert_person("vp1", {"given_name": "Anna", "family_name": "Karlsson", "title": "CEO"})
    assert updated["given_name"] == "Anna"

    suggested = suggest_person(
        "vp1",
        {
            "title": "Channel",
            "tags": ["auto-suggested"],
            "identifiers": [{"scheme": "youtube", "value": "channel-1"}],
            "source_refs": {"youtube": "channel-1"},
        },
    )
    assert suggested["title"] == "CEO"
    assert "auto-suggested" in suggested["tags"]
    assert suggested["identifiers"][0]["scheme"] == "youtube"
    assert suggested["source_refs"]["youtube"] == "channel-1"
