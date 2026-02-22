"""Whisper CLI client and SRT/VTT parsing."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Dict

from app.core.config import load_settings


WhisperBackend = str

def run_whisper(audio_path: str, output_dir: str, output_format: str = "srt") -> Path:
    out_path, _backend = run_whisper_backend(audio_path, output_dir, output_format=output_format)
    return out_path


def run_whisper_backend(audio_path: str, output_dir: str, output_format: str = "srt") -> tuple[Path, WhisperBackend]:
    settings = load_settings()
    backend = _normalize_backend(settings.transcribe_backend)
    if backend == "whisper_cli":
        out = _run_whisper_cli(audio_path, output_dir, output_format=output_format, cmd=settings.whisper_cli_cmd)
        return out, "whisper_cli"
    if backend == "faster_whisper":
        out = _run_faster_whisper(
            audio_path,
            output_dir,
            output_format=output_format,
            model=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            language=settings.whisper_language,
        )
        return out, "faster_whisper"
    if backend == "auto":
        errors = []
        try:
            out = _run_whisper_cli(audio_path, output_dir, output_format=output_format, cmd=settings.whisper_cli_cmd)
            return out, "whisper_cli"
        except Exception as exc:
            errors.append(f"whisper_cli: {exc}")
        try:
            out = _run_faster_whisper(
                audio_path,
                output_dir,
                output_format=output_format,
                model=settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                language=settings.whisper_language,
            )
            return out, "faster_whisper"
        except Exception as exc:
            errors.append(f"faster_whisper: {exc}")
        joined = " | ".join(errors)
        raise RuntimeError(f"No transcription backend available ({joined})")
    raise RuntimeError(f"Unsupported TRANSCRIBE_BACKEND: {settings.transcribe_backend}")


def _run_whisper_cli(audio_path: str, output_dir: str, output_format: str = "srt", cmd: str = "whisper") -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(cmd or "whisper"),
        audio_path,
        "--output_format",
        output_format,
        "--output_dir",
        str(out_dir),
    ]
    subprocess.run(cmd, check=True)
    stem = Path(audio_path).stem
    return out_dir / f"{stem}.{output_format}"


def _run_faster_whisper(
    audio_path: str,
    output_dir: str,
    output_format: str = "srt",
    model: str = "small",
    device: str = "auto",
    compute_type: str = "default",
    language: str | None = None,
) -> Path:
    if output_format not in {"srt", "vtt"}:
        raise RuntimeError("faster_whisper backend supports only srt or vtt output")
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as exc:
        raise RuntimeError("faster-whisper not installed") from exc

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(audio_path).stem
    out_path = out_dir / f"{stem}.{output_format}"

    model_obj = WhisperModel(model_size_or_path=model or "small", device=device or "auto", compute_type=compute_type or "default")
    kwargs = {}
    if language:
        kwargs["language"] = language
    segments, _info = model_obj.transcribe(audio_path, **kwargs)
    _write_segments_caption_file(out_path, segments, output_format)
    return out_path


def _normalize_backend(value: object) -> str:
    candidate = str(value or "auto").strip().lower()
    if candidate in {"auto", "whisper_cli", "faster_whisper"}:
        return candidate
    return "auto"


def _write_segments_caption_file(path: Path, segments: object, output_format: str) -> None:
    lines: List[str] = []
    if output_format == "vtt":
        lines.append("WEBVTT")
        lines.append("")
    index = 0
    for seg in segments:
        start = _segment_seconds(seg, "start")
        end = _segment_seconds(seg, "end")
        text = _segment_text(seg).strip()
        if not text:
            continue
        index += 1
        if output_format == "srt":
            lines.append(str(index))
            lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
            lines.append(text)
            lines.append("")
        else:
            lines.append(f"{_format_vtt_time(start)} --> {_format_vtt_time(end)}")
            lines.append(text)
            lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _segment_seconds(segment: object, field: str) -> float:
    try:
        value = getattr(segment, field)
    except Exception:
        value = None
    if value is None and isinstance(segment, dict):
        value = segment.get(field)
    try:
        return float(value)
    except Exception:
        return 0.0


def _segment_text(segment: object) -> str:
    try:
        value = getattr(segment, "text")
    except Exception:
        value = None
    if value is None and isinstance(segment, dict):
        value = segment.get("text")
    return str(value or "")


def _format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000.0)))
    h = total_ms // 3600000
    rem = total_ms % 3600000
    m = rem // 60000
    rem = rem % 60000
    s = rem // 1000
    ms = rem % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    return _format_srt_time(seconds).replace(",", ".")


def parse_srt_or_vtt(text: str, doc_id: str) -> List[Dict[str, object]]:
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    seg_id = 0
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if re.match(r"^\d+$", lines[0]):
            lines = lines[1:]
        if not lines:
            continue
        time_line = lines[0]
        match = re.match(r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})", time_line)
        if not match:
            continue
        start_ms = _time_to_ms(match.group(1))
        end_ms = _time_to_ms(match.group(2))
        text_lines = lines[1:]
        segment_text = " ".join(text_lines).strip()
        if not segment_text:
            continue
        seg_id += 1
        segments.append(
            {
                "doc_id": doc_id,
                "segment_id": f"seg_{seg_id}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speaker_local_id": "UNKNOWN",
                "text": segment_text,
            }
        )
    return segments


def _time_to_ms(ts: str) -> int:
    ts = ts.replace(",", ".")
    h, m, s = ts.split(":")
    sec, ms = s.split(".")
    total = (int(h) * 3600 + int(m) * 60 + int(sec)) * 1000 + int(ms)
    return total
