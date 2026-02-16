"""Audio extraction via ffmpeg."""

from __future__ import annotations

import subprocess


def extract(input_path: str, output_path: str, sample_rate: int = 16000) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        output_path,
    ]
    subprocess.run(cmd, check=True)
