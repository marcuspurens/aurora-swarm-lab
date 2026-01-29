"""Whisper CLI client and SRT/VTT parsing."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Dict


def run_whisper(audio_path: str, output_dir: str, output_format: str = "srt") -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "whisper",
        audio_path,
        "--output_format",
        output_format,
        "--output_dir",
        str(out_dir),
    ]
    subprocess.run(cmd, check=True)
    stem = Path(audio_path).stem
    return out_dir / f"{stem}.{output_format}"


def parse_srt_or_vtt(text: str, doc_id: str) -> List[Dict[str, object]]:
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    seg_id = 0
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
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
