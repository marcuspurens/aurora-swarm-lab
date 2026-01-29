"""Minimal HTTP client using urllib."""

from __future__ import annotations

from urllib.request import urlopen


def fetch_text(url: str, timeout: int = 30) -> str:
    with urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")
