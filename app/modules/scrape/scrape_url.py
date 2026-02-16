"""Scrape URL to raw HTML."""

from __future__ import annotations

from app.clients.http_client import fetch_text


def scrape(url: str) -> str:
    return fetch_text(url)
