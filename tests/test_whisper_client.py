from pathlib import Path
from types import SimpleNamespace

import pytest

from app.clients import whisper_client
from app.clients.whisper_client import parse_srt_or_vtt

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:03,500 --> 00:00:05,000
Second line
"""


def test_parse_srt():
    segments = parse_srt_or_vtt(SAMPLE_SRT, doc_id="doc1")
    assert len(segments) == 2
    assert segments[0]["start_ms"] == 1000
    assert segments[0]["end_ms"] == 3000
    assert segments[0]["text"] == "Hello world"


def _settings(backend: str) -> SimpleNamespace:
    return SimpleNamespace(
        transcribe_backend=backend,
        whisper_cli_cmd="whisper",
        whisper_model="small",
        whisper_device="auto",
        whisper_compute_type="default",
        whisper_language=None,
    )


def test_run_whisper_backend_auto_falls_back_to_faster(monkeypatch, tmp_path):
    expected = tmp_path / "source.srt"
    monkeypatch.setattr(whisper_client, "load_settings", lambda: _settings("auto"))
    monkeypatch.setattr(
        whisper_client,
        "_run_whisper_cli",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("whisper missing")),
    )
    monkeypatch.setattr(whisper_client, "_run_faster_whisper", lambda *_args, **_kwargs: expected)

    path, backend = whisper_client.run_whisper_backend("a.wav", str(tmp_path), output_format="srt")
    assert path == expected
    assert backend == "faster_whisper"


def test_run_whisper_backend_cli_mode(monkeypatch, tmp_path):
    expected = tmp_path / "source.srt"
    monkeypatch.setattr(whisper_client, "load_settings", lambda: _settings("whisper_cli"))
    monkeypatch.setattr(whisper_client, "_run_whisper_cli", lambda *_args, **_kwargs: expected)

    path, backend = whisper_client.run_whisper_backend("a.wav", str(tmp_path), output_format="srt")
    assert path == expected
    assert backend == "whisper_cli"


def test_run_whisper_backend_fails_when_auto_backends_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(whisper_client, "load_settings", lambda: _settings("auto"))
    monkeypatch.setattr(
        whisper_client,
        "_run_whisper_cli",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("cli failed")),
    )
    monkeypatch.setattr(
        whisper_client,
        "_run_faster_whisper",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("faster failed")),
    )

    with pytest.raises(RuntimeError, match="No transcription backend available"):
        whisper_client.run_whisper_backend("a.wav", str(tmp_path), output_format="srt")


def test_run_whisper_backend_normalizes_invalid_backend_to_auto(monkeypatch, tmp_path):
    expected = tmp_path / "source.srt"
    monkeypatch.setattr(whisper_client, "load_settings", lambda: _settings("bad-backend"))
    monkeypatch.setattr(whisper_client, "_run_whisper_cli", lambda *_args, **_kwargs: expected)

    path, backend = whisper_client.run_whisper_backend("a.wav", str(tmp_path), output_format="srt")
    assert path == expected
    assert backend == "whisper_cli"


def test_write_segments_caption_file_srt(tmp_path):
    out = tmp_path / "x.srt"
    whisper_client._write_segments_caption_file(
        out,
        [{"start": 0.0, "end": 1.2, "text": " Hello "}, {"start": 1.2, "end": 2.2, "text": "World"}],
        "srt",
    )
    text = out.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,200" in text
    assert "Hello" in text
    assert "World" in text
