"""Initiative scoring pipeline (MVP)."""

from __future__ import annotations

import json
from typing import Dict, List

from app.modules.initiatives.intake_initiative import intake
from app.modules.initiatives.score_initiatives import score
from app.modules.initiatives.c_level_report import build_report
from app.modules.initiatives.publish_initiatives import publish
from app.queue.logs import log_run


def run_pipeline(payloads: List[Dict]) -> Dict[str, object]:
    run_id = log_run(lane="nemotron", component="initiative_pipeline", input_json={"count": len(payloads)})
    initiatives = [intake(p) for p in payloads]
    scores = score(initiatives)
    report = build_report(scores)
    receipt = publish(scores, report)
    log_run(
        lane="nemotron",
        component="initiative_pipeline",
        input_json={"run_id": run_id},
        output_json={"scored": len(scores), "published": receipt.get("error") is None},
        error=receipt.get("error"),
    )
    return {"scores": scores, "report": report, "receipt": receipt}


def run_pipeline_from_json(path: str) -> Dict[str, object]:
    data = json.loads(open(path, "r", encoding="utf-8").read())
    if not isinstance(data, list):
        raise ValueError("Expected a list of initiatives")
    return run_pipeline(data)
