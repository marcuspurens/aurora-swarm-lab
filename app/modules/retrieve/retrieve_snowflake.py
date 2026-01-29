"""Retrieve evidence from Snowflake (MVP)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.clients.snowflake_client import SnowflakeClient


def retrieve(query: str, limit: int = 10, client: Optional[SnowflakeClient] = None) -> List[Dict[str, Any]]:
    client = client or SnowflakeClient()
    sql = client.search_segments(query, limit=limit)
    # In MVP, return SQL as placeholder evidence item
    return [{"doc_id": "N/A", "segment_id": "N/A", "text_snippet": query, "sql": sql, "score": 0.0}]
