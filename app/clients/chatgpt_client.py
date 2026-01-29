"""Optional ChatGPT client (feature-flagged)."""

from __future__ import annotations

import json
import urllib.request

from app.core.config import load_settings


def call_chatgpt(prompt: str) -> str:
    settings = load_settings()
    if not settings.chatgpt_api_enabled:
        raise RuntimeError("CHATGPT_API_ENABLED is false")
    if not settings.chatgpt_api_key:
        raise RuntimeError("CHATGPT_API_KEY not set")

    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": settings.chatgpt_model or "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.chatgpt_api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]
