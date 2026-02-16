"""C-level report generation."""

from __future__ import annotations

from typing import List, Dict


def build_report(scores: List[Dict]) -> str:
    if not scores:
        return "# C-level Report\n\nNo initiatives scored."
    ordered = sorted(scores, key=lambda s: float(s.get("overall_score", 0)), reverse=True)
    lines = ["# C-level Report", "", "## Top initiatives"]
    for item in ordered[:5]:
        lines.append(
            f"- {item.get('title')} (score {item.get('overall_score')}) — {item.get('rationale', '')}"
        )
    lines.append("")
    lines.append("## Risks and mitigations")
    lines.append("- Pending detailed risk review; use compliance checklist per initiative.")
    lines.append("")
    lines.append("## Recommended next actions")
    lines.append("- Approve top 1-2 initiatives for discovery and scope validation.")
    return "\n".join(lines)
