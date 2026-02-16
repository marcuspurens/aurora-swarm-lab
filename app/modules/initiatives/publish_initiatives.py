"""Publish initiatives to Snowflake (MVP, SQL-only)."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.snowflake_client import SnowflakeClient
from app.queue.logs import log_run


def _lit(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return f"PARSE_JSON('{json.dumps(value)}')"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def publish(scores: List[Dict], report: str, client: SnowflakeClient | None = None) -> Dict[str, object]:
    client = client or SnowflakeClient()
    run_id = log_run(lane="io", component="initiative_publish", input_json={"count": len(scores)})

    rows_sql = ",\n".join(
        "(" + ", ".join(
            [
                _lit(s.get("initiative_id")),
                _lit(s.get("title")),
                _lit(s.get("scores")),
                _lit(s.get("overall_score")),
                _lit(s.get("rationale")),
                _lit(s.get("citations", [])),
            ]
        ) + ")"
        for s in scores
    )
    sql_scores = (
        "CREATE TABLE IF NOT EXISTS INITIATIVES ("
        "INITIATIVE_ID STRING, TITLE STRING, SCORES VARIANT, OVERALL_SCORE NUMBER, RATIONALE STRING, CITATIONS VARIANT, UPDATED_AT TIMESTAMP_NTZ);\n"
        "MERGE INTO INITIATIVES AS t USING (SELECT * FROM VALUES\n"
        f"{rows_sql}\n"
        ") AS s(INITIATIVE_ID, TITLE, SCORES, OVERALL_SCORE, RATIONALE, CITATIONS) "
        "ON t.INITIATIVE_ID = s.INITIATIVE_ID "
        "WHEN MATCHED THEN UPDATE SET t.TITLE=s.TITLE, t.SCORES=s.SCORES, t.OVERALL_SCORE=s.OVERALL_SCORE, "
        "t.RATIONALE=s.RATIONALE, t.CITATIONS=s.CITATIONS, t.UPDATED_AT=CURRENT_TIMESTAMP() "
        "WHEN NOT MATCHED THEN INSERT (INITIATIVE_ID, TITLE, SCORES, OVERALL_SCORE, RATIONALE, CITATIONS, UPDATED_AT) "
        "VALUES (s.INITIATIVE_ID, s.TITLE, s.SCORES, s.OVERALL_SCORE, s.RATIONALE, s.CITATIONS, CURRENT_TIMESTAMP());\n"
    )

    sql_report = (
        "CREATE TABLE IF NOT EXISTS INITIATIVE_REPORTS ("
        "REPORT_ID STRING, REPORT_TEXT STRING, CREATED_AT TIMESTAMP_NTZ);\n"
        "INSERT INTO INITIATIVE_REPORTS (REPORT_ID, REPORT_TEXT, CREATED_AT) VALUES "
        f"({_lit('report_' + str(len(scores)))}, {_lit(report)}, CURRENT_TIMESTAMP());"
    )

    receipt = {"scores_sql": sql_scores, "report_sql": sql_report, "error": None}
    try:
        client.execute_sql(sql_scores)
        client.execute_sql(sql_report)
    except Exception as exc:
        receipt["error"] = str(exc)

    log_run(lane="io", component="initiative_publish", input_json={"run_id": run_id}, output_json=receipt, error=receipt["error"])
    return receipt
