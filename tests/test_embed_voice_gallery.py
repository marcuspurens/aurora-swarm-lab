import json

from app.modules.embeddings import embed_voice_gallery
from app.queue.db import get_conn, init_db


def test_embed_voice_gallery(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "1")
    init_db()
    artifacts_root.mkdir(parents=True, exist_ok=True)

    gallery = {
        "vp1": {
            "voiceprint_id": "vp1",
            "display_name": "Alice",
            "tags": ["speaker"],
            "ebucore": {"@graph": []},
        }
    }
    gallery_path = artifacts_root / "voice_gallery.json"
    gallery_path.write_text(json.dumps(gallery, ensure_ascii=True), encoding="utf-8")

    monkeypatch.setattr(embed_voice_gallery, "embed", lambda text: [0.25, 0.75])
    embed_voice_gallery.handle_job({"source_id": "voice_gallery", "source_version": "latest", "lane": "oss20b"})

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM embeddings WHERE doc_id='voice_gallery'")
        count = cur.fetchone()[0]
    assert count == 1
