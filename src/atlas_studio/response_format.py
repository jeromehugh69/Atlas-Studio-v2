from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentResponse:
    """Standardized agent response format for Atlas Studio.

    All agents must use this format for structured outputs to ensure
    consistency, auditability, and machine-parseability.
    """

    request: str
    interpretation: str
    evidence: list[str] = field(default_factory=list)
    action_taken: str = ""
    verification: str = ""
    audit: str = ""

    # Optional fields
    approval_required: Optional[str] = None
    next_steps: list[str] = field(default_factory=list)
    delegation: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dictionary format."""
        result = {
            "REQUEST": self.request,
            "INTERPRETATION": self.interpretation,
            "EVIDENCE": self.evidence,
            "ACTION_TAKEN": self.action_taken,
            "VERIFICATION": self.verification,
            "AUDIT": self.audit,
        }

        if self.approval_required:
            result["APPROVAL_REQUIRED"] = self.approval_required

        if self.next_steps:
            result["NEXT"] = self.next_steps

        if self.delegation:
            result["DELEGATION"] = self.delegation

        if self.metadata:
            result["METADATA"] = self.metadata

        return result

    def to_markdown(self) -> str:
        """Convert response to markdown format for display."""
        lines = []

        lines.append(f"**REQUEST:** {self.request}")
        lines.append(f"**INTERPRETATION:** {self.interpretation}")

        if self.evidence:
            lines.append("**EVIDENCE:**")
            for item in self.evidence:
                lines.append(f"- {item}")

        if self.action_taken:
            lines.append(f"**ACTION TAKEN:** {self.action_taken}")

        if self.verification:
            lines.append(f"**VERIFICATION:** {self.verification}")

        if self.audit:
            lines.append(f"**AUDIT:** {self.audit}")

        if self.approval_required:
            lines.append(f"**APPROVAL REQUIRED:** {self.approval_required}")

        if self.next_steps:
            lines.append("**NEXT:**")
            for step in self.next_steps:
                lines.append(f"- {step}")

        if self.delegation:
            lines.append(f"**DELEGATION:** {self.delegation}")

        return "\n".join(lines)

    def to_compact(self) -> str:
        """Convert response to compact format for logging."""
        parts = [
            f"REQ={self.request}",
            f"INT={self.interpretation}",
            f"EVD={len(self.evidence)} items",
            f"ACT={self.action_taken}",
            f"VER={self.verification}",
            f"AUD={self.audit}",
        ]

        if self.approval_required:
            parts.append(f"APR={self.approval_required}")

        if self.delegation:
            parts.append(f"DEL={self.delegation}")

        return " | ".join(parts)


def create_response(
    request: str,
    interpretation: str,
    evidence: list[str] | None = None,
    action_taken: str = "",
    verification: str = "",
    audit: str = "",
    approval_required: str | None = None,
    next_steps: list[str] | None = None,
    delegation: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentResponse:
    """Create a standardized agent response."""
    return AgentResponse(
        request=request,
        interpretation=interpretation,
        evidence=evidence or [],
        action_taken=action_taken,
        verification=verification,
        audit=audit,
        approval_required=approval_required,
        next_steps=next_steps or [],
        delegation=delegation,
        metadata=metadata or {},
    )


def create_delegation_response(
    original_request: str,
    interpretation: str,
    target_skill: str,
    reason: str,
    context: dict[str, Any] | None = None,
) -> AgentResponse:
    """Create a response indicating delegation to another skill."""
    return AgentResponse(
        request=original_request,
        interpretation=interpretation,
        evidence=[],
        action_taken=f"Delegated to {target_skill}",
        verification="Delegation recorded",
        audit="",
        delegation=f"{target_skill}: {reason}",
        metadata=context or {},
    )


def create_approval_response(
    request: str,
    interpretation: str,
    approval_required: str,
    evidence: list[str] | None = None,
) -> AgentResponse:
    """Create a response requiring user approval."""
    return AgentResponse(
        request=request,
        interpretation=interpretation,
        evidence=evidence or [],
        action_taken="Awaiting user approval",
        verification="",
        audit="",
        approval_required=approval_required,
    )


def create_evidence_response(
    request: str,
    interpretation: str,
    evidence: list[str],
    action_taken: str = "",
    verification: str = "",
    audit: str = "",
) -> AgentResponse:
    """Create a response with evidence (for completion claims)."""
    return AgentResponse(
        request=request,
        interpretation=interpretation,
        evidence=evidence,
        action_taken=action_taken,
        verification=verification,
        audit=audit,
    )
