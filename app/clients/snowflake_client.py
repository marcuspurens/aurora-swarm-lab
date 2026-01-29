"""Snowflake client stub with SQL generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import load_settings

try:
    import snowflake.connector  # type: ignore
except Exception:
    snowflake = None
else:
    snowflake = snowflake.connector


@dataclass
class SnowflakeConfig:
    account: Optional[str]
    user: Optional[str]
    password: Optional[str]
    warehouse: Optional[str]
    database: str
    schema: str


def load_snowflake_config() -> SnowflakeConfig:
    s = load_settings()
    return SnowflakeConfig(
        account=s.snowflake_account,
        user=s.snowflake_user,
        password=s.snowflake_password,
        warehouse=s.snowflake_warehouse,
        database=s.snowflake_database,
        schema=s.snowflake_schema,
    )


def merge_documents_sql(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "-- no rows"
    cols = [
        "DOC_ID", "SOURCE_ID", "SOURCE_VERSION", "SOURCE_TYPE", "SOURCE_URI", "TITLE", "LANGUAGE",
        "SUMMARY_SHORT", "SUMMARY_LONG", "METADATA", "CREATED_AT"
    ]
    values = []
    for r in rows:
        vals = [r.get(c.lower()) if c != "CREATED_AT" else r.get("created_at") for c in cols]
        values.append(vals)

    values_sql = ",\n".join(
        "(" + ", ".join([_lit(v) for v in row]) + ")" for row in values
    )
    return (
        f"MERGE INTO DOCUMENTS AS t USING (SELECT * FROM VALUES\n{values_sql}\n) AS s({', '.join(cols)}) "
        "ON t.SOURCE_ID = s.SOURCE_ID AND t.SOURCE_VERSION = s.SOURCE_VERSION "
        "WHEN MATCHED THEN UPDATE SET "
        + ", ".join([f"t.{c}=s.{c}" for c in cols])
        + " WHEN NOT MATCHED THEN INSERT (" + ", ".join(cols) + ") VALUES (" + ", ".join([f"s.{c}" for c in cols]) + ");"
    )


def merge_segments_sql(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "-- no rows"
    cols = [
        "DOC_ID", "SEGMENT_ID", "START_MS", "END_MS", "SPEAKER", "TEXT", "TOPICS", "ENTITIES", "SOURCE_REFS", "UPDATED_AT"
    ]
    values = []
    for r in rows:
        vals = [r.get(c.lower()) if c != "UPDATED_AT" else r.get("updated_at") for c in cols]
        values.append(vals)
    values_sql = ",\n".join(
        "(" + ", ".join([_lit(v) for v in row]) + ")" for row in values
    )
    return (
        f"MERGE INTO KB_SEGMENTS AS t USING (SELECT * FROM VALUES\n{values_sql}\n) AS s({', '.join(cols)}) "
        "ON t.DOC_ID = s.DOC_ID AND t.SEGMENT_ID = s.SEGMENT_ID "
        "WHEN MATCHED THEN UPDATE SET "
        + ", ".join([f"t.{c}=s.{c}" for c in cols])
        + " WHEN NOT MATCHED THEN INSERT (" + ", ".join(cols) + ") VALUES (" + ", ".join([f"s.{c}" for c in cols]) + ");"
    )


def _lit(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        import json
        return f"PARSE_JSON('{json.dumps(value)}')"
    s = str(value).replace("'", "''")
    return f"'{s}'"


class SnowflakeClient:
    def __init__(self, cfg: Optional[SnowflakeConfig] = None):
        self.cfg = cfg or load_snowflake_config()

    def execute_sql(self, sql: str) -> None:
        if snowflake is None:
            raise RuntimeError("snowflake-connector-python not installed")
        if not (self.cfg.account and self.cfg.user and self.cfg.password):
            raise RuntimeError("Snowflake credentials missing")
        ctx = snowflake.connect(
            user=self.cfg.user,
            password=self.cfg.password,
            account=self.cfg.account,
            warehouse=self.cfg.warehouse,
            database=self.cfg.database,
            schema=self.cfg.schema,
        )
        try:
            cs = ctx.cursor()
            cs.execute(sql)
        finally:
            ctx.close()

    def search_segments(self, query: str, limit: int = 10) -> str:
        q = query.replace("'", "''")
        return (
            "SELECT DOC_ID, SEGMENT_ID, START_MS, END_MS, SPEAKER, TEXT FROM KB_SEGMENTS "
            f"WHERE TEXT ILIKE '%{q}%' LIMIT {limit}"
        )
