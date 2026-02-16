"""Initiative intake: validate and normalize initiative payload."""

from __future__ import annotations

from app.core.models import InitiativeInput


def intake(data: dict) -> dict:
    payload = InitiativeInput.model_validate(data)
    return payload.model_dump()
