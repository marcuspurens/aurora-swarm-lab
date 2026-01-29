from app.modules.publish.publish_snowflake import publish_documents, publish_segments


def test_publish_documents_sql():
    sql = publish_documents([
        {
            "doc_id": "d1",
            "source_id": "url:x",
            "source_version": "v1",
            "source_type": "url",
            "source_uri": "x",
            "title": "t",
            "language": "en",
            "summary_short": "s",
            "summary_long": "l",
            "metadata": {"k": "v"},
            "created_at": "2025-01-01",
        }
    ])
    assert "MERGE INTO DOCUMENTS" in sql


def test_publish_segments_sql():
    sql = publish_segments([
        {
            "doc_id": "d1",
            "segment_id": "s1",
            "start_ms": 0,
            "end_ms": 10,
            "speaker": "UNKNOWN",
            "text": "hello",
            "topics": ["a"],
            "entities": ["b"],
            "source_refs": {"x": 1},
            "updated_at": "2025-01-01",
        }
    ])
    assert "MERGE INTO KB_SEGMENTS" in sql
