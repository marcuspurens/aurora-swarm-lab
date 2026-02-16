from app.core.textnorm import normalize_user_text


def test_normalize_user_text_nfkc_and_whitespace():
    raw = "ＡＢＣ　１２３\n\n\tｘ  "
    out = normalize_user_text(raw, max_len=100)
    assert out == "ABC 123 x"


def test_normalize_user_text_enforces_max_len():
    raw = "a" * 200
    out = normalize_user_text(raw, max_len=50)
    assert len(out) == 50


def test_normalize_user_text_handles_bad_shapes():
    samples = [
        " \n\t  ",
        "x" * 5000,
        "Hello\u00A0\u00A0World",
        "Ｈｅｌｌｏ　１２３",
        "a\t\tb\n\nc",
    ]
    for item in samples:
        out = normalize_user_text(item, max_len=80)
        assert len(out) <= 80
        assert "\n" not in out
        assert "\t" not in out
        assert "  " not in out
