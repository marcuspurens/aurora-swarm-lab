from app.clients.snowflake_client import merge_memory_sql


def test_merge_memory_sql():
    sql = merge_memory_sql(
        [
            {
                "memory_id": "m1",
                "category": "working",
                "text": "hello",
                "topics": ["t"],
                "entities": ["e"],
                "source_refs": {"x": 1},
                "created_at": "2025-01-01",
            }
        ]
    )
    assert "MERGE INTO MEMORY" in sql
