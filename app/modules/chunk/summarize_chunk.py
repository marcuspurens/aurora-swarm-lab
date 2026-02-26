"""Generates a one-sentence summary for a chunk using Claude haiku."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def summarize_chunk(text: str, context: str = "") -> str:
    """Return a 1-2 sentence summary of *text* using claude-haiku-4-5-20251001.

    Falls back to ``""`` if the API call fails, times out, or no key is set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    prompt_parts: list[str] = []
    if context:
        prompt_parts.append(f"Context: {context}")
    prompt_parts.append(f"Text: {text[:2000]}")
    user_content = "\n\n".join(prompt_parts)

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 150,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Summarize this text in 1-2 sentences, capturing key "
                    "topics, names, and conclusions:\n\n" + user_content
                ),
            }
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "").strip()
            return ""
    except Exception:
        return ""
