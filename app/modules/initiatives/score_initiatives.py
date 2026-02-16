"""Initiative scoring (MVP)."""

from __future__ import annotations

from typing import List, Dict

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.models import InitiativeInput, InitiativeScore
from app.queue.logs import log_run


def _prompt(item: InitiativeInput) -> str:
    return (
        "Return ONLY valid JSON with keys: initiative_id, title, scores, overall_score, rationale, citations. "
        "scores should be an object with numeric fields: value, feasibility, risk, alignment, time_to_value. "
        "overall_score is 0-100. rationale is a short paragraph. citations optional.\n\n"
        f"Initiative:\n{item.model_dump()}\n"
    )


def score(initiatives: List[Dict]) -> List[Dict]:
    settings = load_settings()
    results: List[Dict] = []
    for data in initiatives:
        item = InitiativeInput.model_validate(data)
        run_id = log_run(
            lane="nemotron",
            component="initiative_score",
            input_json={"initiative_id": item.initiative_id},
            model=settings.ollama_model_strong,
        )
        try:
            output = generate_json(_prompt(item), settings.ollama_model_strong, InitiativeScore)
            results.append(output.model_dump())
            log_run(
                lane="nemotron",
                component="initiative_score",
                input_json={"run_id": run_id},
                output_json=output.model_dump(),
            )
        except Exception as exc:
            log_run(
                lane="nemotron",
                component="initiative_score",
                input_json={"run_id": run_id},
                error=str(exc),
            )
            raise
    return results
