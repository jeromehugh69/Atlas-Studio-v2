from __future__ import annotations

from collections import Counter
from typing import Any

from ..models import Agent, AuditEvent, ToolId


ATLAS_MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "files_write",
        "code_execute",
        "test_execute",
        "document_generate",
        "image_generate",
        "deployment",
        "database_admin",
    }
)

TOOL_RISK: dict[str, int] = {
    "diagnostics": 0,
    "research": 1,
    "investigation": 0,
    "memory_read": 0,
    "files_read": 0,
    "browser": 1,
    "speech": 1,
    "avatar": 1,
    "avatar_generate": 1,
    "security_scan": 1,
    "compliance_review": 1,
    "legal_review": 1,
    "document_generate": 1,
    "image_generate": 1,
    "blueprint_generate": 1,
    "files_write": 2,
    "code_execute": 2,
    "test_execute": 2,
    "deployment": 3,
    "database_admin": 3,
}


class SecurityPolicy:
    """Central, model-independent authorization rules.

    These checks are intentionally outside prompts.  A model cannot grant
    itself capabilities by changing or ignoring natural-language instructions.
    """

    @staticmethod
    def validate_agent_tools(agent: Agent, requested_tools: list[ToolId]) -> None:
        if agent.name.casefold() == "atlas" and ATLAS_MUTATING_TOOLS.intersection(requested_tools):
            raise ValueError("Atlas is permanently read-only and cannot receive implementation tools")

    @staticmethod
    def risk_tier(tools: list[ToolId]) -> int:
        return max((TOOL_RISK.get(tool, 1) for tool in tools), default=0)

    @staticmethod
    def authorization_required(agent: Agent, tools: list[ToolId] | None = None) -> bool:
        selected = tools if tools is not None else agent.tools
        return agent.requires_user_authorization or SecurityPolicy.risk_tier(selected) >= 2

    @staticmethod
    def task_policy(agent: Agent, user_authorized: bool) -> dict[str, Any]:
        risk = SecurityPolicy.risk_tier(agent.tools)
        required = SecurityPolicy.authorization_required(agent)
        return {
            "allowed": not required or user_authorized,
            "risk_tier": risk,
            "authorization_required": required,
            "atlas_read_only": agent.name.casefold() != "atlas" or agent.read_only,
            "reason": None if (not required or user_authorized) else f"{agent.name} requires explicit user authorization",
        }


def build_security_posture(
    agents: list[Agent],
    audit: list[AuditEvent],
    *,
    sandbox_runtime: str,
    sandbox_network: str,
    telemetry_enabled: bool,
    upload_limit_mb: int,
    workspace_read_only: bool,
    kill_switch_engaged: bool,
) -> dict[str, Any]:
    atlas = next((agent for agent in agents if agent.name == "Atlas"), None)
    violations = []
    if not atlas or not atlas.read_only or ATLAS_MUTATING_TOOLS.intersection(atlas.tools):
        violations.append("Atlas read-only boundary requires review")
    unguarded = [agent.name for agent in agents if not agent.read_only and not agent.requires_user_authorization]
    if unguarded:
        violations.append(f"Implementation authorization missing: {', '.join(unguarded)}")

    outcome_counts = Counter(event.outcome for event in audit)
    layers = [
        {
            "id": "identity",
            "name": "Identity & session",
            "status": "planned",
            "description": "Local identity, session expiry, and CSRF protection before non-loopback access.",
        },
        {
            "id": "agent-policy",
            "name": "Agent permissions",
            "status": "enforced" if not violations else "review",
            "description": "Server-side tool allow-lists, protected Atlas permissions, and named-agent boundaries.",
        },
        {
            "id": "authorization",
            "name": "Human authorization",
            "status": "enforced",
            "description": "Implementation-capable agents cannot start without explicit user authorization.",
        },
        {
            "id": "workspace",
            "name": "Workspace isolation",
            "status": "enforced" if workspace_read_only else "review",
            "description": "Resolved-path containment and a read-only project mount for Atlas visibility.",
        },
        {
            "id": "sandbox",
            "name": "Sandbox execution",
            "status": "enforced" if sandbox_network == "none" else "review",
            "description": f"{sandbox_runtime} runtime with network {sandbox_network}, resource ceilings, and dropped privileges.",
        },
        {
            "id": "uploads",
            "name": "Upload protection",
            "status": "enforced",
            "description": f"Filename, media-type, content, and size validation with a {upload_limit_mb} MB limit.",
        },
        {
            "id": "audit",
            "name": "Audit & evidence",
            "status": "enforced",
            "description": "Agent, task, permission, tool-request, cancellation, and kill-switch events are recorded.",
        },
        {
            "id": "secrets",
            "name": "Secrets & integrations",
            "status": "enforced" if not telemetry_enabled else "review",
            "description": "Optional integrations remain disabled by default; telemetry is off in Community mode.",
        },
    ]
    return {
        "status": "review" if violations else "enforced",
        "summary": "Security policy is enforced by the API, independently of model prompts.",
        "sentinel": next((agent.model_dump(mode="json") for agent in agents if agent.name == "Sentinel"), None),
        "layers": layers,
        "controls": {
            "atlas_read_only": bool(atlas and atlas.read_only and not ATLAS_MUTATING_TOOLS.intersection(atlas.tools)),
            "authorization_gates": sum(agent.requires_user_authorization for agent in agents),
            "sandbox_runtime": sandbox_runtime,
            "sandbox_network": sandbox_network,
            "workspace_read_only": workspace_read_only,
            "telemetry_enabled": telemetry_enabled,
            "kill_switch_engaged": kill_switch_engaged,
            "audit_events": len(audit),
            "denied_events": outcome_counts.get("denied", 0),
        },
        "violations": violations,
        "trust_flow": ["User", "FastAPI policy", "Atlas plan", "Approval gate", "Specialist agent", "Sandbox", "Evidence"],
        "recent_events": [event.model_dump(mode="json") for event in audit[:12]],
    }

