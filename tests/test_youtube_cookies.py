"""Tests for YouTube cookie support in youtube_client."""

from app.clients.youtube_client import _resolve_cookies, _apply_cookies


def test_resolve_cookies_none_by_default():
    assert _resolve_cookies() is None


def test_resolve_cookies_explicit_param():
    assert _resolve_cookies("chrome") == "chrome"


def test_resolve_cookies_from_env(monkeypatch):
    monkeypatch.setenv("AURORA_YOUTUBE_COOKIES_FROM_BROWSER", "safari")
    assert _resolve_cookies() == "safari"


def test_resolve_cookies_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("AURORA_YOUTUBE_COOKIES_FROM_BROWSER", "safari")
    assert _resolve_cookies("firefox") == "firefox"


def test_resolve_cookies_empty_string_returns_none():
    assert _resolve_cookies("") is None


def test_resolve_cookies_whitespace_returns_none():
    assert _resolve_cookies("  ") is None


def test_apply_cookies_noop_without_source():
    opts = {"quiet": True}
    _apply_cookies(opts)
    assert "cookiesfrombrowser" not in opts
    assert "cookiefile" not in opts


def test_apply_cookies_browser_name():
    opts = {}
    _apply_cookies(opts, "chrome")
    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert "cookiefile" not in opts


def test_apply_cookies_safari():
    opts = {}
    _apply_cookies(opts, "safari")
    assert opts["cookiesfrombrowser"] == ("safari",)


def test_apply_cookies_file_path():
    opts = {}
    _apply_cookies(opts, "/path/to/cookies.txt")
    assert opts["cookiefile"] == "/path/to/cookies.txt"
    assert "cookiesfrombrowser" not in opts


def test_apply_cookies_windows_path():
    opts = {}
    _apply_cookies(opts, "C:\\Users\\me\\cookies.txt")
    assert opts["cookiefile"] == "C:\\Users\\me\\cookies.txt"


def test_apply_cookies_txt_suffix():
    opts = {}
    _apply_cookies(opts, "cookies.txt")
    assert opts["cookiefile"] == "cookies.txt"


def test_apply_cookies_from_env(monkeypatch):
    monkeypatch.setenv("AURORA_YOUTUBE_COOKIES_FROM_BROWSER", "firefox")
    opts = {}
    _apply_cookies(opts)
    assert opts["cookiesfrombrowser"] == ("firefox",)


def test_backward_compatible_no_cookies():
    """Existing calls without cookies parameter work unchanged."""
    opts = {"format": "bestaudio/best", "quiet": True}
    original = dict(opts)
    _apply_cookies(opts)
    assert opts == original
