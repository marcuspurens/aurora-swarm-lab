"""Transcribe audio using Whisper CLI and parse segments."""

from __future__ import annotations

from pathlib import Path
from typing import List, Dict

from app.clients.whisper_client import run_whisper, parse_srt_or_vtt


def transcribe(audio_path: str, output_dir: str, doc_id: str, output_format: str = "srt") -> List[Dict[str, object]]:
    out_path = run_whisper(audio_path, output_dir, output_format=output_format)
    text = Path(out_path).read_text(encoding="utf-8")
    return parse_srt_or_vtt(text, doc_id=doc_id)
