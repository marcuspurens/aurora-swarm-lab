"""Tests for chunk summary generation."""

from unittest.mock import patch

from app.modules.chunk import chunk_text, chunk_transcript
from app.modules.chunk.summarize_chunk import summarize_chunk


def test_summarize_chunk_returns_string():
    """summarize_chunk returns a string (mocked API)."""
    fake_response = b'{"content": [{"type": "text", "text": "A brief summary."}]}'
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        mock_urlopen.return_value.read.return_value = fake_response
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            result = summarize_chunk("The meeting discussed quarterly results.")
    assert isinstance(result, str)
    assert result == "A brief summary."


def test_summarize_chunk_empty_on_missing_api_key(monkeypatch):
    """summarize_chunk returns empty string when API key is not set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = summarize_chunk("Some text here.")
    assert result == ""


def test_summarize_chunk_empty_on_api_error():
    """summarize_chunk returns empty string on API errors."""
    with patch("urllib.request.urlopen", side_effect=Exception("connection error")):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            result = summarize_chunk("Some text here.")
    assert result == ""


def test_chunk_text_returns_text_to_embed_field(monkeypatch):
    """chunk_text.chunk() returns chunks with text_to_embed field."""
    monkeypatch.setenv("CHUNK_SUMMARIES_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_response = b'{"content": [{"type": "text", "text": "Revenue growth discussion."}]}'
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        mock_urlopen.return_value.read.return_value = fake_response
        chunks = chunk_text.chunk(
            "The meeting discussed quarterly results. Revenue was up 12 percent.",
            doc_id="test",
        )
    assert len(chunks) >= 1
    c = chunks[0]
    assert "text_to_embed" in c
    assert "summary" in c
    assert c["summary"] == "Revenue growth discussion."
    assert c["text_to_embed"].startswith("Summary: Revenue growth discussion.")
    assert "The meeting discussed" in c["text_to_embed"]


def test_chunk_text_original_text_unchanged(monkeypatch):
    """chunk_text.chunk() does not modify the original text field."""
    monkeypatch.setenv("CHUNK_SUMMARIES_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    original = "The meeting discussed quarterly results."
    fake_response = b'{"content": [{"type": "text", "text": "Summary of meeting."}]}'
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        mock_urlopen.return_value.read.return_value = fake_response
        chunks = chunk_text.chunk(original, doc_id="test")
    assert chunks[0]["text"] == original


def test_chunk_text_disabled_no_summary(monkeypatch):
    """When chunk_summaries_enabled=False, text_to_embed equals text."""
    monkeypatch.setenv("CHUNK_SUMMARIES_ENABLED", "0")
    text = "Some content here."
    chunks = chunk_text.chunk(text, doc_id="test")
    assert len(chunks) >= 1
    c = chunks[0]
    assert c["text_to_embed"] == text
    assert c["summary"] == ""


def test_chunk_transcript_returns_text_to_embed_field(monkeypatch):
    """chunk_transcript.chunk() returns chunks with text_to_embed field."""
    monkeypatch.setenv("CHUNK_SUMMARIES_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_response = b'{"content": [{"type": "text", "text": "Discussion about AI."}]}'
    segments = [
        {
            "text": "We discussed AI trends.",
            "start_ms": 0,
            "end_ms": 5000,
            "speaker_local_id": "S1",
            "segment_id": "s1",
        },
        {
            "text": "The market is growing fast.",
            "start_ms": 5000,
            "end_ms": 10000,
            "speaker_local_id": "S1",
            "segment_id": "s2",
        },
    ]
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        mock_urlopen.return_value.read.return_value = fake_response
        chunks = chunk_transcript.chunk(segments, doc_id="test")
    assert len(chunks) >= 1
    c = chunks[0]
    assert "text_to_embed" in c
    assert "summary" in c
    assert c["text_to_embed"].startswith("Summary:")


def test_chunk_transcript_disabled(monkeypatch):
    """When chunk_summaries_enabled=False, transcript chunks have no summary."""
    monkeypatch.setenv("CHUNK_SUMMARIES_ENABLED", "0")
    segments = [
        {
            "text": "Hello world.",
            "start_ms": 0,
            "end_ms": 1000,
            "speaker_local_id": "S1",
            "segment_id": "s1",
        },
    ]
    chunks = chunk_transcript.chunk(segments, doc_id="test")
    assert len(chunks) >= 1
    c = chunks[0]
    assert c["summary"] == ""
    assert c["text_to_embed"] == c["text"]
