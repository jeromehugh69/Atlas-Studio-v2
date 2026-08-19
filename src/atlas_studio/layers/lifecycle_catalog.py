"""Auditable software-lifecycle and named-agent workflow definitions."""

from __future__ import annotations


HALLUCINATION_CONTROLS = [
    {"id": "missing-input-stop", "control": "Ask for missing requirements", "enforcement": "prompt-and-policy", "effect": "The agent must ask one direct question instead of inventing a requirement."},
    {"id": "tool-boundary", "control": "Server-side tool allow-list", "enforcement": "api", "effect": "Model text cannot grant tools, permissions, network access, or execution authority."},
    {"id": "claim-verification", "control": "Completion-claim detection", "enforcement": "deterministic", "effect": "Unsupported claims that code changed, tests passed, scans completed, or deployments succeeded are marked verification_required."},
    {"id": "source-grounding", "control": "Source-required specialist review", "enforcement": "deterministic", "effect": "Research, legal, compliance, and security conclusions without evidence references are marked verification_required."},
    {"id": "artifact-hashes", "control": "File and change-set hashes", "enforcement": "worker", "effect": "Approved content is bound to pre-change and post-change SHA-256 evidence."},
    {"id": "machine-evidence", "control": "Machine-recorded lifecycle gates", "enforcement": "api", "effect": "Test, Sandbox, and Production gates reject narrative-only completion claims."},
    {"id": "human-approval", "control": "Expiring single-use approval", "enforcement": "api", "effect": "High-risk actions require a payload-bound six-digit user approval."},
    {"id": "independent-review", "control": "Separation of duties", "enforcement": "workflow", "effect": "Forge implementation is independently evaluated by Quanta, Sentinel, Verity, and the user."},
]


AGENT_WORKFLOW_NODES = {
    "Atlas": ["intake", "clarify", "scope", "evidence-inventory", "plan", "user-decision", "delegate", "monitor", "close"],
    "Forge": ["approved-workspace", "inspect", "propose-change-set", "diff-review", "write-approval", "apply", "test-approval", "commit-approval", "handoff"],
    "Sentinel": ["threat-model", "security-scan", "verify-finding", "risk-rate", "recommend", "retest", "security-gate"],
    "Verity": ["identify-obligations", "map-controls", "collect-evidence", "assess-gaps", "review-remediation", "compliance-gate"],
    "Quanta": ["test-plan", "unit-test", "integration-test", "regression-test", "performance-test", "record-results", "quality-gate"],
    "Sage": ["research-question", "source-plan", "egress-approval", "primary-sources", "compare", "limitations", "research-handoff"],
    "Counsel": ["issue-spot", "jurisdiction", "authoritative-sources", "license-and-terms", "risk-summary", "human-legal-review"],
    "Scribe": ["approved-inputs", "draft", "technical-review", "source-links", "user-approval", "publish"],
    "Pixel": ["visual-brief", "rights-check", "local-generation", "review", "user-approval", "publish-asset"],
    "Blueprint": ["constraints", "current-state", "options", "architecture", "data-flow", "risk-review", "decision-record"],
    "Nexus": ["contract", "schema", "errors", "authorization", "compatibility", "integration-test", "handoff"],
    "DataCore": ["data-model", "migration-plan", "backup-check", "migration-test", "approval", "execute", "integrity-verify"],
    "Interface": ["user-flow", "design", "accessibility", "approved-implementation", "browser-test", "review", "handoff"],
    "Release": ["release-plan", "build", "sandbox-deploy", "observe", "production-approval", "production-deploy", "verify-or-rollback"],
    "Echo": ["voice-requirements", "asset-consent", "local-pipeline", "latency-test", "experience-review", "user-activation"],
}


AGENT_OUTPUTS = {
    "Atlas": ["approved scope", "plan", "delegation record", "closure record"],
    "Forge": ["change set", "combined diff", "test evidence", "local branch and commit"],
    "Sentinel": ["threat model", "verified findings", "security gate decision"],
    "Verity": ["control map", "evidence register", "compliance decision"],
    "Quanta": ["test plan", "machine results", "quality gate decision"],
    "Sage": ["source register", "research brief", "limitations"],
    "Counsel": ["legal issue register", "license review", "human-review flags"],
    "Scribe": ["versioned documentation", "source links", "approval record"],
    "Pixel": ["local visual artifact", "rights record", "approval record"],
    "Blueprint": ["architecture diagram", "data flow", "decision record"],
    "Nexus": ["API contract", "compatibility report", "integration evidence"],
    "DataCore": ["migration", "backup evidence", "integrity report"],
    "Interface": ["user flow", "accessible UI change", "browser evidence"],
    "Release": ["release artifact", "deployment evidence", "rollback record"],
    "Echo": ["voice configuration", "latency evidence", "activation record"],
}


def agent_workflow_definitions() -> list[dict]:
    return [
        {
            "id": f"agent-{name.casefold()}-workflow",
            "name": f"{name} governed workflow",
            "version": 1,
            "owner": name,
            "status": "defined",
            "source_type": "platform_policy",
            "nodes": nodes,
            "outputs": AGENT_OUTPUTS[name],
            "hallucination_controls": [item["id"] for item in HALLUCINATION_CONTROLS],
            "audit_events": ["task.create", "workflow.started", "grounding.evaluate", "task.execute"],
            "description": f"Evidence-first, policy-gated workflow for {name}. Every execution records task, grounding, outcome, and timing evidence.",
        }
        for name, nodes in AGENT_WORKFLOW_NODES.items()
    ]


LIFECYCLE_ACCEPTANCE_CASE = {
    "id": "tc-lifecycle-001",
    "name": "Approved software change from intake through Production",
    "objective": "Prove that a user-owned change is researched, designed, implemented, independently tested, security reviewed, promoted, and fully auditable without trusting unsupported model claims.",
    "preconditions": [
        "Ollama, worker, PostgreSQL, and Redis report healthy",
        "Forge model is installed",
        "kill switch is released",
        "user can complete six-digit approval challenges",
    ],
    "steps": [
        {"stage": "intake", "owners": ["Atlas"], "action": "Clarify the request and create a plan.", "evidence": ["plan.create"]},
        {"stage": "research", "owners": ["Sage", "Counsel", "Verity"], "action": "Collect approved sources, licensing, and applicable controls.", "evidence": ["source register", "grounding.evaluate"]},
        {"stage": "architecture", "owners": ["Blueprint", "Nexus", "DataCore", "Interface"], "action": "Define architecture, APIs, data, and user flow.", "evidence": ["decision record", "task.execute"]},
        {"stage": "authorization", "owners": ["Atlas", "User"], "action": "Review the plan and authorize an isolated workspace.", "evidence": ["approval.request", "approval.decision", "plan.decision"]},
        {"stage": "development", "owners": ["Forge", "Scribe", "Pixel", "Echo"], "action": "Produce a reviewable change set and approved artifacts.", "evidence": ["forge.change_set.propose", "forge.change_set.apply", "SHA-256 hashes"]},
        {"stage": "test", "owners": ["Quanta"], "action": "Run unit, integration, regression, security, and performance checks.", "evidence": ["forge.change_set.test", "exit code 0", "lifecycle.transition"]},
        {"stage": "sandbox", "owners": ["Sentinel", "Verity", "Release"], "action": "Verify security, compliance, deployment, and rollback in Sandbox.", "evidence": ["security decision", "sandbox evidence", "lifecycle.transition"]},
        {"stage": "production", "owners": ["User", "Release"], "action": "Approve and perform Production promotion, then verify or roll back.", "evidence": ["production_promotion approval", "lifecycle.transition", "release evidence"]},
        {"stage": "closure", "owners": ["Atlas"], "action": "Confirm evidence completeness and close the plan.", "evidence": ["completed lifecycle", "audit coverage report"]},
    ],
    "negative_tests": [
        "Missing requirements cause a direct question, not an inferred choice.",
        "Unsupported completion claims are marked verification_required.",
        "A write without its exact approval is rejected.",
        "A Test promotion without machine-recorded implementation evidence is rejected.",
        "A Sandbox promotion without passing test or security evidence is rejected.",
        "A Production promotion without a single-use user approval is rejected.",
    ],
    "pass_criteria": [
        "Every stage contains its required evidence.",
        "Every participating agent has task and grounding audit events.",
        "No lifecycle gate accepts narrative-only evidence.",
        "The final audit coverage report has no missing required event categories.",
    ],
}


AUDIT_COVERAGE = [
    {"area": "intake and planning", "events": ["plan.create", "plan.decision"]},
    {"area": "agent execution", "events": ["task.create", "workflow.started", "grounding.evaluate", "task.execute"]},
    {"area": "authorization", "events": ["approval.request", "approval.decision"]},
    {"area": "implementation", "events": ["forge.change_set.propose", "forge.change_set.file_view", "forge.change_set.apply", "forge.change_set.test", "forge.change_set.commit"]},
    {"area": "lifecycle gates", "events": ["lifecycle.create", "lifecycle.transition"]},
    {"area": "tools and worker", "events": ["worker.preview_write", "worker.file_write", "worker.code_execute", "worker.test_execute"]},
    {"area": "security operations", "events": ["agent.permissions.update", "platform.kill_switch", "external.request", "external.decision"]},
    {"area": "artifacts and knowledge", "events": ["artifact.upload", "source.addition.request", "workflow.request", "workflow.definition.create"]},
]


def lifecycle_governance_catalog() -> dict:
    return {
        "acceptance_test": LIFECYCLE_ACCEPTANCE_CASE,
        "agent_workflows": agent_workflow_definitions(),
        "hallucination_controls": HALLUCINATION_CONTROLS,
        "audit_coverage": AUDIT_COVERAGE,
    }
