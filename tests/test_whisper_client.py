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
