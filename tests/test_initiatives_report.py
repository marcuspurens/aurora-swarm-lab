from app.modules.initiatives.c_level_report import build_report


def test_build_report():
    report = build_report([
        {"title": "A", "overall_score": 90, "rationale": "Good"},
        {"title": "B", "overall_score": 80, "rationale": "Ok"},
    ])
    assert "C-level Report" in report
    assert "A" in report
