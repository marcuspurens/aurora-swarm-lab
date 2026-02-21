import json

from app.core.manifest import get_manifest, upsert_manifest
from app.core.models import TranscriptMarkdownOutput
from app.core.storage import artifact_path, write_artifact
from app.modules.transcribe import transcript_markdown
from app.queue.db import init_db


def test_transcript_markdown_writes_json_and_md(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "youtube:abc123"
    source_version = "v1"
    write_artifact(
        source_id,
        source_version,
        "transcript/segments.jsonl",
        (
            '{"doc_id":"youtube:abc123","segment_id":"seg_1","start_ms":0,"end_ms":1000,"speaker_local_id":"UNKNOWN","text":"hello world"}\n'
            '{"doc_id":"youtube:abc123","segment_id":"seg_2","start_ms":1000,"end_ms":2000,"speaker_local_id":"UNKNOWN","text":"second sentence"}\n'
        ),
    )
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "metadata": {
                "intake": {
                    "tags": ["Knowledge Graph"],
                    "context": "Webinar context",
                    "source_metadata": {
                        "speaker": "Philipp Roth",
                        "organization": "ORF",
                        "event_date": "2025-06-24",
                    },
                }
            },
            "artifacts": {"segments": "transcript/segments.jsonl", "transcript": "transcript/source.srt"},
        },
    )

    def fake_generate_json(prompt, model, schema):
        return TranscriptMarkdownOutput(
            cleaned_transcript="Hello world. Second sentence.",
            summary_short="Short summary.",
            summary_long="Long summary.",
        )

    monkeypatch.setattr(transcript_markdown, "generate_json", fake_generate_json)
    transcript_markdown.handle_job({"source_id": source_id, "source_version": source_version, "lane": "oss20b"})

    md_path = artifact_path(source_id, source_version, "transcript/summary.md")
    json_path = artifact_path(source_id, source_version, "transcript/summary.json")
    assert md_path.exists()
    assert json_path.exists()
    md = md_path.read_text(encoding="utf-8")
    assert "## Short Summary" in md
    assert "## Long Summary" in md
    assert "## Clean Transcript" in md
    assert "Philipp Roth" in md
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary_short"] == "Short summary."

    manifest = get_manifest(source_id, source_version)
    assert manifest is not None
    assert manifest.get("artifacts", {}).get("transcript_summary_md") == "transcript/summary.md"
    assert manifest.get("steps", {}).get("transcript_markdown", {}).get("status") == "done"


def test_transcript_markdown_marks_clipped_when_prompt_limited(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("AURORA_TRANSCRIPT_MARKDOWN_MAX_CHARS", "4000")
    init_db()

    source_id = "youtube:cliptest"
    source_version = "v1"
    long_text = "x " * 5000
    write_artifact(
        source_id,
        source_version,
        "transcript/source.srt",
        long_text,
    )
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {"transcript": "transcript/source.srt"},
        },
    )

    def fake_generate_json(prompt, model, schema):
        return TranscriptMarkdownOutput(
            cleaned_transcript="Cleaned.",
            summary_short="Short.",
            summary_long="Long.",
        )

    monkeypatch.setattr(transcript_markdown, "generate_json", fake_generate_json)
    transcript_markdown.handle_job({"source_id": source_id, "source_version": source_version, "lane": "oss20b"})

    manifest = get_manifest(source_id, source_version)
    assert manifest is not None
    step = manifest.get("steps", {}).get("transcript_markdown", {})
    assert step.get("clipped") is True
