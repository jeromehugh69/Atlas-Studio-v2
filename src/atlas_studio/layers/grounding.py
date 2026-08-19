"""Deterministic post-generation checks for unsupported agent claims."""

from __future__ import annotations

import re


SOURCE_REQUIRED_AGENTS = frozenset({"Sage", "Counsel", "Verity", "Sentinel"})
COMPLETION_CLAIM = re.compile(
    r"\b(?:i|we)\s+(?:changed|modified|implemented|deployed|deleted|created|wrote|executed|ran|tested|verified)\b"
    r"|\b(?:tests?|deployment|migration|scan|build)\s+(?:passed|completed|succeeded|finished)\b",
    re.IGNORECASE,
)
def evaluate_grounding(agent_name: str, output: str, evidence_refs: list[str] | None = None) -> dict:
    evidence = [str(item) for item in (evidence_refs or []) if str(item).strip()]
    issues: list[str] = []
    if COMPLETION_CLAIM.search(output or "") and not evidence:
        issues.append("A completion claim has no machine-recorded tool, artifact, test, or deployment evidence.")
    if agent_name in SOURCE_REQUIRED_AGENTS and len((output or "").strip()) >= 80 and not evidence:
        issues.append(f"{agent_name} produced a specialist conclusion without a recorded source reference.")
    status = "verification_required" if issues else "grounded" if evidence else "not_applicable"
    return {"status": status, "issues": issues, "evidence_refs": evidence}
