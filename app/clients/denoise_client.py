"""Audio denoise client (DeepFilterNet wrapper)."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import List

from app.core.config import load_settings


@dataclass
class DenoiseConfig:
    enabled: bool
    backend: str
    deepfilternet_cmd: str
    deepfilternet_args: str


def _load_cfg() -> DenoiseConfig:
    settings = load_settings()
    return DenoiseConfig(
        enabled=getattr(settings, "audio_denoise_enabled", False),
        backend=getattr(settings, "audio_denoise_backend", "deepfilternet"),
        deepfilternet_cmd=getattr(settings, "deepfilternet_cmd", "deepfilternet"),
        deepfilternet_args=getattr(settings, "deepfilternet_args", ""),
    )


def denoise_audio(input_path: str, output_path: str) -> None:
    cfg = _load_cfg()
    if not cfg.enabled:
        raise RuntimeError("Audio denoise is disabled. Set AUDIO_DENOISE_ENABLED=1")

    if cfg.backend != "deepfilternet":
        raise RuntimeError(f"Unsupported denoise backend: {cfg.backend}")

    cmd = cfg.deepfilternet_cmd
    if shutil.which(cmd) is None:
        raise RuntimeError("DeepFilterNet command not found. Install deepfilternet and set DEEPFILTERNET_CMD if needed.")

    args: List[str] = [cmd]
    if cfg.deepfilternet_args:
        args.extend(shlex.split(cfg.deepfilternet_args))
    args.extend([input_path, output_path])
    subprocess.run(args, check=True)
