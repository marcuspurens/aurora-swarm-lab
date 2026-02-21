"""Analyze evidence using strong model."""

from __future__ import annotations

from typing import List, Dict

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.models import AnalyzeOutput
from app.core.prompts import render_prompt
from app.core.textnorm import normalize_user_text
from app.modules.privacy.egress_policy import apply_egress_policy
from app.modules.swarm.prompt_format import serialize_for_prompt
from app.queue.logs import log_run


def analyze(question: str, evidence: List[Dict]) -> AnalyzeOutput:
    raw_question = str(question or "")
    question = normalize_user_text(raw_question, max_len=2400)
    evidence_json, evidence_meta = serialize_for_prompt(evidence, max_chars=9000, max_list_items=18, max_text_chars=650)
    settings = load_settings()
    prompt = render_prompt("swarm_analyze", question=question, evidence_json=evidence_json)
    egress = apply_egress_policy(prompt, provider="ollama")
    run_id = log_run(
        lane="nemotron",
        component="swarm_analyze",
        input_json={
            "question": question,
            "question_len_raw": len(raw_question),
            "question_len": len(question),
            "question_truncated": len(question) < len(raw_question),
            "evidence_count": len(evidence),
            "evidence_prompt_chars_raw": evidence_meta.get("chars_raw"),
            "evidence_prompt_chars": evidence_meta.get("chars_final"),
            "evidence_prompt_truncated": evidence_meta.get("truncated"),
            **egress.audit_fields(),
        },
        model=settings.ollama_model_strong,
    )
    try:
        output = generate_json(egress.text, settings.ollama_model_strong, AnalyzeOutput)
        log_run(lane="nemotron", component="swarm_analyze", input_json={"run_id": run_id}, output_json=output.model_dump())
        return output
    except Exception as exc:
        log_run(lane="nemotron", component="swarm_analyze", input_json={"run_id": run_id}, error=str(exc))
        return AnalyzeOutput(claims=[], timeline=[], open_questions=[f"analysis_fallback:{exc}"])
