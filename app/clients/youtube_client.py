"""YouTube client for audio extraction via yt-dlp."""

from __future__ import annotations

from pathlib import Path
from typing import Dict


def get_video_info(url: str) -> Dict[str, object]:
    try:
        import yt_dlp  # type: ignore
    except Exception as exc:
        raise RuntimeError("yt-dlp not installed") from exc

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def extract_audio(url: str, output_path: str) -> Path:
    try:
        import yt_dlp  # type: ignore
    except Exception as exc:
        raise RuntimeError("yt-dlp not installed") from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_base = output.with_suffix("")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_base),
        "quiet": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "0",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return output_base.with_suffix(".m4a")
