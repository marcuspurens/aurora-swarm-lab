from app.modules.initiatives import score_initiatives, pipeline
from app.modules.initiatives.pipeline import run_pipeline
from app.core.models import InitiativeScore, SynthesizeCitation
from app.queue.db import init_db


def test_pipeline(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    def fake_generate(prompt, model, schema):
        return InitiativeScore(
            initiative_id="i1",
            title="Test",
            scores={"value": 8, "feasibility": 7, "risk": 5, "alignment": 9, "time_to_value": 6},
            overall_score=78.0,
            rationale="OK",
            citations=[SynthesizeCitation(doc_id="d", segment_id="s")],
        )

    monkeypatch.setattr(score_initiatives, "generate_json", fake_generate)
    monkeypatch.setattr(pipeline, "publish", lambda scores, report: {"error": None})

    data = [
        {
            "initiative_id": "i1",
            "title": "Test",
            "problem_statement": "p",
            "users_affected": "u",
            "data_sources": ["x"],
            "feasibility": "f",
            "risk_compliance": "r",
            "expected_value": "v",
            "dependencies": ["d"],
            "time_to_value": "t",
            "strategic_alignment": "s",
        }
    ]
    result = run_pipeline(data)
    assert result["scores"][0]["initiative_id"] == "i1"
