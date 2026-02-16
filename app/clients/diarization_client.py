"""Diarization client using pyannote.audio when available."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.core.config import load_settings


@dataclass
class DiarizationSegment:
    start_ms: int
    end_ms: int
    speaker: str


def run_diarization(audio_path: str) -> List[DiarizationSegment]:
    try:
        from pyannote.audio import Pipeline  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyannote.audio not installed") from exc

    settings = load_settings()
    token = getattr(settings, "pyannote_token", None)
    model = getattr(settings, "pyannote_model", None) or "pyannote/speaker-diarization"
    if not token:
        raise RuntimeError("PYANNOTE_TOKEN not set")

    pipeline = Pipeline.from_pretrained(model, use_auth_token=token)
    diarization = pipeline(audio_path)
    segments: List[DiarizationSegment] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            DiarizationSegment(
                start_ms=int(turn.start * 1000),
                end_ms=int(turn.end * 1000),
                speaker=str(speaker),
            )
        )
    return segments
