from app.modules.initiatives.publish_initiatives import publish
from app.queue.db import init_db


def test_publish_initiatives_builds_sql(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    class FakeClient:
        def execute_sql(self, sql: str) -> None:
            return None

    scores = [
        {
            "initiative_id": "i1",
            "title": "Test",
            "scores": {"value": 1},
            "overall_score": 50,
            "rationale": "ok",
            "citations": [],
        }
    ]
    receipt = publish(scores, "report text", client=FakeClient())
    assert "INITIATIVES" in receipt["scores_sql"]
    assert receipt["error"] is None
