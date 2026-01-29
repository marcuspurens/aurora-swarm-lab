"""Ollama client stub."""

from __future__ import annotations

import json
import urllib.request

from app.core.config import load_settings


def generate(prompt: str, model: str) -> str:
    settings = load_settings()
    url = f"{settings.ollama_base_url}/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "keep_alive": -1}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("response", "")
