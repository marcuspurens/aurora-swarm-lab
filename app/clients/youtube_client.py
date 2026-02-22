"""YouTube client for audio extraction via yt-dlp."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional


def _resolve_cookies(cookies_from_browser: Optional[str] = None) -> Optional[str]:
    """Resolve cookie source from parameter or environment variable.

    Returns the cookie source string (browser name or file path), or None.
    Never logs the actual cookie content.
    """
    source = cookies_from_browser or os.getenv("AURORA_YOUTUBE_COOKIES_FROM_BROWSER")
    if not source:
        return None
    return source.strip() or None


def _apply_cookies(ydl_opts: dict, cookies_from_browser: Optional[str] = None) -> None:
    """Apply cookie options to yt-dlp options dict."""
    source = _resolve_cookies(cookies_from_browser)
    if not source:
        return
    # If it looks like a file path (contains / or \), use cookiefile
    if "/" in source or "\\" in source or source.endswith(".txt"):
        ydl_opts["cookiefile"] = source
    else:
        # Browser name: chrome, safari, firefox, etc.
        ydl_opts["cookiesfrombrowser"] = (source,)


def get_video_info(url: str, *, cookies_from_browser: Optional[str] = None) -> Dict[str, object]:
    try:
        import yt_dlp  # type: ignore
    except Exception as exc:
        raise RuntimeError("yt-dlp not installed") from exc

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }
    _apply_cookies(ydl_opts, cookies_from_browser)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def extract_audio(url: str, output_path: str, *, cookies_from_browser: Optional[str] = None) -> Path:
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
    _apply_cookies(ydl_opts, cookies_from_browser)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return output_base.with_suffix(".m4a")
