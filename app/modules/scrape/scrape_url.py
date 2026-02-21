"""Scrape URL to raw HTML, with optional headless-browser fallback."""

from __future__ import annotations

import os
from typing import Optional, Tuple

from app.clients.http_client import fetch_text
from app.modules.scrape.readable_text import extract as extract_readable


_WAIT_UNTIL_ALLOWED = {"load", "domcontentloaded", "networkidle", "commit"}


def _getenv_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _getenv_int(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def _resolve_wait_until() -> str:
    value = str(os.getenv("AURORA_URL_HEADLESS_WAIT_UNTIL", "networkidle")).strip().lower()
    if value in _WAIT_UNTIL_ALLOWED:
        return value
    return "networkidle"


def _resolve_browser_name() -> str:
    value = str(os.getenv("AURORA_URL_HEADLESS_BROWSER", "chromium")).strip().lower()
    if value in {"chromium", "firefox", "webkit"}:
        return value
    return "chromium"


def _render_headless_html(url: str, timeout_ms: int, wait_until: str, browser_name: str) -> Tuple[Optional[str], str]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return None, "playwright_not_installed"

    try:
        with sync_playwright() as pw:
            if browser_name == "firefox":
                browser_type = pw.firefox
            elif browser_name == "webkit":
                browser_type = pw.webkit
            else:
                browser_type = pw.chromium
            browser = browser_type.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                html = page.content()
                return str(html or ""), "ok"
            finally:
                browser.close()
    except Exception as exc:
        return None, f"headless_error:{exc}"


def scrape(url: str) -> str:
    html = fetch_text(url)
    if not _getenv_bool("AURORA_URL_HEADLESS_FALLBACK_ENABLED", True):
        return html

    baseline_text = extract_readable(html)
    min_chars = _getenv_int("AURORA_URL_HEADLESS_FALLBACK_MIN_TEXT_CHARS", 500, 0, 20000)
    if len(baseline_text) >= min_chars:
        return html

    rendered_html, _reason = _render_headless_html(
        url=url,
        timeout_ms=_getenv_int("AURORA_URL_HEADLESS_TIMEOUT_MS", 20000, 1000, 120000),
        wait_until=_resolve_wait_until(),
        browser_name=_resolve_browser_name(),
    )
    if not rendered_html:
        return html

    rendered_text = extract_readable(rendered_html)
    if len(rendered_text) > len(baseline_text):
        return rendered_html
    return html
