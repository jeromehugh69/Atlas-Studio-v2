from fastapi.testclient import TestClient
from atlas_studio.layers.grounding import evaluate_grounding
from atlas_studio.layers.lifecycle_catalog import (
    AGENT_WORKFLOW_NODES,
    LIFECYCLE_ACCEPTANCE_CASE,
    agent_workflow_definitions,
    lifecycle_governance_catalog,
)
from atlas_studio.main import app, approval_service, store
from atlas_studio.models import DevelopmentLifecycle, Plan, ProtectedActionRequest, Task


client = TestClient(app)


def test_every_named_agent_has_a_governed_workflow():
    named_agents = {agent.name for agent in store.agents.values() if agent.system}
    workflows = {workflow["owner"] for workflow in agent_workflow_definitions()}
    assert named_agents == workflows
    assert all(AGENT_WORKFLOW_NODES[name] for name in named_agents)


def test_lifecycle_case_covers_start_to_finish_and_every_agent():
    stages = [step["stage"] for step in LIFECYCLE_ACCEPTANCE_CASE["steps"]]
    assert stages == ["intake", "research", "architecture", "authorization", "development", "test", "sandbox", "production", "closure"]
    participating_agents = {owner for step in LIFECYCLE_ACCEPTANCE_CASE["steps"] for owner in step["owners"] if owner != "User"}
    assert participating_agents == set(AGENT_WORKFLOW_NODES)
    assert len(LIFECYCLE_ACCEPTANCE_CASE["negative_tests"]) >= 6


def test_unsupported_completion_claim_requires_verification():
    result = evaluate_grounding("Forge", "I implemented the requested change and the tests passed.")
    assert result["status"] == "verification_required"
    assert result["issues"]


def test_specialist_conclusion_requires_sources():
    output = "The assessed control environment satisfies every applicable obligation and contains no material security gap in the reviewed design."
    result = evaluate_grounding("Sentinel", output)
    assert result["status"] == "verification_required"


def test_machine_evidence_grounds_completion_claim():
    result = evaluate_grounding("Forge", "I implemented the approved change.", ["change-set:123"])
    assert result == {"status": "grounded", "issues": [], "evidence_refs": ["change-set:123"]}


def test_governance_api_exposes_live_audit_coverage_without_inventing_activity():
    response = client.get("/api/lifecycle/governance")
    assert response.status_code == 200
    body = response.json()
    assert body["acceptance_test"]["id"] == "tc-lifecycle-001"
    assert len(body["agent_workflows"]) == len(AGENT_WORKFLOW_NODES)
    assert body["logging"]["configured"] is True
    assert all("observed_events" in area and "missing_events" in area for area in body["audit_coverage"])
    assert "not occurred" in body["logging"]["note"]


def test_catalog_defines_audit_coverage_for_all_control_areas():
    catalog = lifecycle_governance_catalog()
    areas = {item["area"] for item in catalog["audit_coverage"]}
    assert {"intake and planning", "agent execution", "authorization", "implementation", "lifecycle gates", "tools and worker", "security operations", "artifacts and knowledge"} == areas


def test_machine_evidence_and_user_approval_gate_the_full_environment_lifecycle():
    forge = next(agent for agent in store.agents.values() if agent.name == "Forge")
    plan = Plan(title="Lifecycle acceptance", request="Verify all governed environment gates", implementation_agent_id=forge.id, status="in_progress")
    lifecycle = DevelopmentLifecycle(plan_id=plan.id, title=plan.title)
    implementation = Task(
        title="Approved implementation", prompt=plan.request, agent_id=forge.id,
        model="local-test-model", status="completed", plan_id=plan.id,
        grounding_status="grounded", evidence_refs=["change-set:test"],
    )
    store.plans[plan.id] = plan
    store.lifecycles[lifecycle.id] = lifecycle
    store.tasks[implementation.id] = implementation
    lifecycle.evidence.append({"stage": "development", "type": "implementation", "status": "passed", "source": "automated-test"})
    try:
        to_test = client.post(
            f"/api/lifecycles/{lifecycle.id}/transition",
            json={"target_stage": "test", "evidence": "Approved change set exists", "evidence_type": "implementation", "task_id": str(implementation.id)},
        )
        assert to_test.status_code == 200
        lifecycle.evidence.append({"stage": "test", "type": "test", "status": "passed", "source": "automated-test", "exit_code": 0})
        to_sandbox = client.post(
            f"/api/lifecycles/{lifecycle.id}/transition",
            json={"target_stage": "sandbox", "evidence": "Automated suite passed", "evidence_type": "test", "task_id": str(implementation.id)},
        )
        assert to_sandbox.status_code == 200
        production_payload = {"target_stage": "production", "evidence": "Sandbox verification passed", "evidence_type": "sandbox"}
        approval = approval_service.request(ProtectedActionRequest(
            action="production_promotion", purpose="Lifecycle acceptance production gate",
            target=str(lifecycle.id), actor="local-user", payload=production_payload,
        ))
        approval_service.decide(approval.id, "approved", passcode_verified=True)
        to_production = client.post(
            f"/api/lifecycles/{lifecycle.id}/transition",
            json={**production_payload, "user_authorized": True, "approval_id": str(approval.id)},
        )
        assert to_production.status_code == 200
        assert to_production.json()["stage"] == "production"
        assert to_production.json()["status"] == "completed"
        transitions = [event for event in store.audit if event.action == "lifecycle.transition" and event.target == str(lifecycle.id)]
        assert [event.outcome for event in reversed(transitions)] == ["test", "sandbox", "production"]
    finally:
        store.tasks.pop(implementation.id, None)
        store.lifecycles.pop(lifecycle.id, None)
        store.plans.pop(plan.id, None)
        store.external_approvals.pop(approval.id, None) if "approval" in locals() else None
