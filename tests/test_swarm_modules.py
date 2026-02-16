from app.modules.swarm import route, analyze, synthesize
from app.core.models import RouteOutput, AnalyzeOutput, SynthesizeOutput, SynthesizeCitation
from app.queue.db import init_db


def test_route_question_uses_generate_json(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()
    def fake_generate(prompt, model, schema):
        return RouteOutput(intent="ask", filters={"topics": ["t"]}, retrieve_top_k=3, need_strong_model=False, reason="ok")

    monkeypatch.setattr(route, "generate_json", fake_generate)
    out = route.route_question("hello")
    assert out.retrieve_top_k == 3
    assert out.reason == "ok"


def test_route_question_normalizes_whitespace(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()
    captured = {}

    def fake_generate(prompt, model, schema):
        captured["prompt"] = prompt
        return RouteOutput(intent="ask", filters={}, retrieve_top_k=3, need_strong_model=False, reason="ok")

    monkeypatch.setattr(route, "generate_json", fake_generate)
    out = route.route_question("  hello   \n   world  ")
    assert out.retrieve_top_k == 3
    assert "Question:\nhello world\n" in captured["prompt"]


def test_route_question_sanitizes_route_output(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    def fake_generate(prompt, model, schema):
        return RouteOutput(
            intent="ask",
            filters={
                "topics": ["finance", "finance", " "],
                "entities": [" ACME  ", ""],
                "source_type": "report",
                "memory_type": "working",
                "memory_kind": "procedural",
                "date_from": "2026-02-01",
                "date_to": "bad-date",
                "unknown": "drop-me",
            },
            retrieve_top_k=999,
            need_strong_model=False,
            reason="ok",
        )

    monkeypatch.setattr(route, "generate_json", fake_generate)
    out = route.route_question("hello")
    assert out.retrieve_top_k == 20
    assert out.filters == {
        "topics": ["finance"],
        "entities": ["ACME"],
        "source_type": "report",
        "memory_type": "working",
        "memory_kind": "procedural",
        "date_from": "2026-02-01",
    }


def test_route_question_drops_invalid_memory_kind(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    def fake_generate(prompt, model, schema):
        return RouteOutput(intent="ask", filters={"memory_kind": "unknown_kind"}, retrieve_top_k=3, need_strong_model=False, reason="ok")

    monkeypatch.setattr(route, "generate_json", fake_generate)
    out = route.route_question("hello")
    assert "memory_kind" not in out.filters


def test_analyze(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()
    def fake_generate(prompt, model, schema):
        return AnalyzeOutput(claims=["c"], timeline=[], open_questions=[])

    monkeypatch.setattr(analyze, "generate_json", fake_generate)
    out = analyze.analyze("q", [{"doc_id": "d"}])
    assert out.claims == ["c"]


def test_synthesize(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()
    def fake_generate(prompt, model, schema):
        return SynthesizeOutput(answer_text="a", citations=[SynthesizeCitation(doc_id="d", segment_id="s")])

    monkeypatch.setattr(synthesize, "generate_json", fake_generate)
    out = synthesize.synthesize("q", [{"doc_id": "d"}], analysis=None, use_strong_model=False)
    assert out.answer_text == "a"


def test_route_question_fallback_on_model_error(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    def fake_generate(prompt, model, schema):
        raise RuntimeError("route timeout")

    monkeypatch.setattr(route, "generate_json", fake_generate)
    out = route.route_question("hello")
    assert out.intent == "ask"
    assert out.filters == {}
    assert out.retrieve_top_k == 8
    assert out.need_strong_model is False
    assert "fallback_route:" in (out.reason or "")


def test_analyze_fallback_on_model_error(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    def fake_generate(prompt, model, schema):
        raise RuntimeError("analyze timeout")

    monkeypatch.setattr(analyze, "generate_json", fake_generate)
    out = analyze.analyze("q", [{"doc_id": "d"}])
    assert out.claims == []
    assert out.timeline == []
    assert out.open_questions
    assert "analysis_fallback:" in out.open_questions[0]


def test_synthesize_fallback_on_model_error(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    def fake_generate(prompt, model, schema):
        raise RuntimeError("synthesize timeout")

    monkeypatch.setattr(synthesize, "generate_json", fake_generate)
    out = synthesize.synthesize(
        "q",
        [{"doc_id": "doc-1", "segment_id": "seg-1", "text_snippet": "alpha evidence"}],
        analysis=None,
        use_strong_model=False,
    )
    assert "Fallback answer" in out.answer_text
    assert out.citations
    assert out.citations[0].doc_id == "doc-1"
