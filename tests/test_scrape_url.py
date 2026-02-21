from app.modules.scrape import scrape_url


def test_scrape_keeps_http_html_when_text_is_sufficient(monkeypatch):
    monkeypatch.setenv("AURORA_URL_HEADLESS_FALLBACK_ENABLED", "1")
    monkeypatch.setenv("AURORA_URL_HEADLESS_FALLBACK_MIN_TEXT_CHARS", "5")
    http_html = "<html><body><p>Hello world from HTTP.</p></body></html>"

    monkeypatch.setattr(scrape_url, "fetch_text", lambda _url: http_html)

    def _never_called(*_args, **_kwargs):
        raise AssertionError("headless should not be used")

    monkeypatch.setattr(scrape_url, "_render_headless_html", _never_called)
    out = scrape_url.scrape("https://example.com")
    assert out == http_html


def test_scrape_uses_headless_when_http_text_is_too_thin(monkeypatch):
    monkeypatch.setenv("AURORA_URL_HEADLESS_FALLBACK_ENABLED", "1")
    monkeypatch.setenv("AURORA_URL_HEADLESS_FALLBACK_MIN_TEXT_CHARS", "20")
    http_html = "<html><body><div id='app'></div></body></html>"
    headless_html = "<html><body><article>Rendered content from JS app</article></body></html>"

    monkeypatch.setattr(scrape_url, "fetch_text", lambda _url: http_html)
    monkeypatch.setattr(scrape_url, "_render_headless_html", lambda *_args, **_kwargs: (headless_html, "ok"))
    out = scrape_url.scrape("https://example.com")
    assert out == headless_html


def test_scrape_falls_back_to_http_when_headless_unavailable(monkeypatch):
    monkeypatch.setenv("AURORA_URL_HEADLESS_FALLBACK_ENABLED", "1")
    monkeypatch.setenv("AURORA_URL_HEADLESS_FALLBACK_MIN_TEXT_CHARS", "20")
    http_html = "<html><body><div id='app'></div></body></html>"

    monkeypatch.setattr(scrape_url, "fetch_text", lambda _url: http_html)
    monkeypatch.setattr(scrape_url, "_render_headless_html", lambda *_args, **_kwargs: (None, "playwright_not_installed"))
    out = scrape_url.scrape("https://example.com")
    assert out == http_html
