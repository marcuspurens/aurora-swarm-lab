"""Minimal HTTP client using urllib."""

from __future__ import annotations

import urllib.request


def fetch_text(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return its body as text, sending a custom User-Agent header."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AuroraBot/1.0)",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")
