"""Synthesize an answer with citations."""

from __future__ import annotations

from typing import List, Dict, Optional

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.models import SynthesizeOutput, SynthesizeCitation, AnalyzeOutput
from app.core.prompts import render_prompt
from app.core.textnorm import normalize_user_text
from app.modules.privacy.egress_policy import apply_egress_policy
from app.modules.swarm.prompt_format import serialize_for_prompt
from app.queue.logs import log_run


def synthesize(
    question: str,
    evidence: List[Dict],
    analysis: Optional[AnalyzeOutput] = None,
    use_strong_model: bool = False,
) -> SynthesizeOutput:
    raw_question = str(question or "")
    question = normalize_user_text(raw_question, max_len=2400)
    settings = load_settings()
    model = settings.ollama_model_strong if use_strong_model else settings.ollama_model_fast
    evidence_json, evidence_meta = serialize_for_prompt(evidence, max_chars=9000, max_list_items=20, max_text_chars=700)
    analysis_json, analysis_meta = serialize_for_prompt(
        analysis.model_dump() if analysis else {},
        max_chars=3500,
        max_list_items=20,
        max_text_chars=500,
    )
    prompt = render_prompt(
        "swarm_synthesize",
        question=question,
        evidence_json=evidence_json,
        analysis_json=analysis_json,
    )
    egress = apply_egress_policy(prompt, provider="ollama")
    run_id = log_run(
        lane="nemotron" if use_strong_model else "oss20b",
        component="swarm_synthesize",
        input_json={
            "question": question,
            "question_len_raw": len(raw_question),
            "question_len": len(question),
            "question_truncated": len(question) < len(raw_question),
            "evidence_count": len(evidence),
            "evidence_prompt_chars_raw": evidence_meta.get("chars_raw"),
            "evidence_prompt_chars": evidence_meta.get("chars_final"),
            "evidence_prompt_truncated": evidence_meta.get("truncated"),
            "analysis_prompt_chars_raw": analysis_meta.get("chars_raw"),
            "analysis_prompt_chars": analysis_meta.get("chars_final"),
            "analysis_prompt_truncated": analysis_meta.get("truncated"),
            "use_strong_model": use_strong_model,
            **egress.audit_fields(),
        },
        model=model,
    )
    try:
        output = generate_json(egress.text, model, SynthesizeOutput)
        log_run(
            lane="nemotron" if use_strong_model else "oss20b",
            component="swarm_synthesize",
            input_json={"run_id": run_id},
            output_json=output.model_dump(),
        )
        return output
    except Exception as exc:
        fallback = _fallback_output(question, evidence, exc)
        log_run(
            lane="nemotron" if use_strong_model else "oss20b",
            component="swarm_synthesize",
            input_json={"run_id": run_id},
            output_json=fallback.model_dump(),
            error=str(exc),
        )
        return fallback


def _fallback_output(question: str, evidence: List[Dict], error: Exception) -> SynthesizeOutput:
    snippets: List[str] = []
    citations: List[SynthesizeCitation] = []
    for row in evidence[:3]:
        doc_id = str(row.get("doc_id") or "").strip()
        segment_id = str(row.get("segment_id") or "").strip() or "N/A"
        text = str(row.get("text_snippet") or "").strip()
        if doc_id:
            citations.append(
                SynthesizeCitation(
                    doc_id=doc_id,
                    segment_id=segment_id,
                    start_ms=row.get("start_ms"),
                    end_ms=row.get("end_ms"),
                )
            )
        if text:
            snippets.append(text[:220])

    if snippets:
        body = " ".join(snippets)
    else:
        body = "No evidence snippets available."

    answer = (
        "Fallback answer (model unavailable). "
        f"Question: {question[:240]}. "
        f"Evidence snapshot: {body}. "
        f"Error: {str(error)[:200]}"
    )
    return SynthesizeOutput(answer_text=answer, citations=citations)
