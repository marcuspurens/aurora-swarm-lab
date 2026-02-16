"""Ollama client."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import List, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import load_settings
from app.modules.privacy.egress_policy import apply_egress_policy

T = TypeVar("T", bound=BaseModel)


def generate(prompt: str, model: str) -> str:
    settings = load_settings()
    decision = apply_egress_policy(prompt, provider="ollama")
    url = f"{settings.ollama_base_url}/api/generate"
    payload = {"model": model, "prompt": decision.text, "stream": False, "keep_alive": -1}
    data = _post_json(
        url=url,
        payload=payload,
        timeout_seconds=settings.ollama_request_timeout_seconds,
        retries=settings.ollama_request_retries,
        backoff_seconds=settings.ollama_request_backoff_seconds,
    )
    return data.get("response", "")


def generate_json(prompt: str, model: str, schema: Type[T], max_retries: int = 2) -> T:
    last_error = None
    current_prompt = prompt
    for _ in range(max_retries + 1):
        response = generate(current_prompt, model)
        try:
            payload = _extract_json(response)
            return schema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            current_prompt = (
                "Return ONLY valid JSON for the schema. Fix this output:\n"
                f"{response}\n"
            )
    raise RuntimeError(f"Failed to generate valid JSON: {last_error}")


def embed(text: str, model: str | None = None) -> List[float]:
    settings = load_settings()
    use_model = model or settings.ollama_model_embed
    url = f"{settings.ollama_base_url}/api/embeddings"
    data = _post_json(
        url=url,
        payload={"model": use_model, "prompt": text},
        timeout_seconds=settings.ollama_request_timeout_seconds,
        retries=settings.ollama_request_retries,
        backoff_seconds=settings.ollama_request_backoff_seconds,
    )
    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        raise RuntimeError("Ollama embeddings response missing embedding list")
    return [float(x) for x in embedding]


def _extract_json(text: str) -> object:
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    start = min((i for i in [text.find("{"), text.find("[")] if i != -1), default=-1)
    if start == -1:
        raise ValueError("No JSON start found")
    end_curly = text.rfind("}")
    end_bracket = text.rfind("]")
    end = max(end_curly, end_bracket)
    if end == -1 or end <= start:
        raise ValueError("No JSON end found")
    snippet = text[start : end + 1]
    return json.loads(snippet)


def _post_json(
    url: str,
    payload: object,
    timeout_seconds: int,
    retries: int,
    backoff_seconds: float,
) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    attempts = max(1, int(retries) + 1)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError("Ollama response must be a JSON object")
            return parsed
        except Exception as exc:
            last_error = exc
            if attempt >= attempts - 1:
                break
            sleep_seconds = max(0.0, float(backoff_seconds)) * (2**attempt)
            if sleep_seconds > 0.0:
                time.sleep(sleep_seconds)
    raise RuntimeError(f"Ollama request failed after {attempts} attempt(s): {last_error}")
