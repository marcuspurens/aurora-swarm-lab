from app.modules.voiceprint.diarize import _assign_speakers
from app.clients.diarization_client import DiarizationSegment


def test_assign_speakers():
    segments = [
        {"segment_id": "s1", "start_ms": 0, "end_ms": 1000, "speaker_local_id": "UNKNOWN", "text": "a"},
        {"segment_id": "s2", "start_ms": 1000, "end_ms": 2000, "speaker_local_id": "UNKNOWN", "text": "b"},
    ]
    diar = [
        DiarizationSegment(start_ms=0, end_ms=1200, speaker="SPK1"),
        DiarizationSegment(start_ms=1200, end_ms=2200, speaker="SPK2"),
    ]
    out = _assign_speakers(segments, diar)
    assert out[0]["speaker_local_id"] == "SPK1"
    assert out[1]["speaker_local_id"] == "SPK2"
