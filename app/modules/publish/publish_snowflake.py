"""Publish artifacts to Snowflake."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.clients.snowflake_client import SnowflakeClient, merge_documents_sql, merge_segments_sql


def publish_documents(rows: List[Dict[str, Any]], client: Optional[SnowflakeClient] = None, dry_run: bool = True) -> str:
    sql = merge_documents_sql(rows)
    if dry_run:
        return sql
    client = client or SnowflakeClient()
    client.execute_sql(sql)
    return sql


def publish_segments(rows: List[Dict[str, Any]], client: Optional[SnowflakeClient] = None, dry_run: bool = True) -> str:
    sql = merge_segments_sql(rows)
    if dry_run:
        return sql
    client = client or SnowflakeClient()
    client.execute_sql(sql)
    return sql
