"""Route a question using fast model (stub)."""

from __future__ import annotations

from app.core.models import RouteOutput


def route_question(question: str) -> RouteOutput:
    return RouteOutput(intent="ask", filters={}, retrieve_top_k=10, need_strong_model=False, reason="stub")
