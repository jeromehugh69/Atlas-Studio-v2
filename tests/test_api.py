import os
from pathlib import Path
import tempfile
from typing import get_args
from uuid import UUID, uuid4

import pytest

os.environ["ATLAS_STUDIO_ARTIFACT_ROOT"] = str(Path(tempfile.gettempdir()) / "atlas-studio-test-artifacts")

from fastapi.testclient import TestClient
import atlas_studio.main as main_module
from atlas_studio.main import app, settings
from atlas_studio.models import Agent, AvatarGeneration, ChangeSet, ChangeSetFile, DevelopmentLifecycle, Plan, PlanWorkspace, ProtectedActionRequest, Task, ToolId
from atlas_studio.workspace_browser import WorkspaceBrowser


client = TestClient(app)


def test_liveness_and_local_config():
    assert client.get("/api/health/live").json()["status"] == "ok"
    config = client.get("/api/config").json()
    assert config["mode"] == "community"
    assert config["provider"] == "ollama"
    assert config["forge_model"] == "qwen3:4b"
    assert config["forge_runtime"] == {
        "timeout_seconds": 300,
        "max_tokens": 2048,
        "context_tokens": 4096,
    }
    assert config["telemetry"] is False


def test_protected_approval_issues_a_random_six_digit_one_time_challenge():
    request = {
        "action": "plan_decision", "purpose": "Approve a local implementation plan",
        "target": "plan-test", "actor": "local-user", "payload": {"decision": "approved", "reason": "test"},
    }
    first = client.post("/api/approvals", json=request)
    second = client.post("/api/approvals", json={**request, "target": "plan-test-two"})
    assert first.status_code == second.status_code == 202
    code = first.json()["challenge_code"]
    assert len(code) == 6 and code.isdigit()
    assert len(second.json()["challenge_code"]) == 6 and second.json()["challenge_code"].isdigit()
    decision = client.post(
        f"/api/approvals/{first.json()['id']}/decision",
        json={"decision": "approved", "user_authorized": True, "approval_passcode": code, "reason": "test"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"


def test_metrics_api_reports_operational_domains(monkeypatch):
    async def model_is_ready():
        return True

    monkeypatch.setattr(main_module.gateway.get(), "healthy", model_is_ready)
    response = client.get("/api/metrics")
    assert response.status_code == 200
    metrics = response.json()
    assert {"platform", "services", "tasks", "agents", "model", "security", "storage", "runtime", "tools", "audit"}.issubset(metrics)
    assert metrics["platform"]["local_only"] is True
    assert metrics["security"]["atlas_read_only"] is True
    assert metrics["agents"]["total"] >= 15
    assert metrics["model"]["provider"] == "ollama"


def test_all_agents_are_named_and_atlas_is_read_only():
    agents = client.get("/api/agents").json()
    assert all(agent["name"] for agent in agents)
    atlas = next(agent for agent in agents if agent["name"] == "Atlas")
    assert atlas["read_only"] is True
    assert "files_write" not in atlas["tools"]
    assert "code_execute" not in atlas["tools"]
    assert {"Forge", "Sentinel", "Verity", "Quanta", "Sage", "Counsel", "Scribe", "Pixel", "Blueprint"}.issubset({agent["name"] for agent in agents})
    forge = next(agent for agent in agents if agent["name"] == "Forge")
    assert forge["role"] == "Platform Development AI"
    assert forge["requires_user_authorization"] is True


def test_atlas_routes_scoped_read_only_qa_request_to_quanta():
    atlas = next(agent for agent in main_module.store.agents.values() if agent.name == "Atlas")
    specialist = main_module.delegated_read_only_specialist(
        atlas,
        "I need QA to inspect the light/dark toggle button in read-only mode, determine why it fails, and report.",
    )
    assert specialist is not None
    assert specialist.name == "Quanta"
    assert main_module.delegated_read_only_specialist(atlas, "Please change the light theme") is None
    assert main_module.delegated_read_only_specialist(
        atlas,
        "Recent conversation context:\nUSER: QA should test the theme in read-only mode.\n\nATLAS: Report complete.\n\nCURRENT USER REQUEST:\nThanks.",
    ) is None
    continued = main_module.delegated_read_only_specialist(
        atlas,
        "Recent conversation context:\nUSER: QA should test the light/dark toggle in read-only mode and report why it fails."
        "\n\nATLAS: Please confirm.\n\nCURRENT USER REQUEST:\nI am authorized. Proceed.",
    )
    assert continued is not None and continued.name == "Quanta"


def test_qa_page_exposes_approved_full_pipeline_control():
    page = client.get("/static/index.html")
    script = client.get("/static/developer-features.js")
    assert page.status_code == script.status_code == 200
    assert "Run full QA pipeline" in script.text
    assert "/api/qa/pipeline-runs" in script.text
    assert "qa-pipeline:" in script.text
    assert '["python", "-m", "pytest", "-q"]' in script.text


def test_atlas_delegates_read_only_site_inspection_to_interface():
    atlas = next(agent for agent in main_module.store.agents.values() if agent.name == "Atlas")
    specialist = main_module.delegated_read_only_specialist(
        atlas, "Inspect the dashboard UI in read-only mode and report why the theme toggle does not respond."
    )
    assert specialist is not None
    assert specialist.name == "Interface"


@pytest.mark.asyncio
async def test_atlas_delegates_read_only_qa_without_reconfirmation(monkeypatch):
    atlas = next(agent for agent in main_module.store.agents.values() if agent.name == "Atlas")
    task = Task(
        title="Theme QA",
        prompt="QA must test the light/dark toggle feature in read-only mode and determine why it is occurring.",
        agent_id=atlas.id,
        model="local-test",
    )
    events = []

    async def specialist_run(**_kwargs):
        return "Finding: the handler is missing. Recommended next step: request a Forge plan.", ["workspace:src/atlas_studio/static/app.js:10"]

    async def capture(event):
        events.append(event)

    async def persist(_item):
        return None

    monkeypatch.setattr(main_module.read_only_specialist_loop, "run", specialist_run)
    monkeypatch.setattr(main_module, "broadcast", capture)
    monkeypatch.setattr(main_module.infrastructure, "persist_task", persist)
    monkeypatch.setattr(main_module.infrastructure, "persist_audit", persist)
    main_module.store.tasks[task.id] = task
    try:
        await main_module.execute(task)
    finally:
        main_module.store.tasks.pop(task.id, None)

    assert task.status == "completed"
    assert task.grounding_status == "grounded"
    assert task.evidence_refs == ["workspace:src/atlas_studio/static/app.js:10"]
    assert task.output.startswith("Quanta read-only QA report")
    delegated = next(event for event in events if event["type"] == "task.delegated")
    assert delegated["from_agent"] == "Atlas"
    assert delegated["to_agent"] == "Quanta"
    assert delegated["mode"] == "read_only"
    specialist_audit = next(event for event in main_module.store.audit if event.action == "specialist.investigate" and event.target == str(task.id))
    assert specialist_audit.actor == "Quanta"
    assert specialist_audit.outcome == "completed"
    assert specialist_audit.details["mutations_allowed"] is False


@pytest.mark.asyncio
async def test_quanta_full_pipeline_runs_complete_suite_in_test_workspace(monkeypatch):
    quanta = next(agent for agent in main_module.store.agents.values() if agent.name == "Quanta")
    plan_id = uuid4()
    workspace_id = uuid4()
    lifecycle = DevelopmentLifecycle(plan_id=plan_id, title="Theme lifecycle", stage="test")
    main_module.store.lifecycles[lifecycle.id] = lifecycle

    async def execute_worker(payload):
        assert payload == {
            "action": "test_execute", "workspace_id": str(workspace_id), "path": ".",
            "command": ["python", "-m", "pytest", "-q"], "timeout_seconds": 300,
        }
        return {"exit_code": 0, "stdout": "42 passed", "stderr": "", "duration_ms": 1250}

    async def persist(_item):
        return None

    monkeypatch.setattr(main_module.implementation_worker, "execute", execute_worker)
    monkeypatch.setattr(main_module.infrastructure, "persist_lifecycle", persist)
    monkeypatch.setattr(main_module.infrastructure, "persist_audit", persist)
    try:
        result = await main_module.run_model_step({
            "task_id": str(uuid4()), "run_id": str(uuid4()), "agent_id": str(quanta.id),
            "agent_name": "Quanta", "prompt": "[FULL_QA_PIPELINE]\nRun all tests.", "model": "local-test",
            "plan_id": str(plan_id), "workspace_id": str(workspace_id), "user_authorized": True,
        })
    finally:
        main_module.store.lifecycles.pop(lifecycle.id, None)

    assert result["status"] == "completed"
    assert result["grounding_status"] == "grounded"
    assert "42 passed" in result["output"]
    assert lifecycle.evidence[-1]["source"] == "quanta-full-pipeline"
    assert lifecycle.evidence[-1]["status"] == "passed"


def test_atlas_cannot_receive_implementation_tools():
    atlas = next(agent for agent in client.get("/api/agents").json() if agent["name"] == "Atlas")
    response = client.patch(f"/api/agents/{atlas['id']}", json={"tools": ["diagnostics", "files_write"]})
    assert response.status_code == 422


def test_agent_metadata_edit_requires_exact_approval_and_is_audited():
    agent = Agent(
        name="EditTest", role="Test operator",
        description="Temporary agent used to verify guarded metadata editing.",
        tools=["memory_read"], read_only=True, requires_user_authorization=True, system=False,
    )
    main_module.store.agents[agent.id] = agent
    changes = {"role": "Lifecycle test operator", "tools": ["memory_read", "files_read"]}
    try:
        blocked = client.patch(f"/api/agents/{agent.id}", json=changes)
        assert blocked.status_code == 403
        approval = main_module.approval_service.request(ProtectedActionRequest(
            action="agent_permission", purpose="Update test agent", target=str(agent.id),
            actor="local-user", payload=changes,
        ))
        main_module.approval_service.decide(approval.id, "approved", passcode_verified=True)
        updated = client.patch(f"/api/agents/{agent.id}", json={**changes, "approval_id": str(approval.id)})
        assert updated.status_code == 200
        assert updated.json()["role"] == changes["role"]
        assert main_module.store.audit[0].action == "agent.update"
        assert set(main_module.store.audit[0].details["changed_fields"]) == set(changes)
    finally:
        main_module.store.agents.pop(agent.id, None)


def test_environment_swimlane_move_requires_override_approval_and_audit():
    lifecycle = DevelopmentLifecycle(plan_id=uuid4(), title="Swimlane override test")
    main_module.store.lifecycles[lifecycle.id] = lifecycle
    payload = {"target_environment": "sandbox", "reason": "User accepts bypassing the normal lifecycle gates for this local test."}
    try:
        blocked = client.post(f"/api/lifecycles/{lifecycle.id}/override", json=payload)
        assert blocked.status_code == 403
        approval = main_module.approval_service.request(ProtectedActionRequest(
            action="lifecycle_override", purpose="Move test project to Sandbox",
            target=str(lifecycle.id), actor="local-user", payload=payload,
        ))
        main_module.approval_service.decide(approval.id, "approved", passcode_verified=True)
        moved = client.post(
            f"/api/lifecycles/{lifecycle.id}/override",
            json={**payload, "approval_id": str(approval.id)},
        )
        assert moved.status_code == 200
        assert moved.json()["stage"] == "sandbox"
        assert moved.json()["gates"]["production"] == "locked"
        assert moved.json()["evidence"][-1]["status"] == "overridden"
        assert main_module.store.audit[0].action == "lifecycle.override"
        assert main_module.store.audit[0].details["from_stage"] == "development"
    finally:
        main_module.store.lifecycles.pop(lifecycle.id, None)


def test_task_requires_known_agent():
    response = client.post("/api/tasks", json={"title": "test", "prompt": "hello", "agent_id": "00000000-0000-0000-0000-000000000099"})
    assert response.status_code == 404


def test_implementation_agents_require_explicit_user_authorization():
    forge = next(agent for agent in client.get("/api/agents").json() if agent["name"] == "Forge")
    response = client.post("/api/tasks", json={"title": "implementation", "prompt": "change the platform", "agent_id": forge["id"]})
    assert response.status_code == 403
    assert "explicit user authorization" in response.json()["detail"]


def test_user_can_add_a_named_agent_with_scoped_tools():
    payload = {
        "name": "Meridian",
        "role": "Privacy Engineering",
        "description": "Reviews privacy controls and data handling boundaries.",
        "tools": ["memory_read", "files_read", "compliance_review"],
        "read_only": True,
        "requires_user_authorization": True,
    }
    approval = client.post("/api/approvals", json={
        "action": "agent_permission", "purpose": "Create the scoped Meridian agent",
        "target": "new:Meridian", "actor": "local-user", "payload": payload,
    })
    assert approval.status_code == 202
    decision = client.post(
        f"/api/approvals/{approval.json()['id']}/decision",
        json={
            "decision": "approved", "user_authorized": True,
            "approval_passcode": approval.json()["challenge_code"], "reason": "test",
        },
    )
    assert decision.status_code == 200
    response = client.post("/api/agents", json={**payload, "approval_id": approval.json()["id"]})
    assert response.status_code == 201
    agent = response.json()
    assert agent["name"] == "Meridian"
    assert agent["system"] is False
    assert agent["requires_user_authorization"] is True


def test_upload_rejects_path_traversal_and_executables():
    response = client.post("/api/artifacts", files={"file": ("../malware.exe", b"bad", "application/octet-stream")})
    assert response.status_code == 422


def test_text_upload_returns_local_context_for_agent_analysis():
    response = client.post(
        "/api/artifacts",
        files={"file": ("atlas-notes.txt", b"Priority: inspect the local queue.", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["context"] == "Priority: inspect the local queue."


def test_source_code_upload_returns_bounded_local_context():
    response = client.post(
        "/api/artifacts",
        files={"file": ("auth_flow.py", b"def authorize(user):\n    return user.is_admin\n", "text/x-python")},
    )
    assert response.status_code == 200
    assert "def authorize(user)" in response.json()["context"]


def test_speech_proxy_validates_audio_before_contacting_worker():
    response = client.post(
        "/api/speech/transcribe",
        files={"audio": ("turn.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 422


def test_speech_proxy_is_optional_when_local_worker_is_absent(monkeypatch):
    monkeypatch.setattr(settings, "stt_url", "")
    response = client.post(
        "/api/speech/transcribe",
        files={"audio": ("turn.webm", b"voice", "audio/webm")},
    )
    assert response.status_code == 503


def test_speech_synthesis_rejects_empty_text():
    response = client.post("/api/speech/synthesize", json={"text": ""})
    assert response.status_code == 422


def test_live_atlas_page_exposes_global_conversation_launcher():
    page = client.get("/static/live-atlas.html")
    assert page.status_code == 200
    assert "Open conversation" in page.text
    assert "/static/atlas-widget.js" in page.text


def test_atlas_popup_is_available_across_product_pages():
    for path in ("/static/index.html", "/static/avatar-station.html", "/static/live-atlas.html"):
        page = client.get(path)
        assert page.status_code == 200
        assert "/static/atlas-widget.css" in page.text
        assert "/static/atlas-widget.js" in page.text

    panel = client.get("/static/atlas-chat-panel.html")
    assert panel.status_code == 200
    assert "conversation transcript" in panel.text.lower()
    assert "ATLAS AI ASSISTANT" in panel.text
    assert "TEST VOICE WITH ATLAS" in panel.text
    assert "Start Voice Test" in panel.text
    assert "Attach images or documents" in panel.text
    assert "Attach code or workspace context" in panel.text


def test_atlas_popup_launcher_uses_face_and_right_drawer():
    widget = client.get("/static/atlas-widget.js")
    styles = client.get("/static/atlas-widget.css")
    assert widget.status_code == styles.status_code == 200
    assert "atlas_portrait.png" in widget.text
    assert "atlas-widget-drawer" in widget.text
    assert 'right: 18px' in styles.text


def test_command_dashboard_exposes_the_complete_engineering_workspace():
    page = client.get("/static/index.html")
    script = client.get("/static/app.js")
    styles = client.get("/static/dashboard-widgets.css")
    assert page.status_code == script.status_code == styles.status_code == 200
    assert 'id="atlasCommandFrame"' in page.text
    assert "/static/atlas-chat-panel.html?embedded=1" in page.text
    for label in ("Overview", "Workspace Explorer", "AI Agents", "ACTIVE TASKS", "ATLAS STATUS", "Connected Tools", "Add agent"):
        assert label in page.text
    assert "User → Atlas → Forge" in page.text
    assert "initializeAgentCreator" in script.text


def test_implementation_page_exposes_governed_forge_change_set_review():
    page = client.get("/static/index.html")
    script = client.get("/static/developer-features.js")
    styles = client.get("/static/dashboard-widgets.css")
    assert page.status_code == script.status_code == styles.status_code == 200
    assert 'id="forgeChangeSets"' in page.text
    assert "Review and approve write" in script.text
    assert "Approve test run" in script.text
    assert "Approve branch and commit" in script.text
    assert "change_set_apply" in script.text
    assert "git_commit" in script.text
    assert ".command-cockpit" in styles.text


def test_overview_cards_are_reorderable_accessible_and_persisted():
    page = client.get("/static/index.html")
    script = client.get("/static/app.js")
    styles = client.get("/static/developer-features.css")

    assert 'id="commandDashboard"' in page.text
    assert 'id="resetDashboardLayout"' in page.text
    for widget_id in ("task-orchestrator", "active-tasks", "atlas-status"):
        assert f'data-widget-id="{widget_id}"' in page.text
    assert page.text.count('class="widget-handle"') == 3
    assert 'aria-grabbed="false"' in page.text
    assert "DASHBOARD_LAYOUT_KEY" in script.text
    assert "localStorage.setItem" in script.text
    assert "pointerdown" in script.text
    assert "moveCommandWidgetByKeyboard" in script.text
    assert ".dashboard-widget.is-moving" in styles.text


def test_langgraph_workflow_layer_is_visible_and_registered():
    page = client.get("/static/index.html")
    script = client.get("/static/app.js")
    workflow = client.get("/api/workflows")

    assert workflow.status_code == 200
    data = workflow.json()
    assert data["engine"] == "LangGraph OSS"
    assert any(item["id"] == "governed-agent-task" and item["status"] == "active" for item in data["definitions"])
    rd = next(item for item in data["definitions"] if item["id"] == "research-and-development-delivery")
    assert "egress-approval" in rd["nodes"]
    assert "isolated-prototype" in rd["nodes"]
    assert {"Sage", "Forge", "Quanta", "Sentinel"}.issubset(rd["agents"])
    assert 'data-view="workflows"' in page.text
    assert 'id="workflowDefinitions"' in page.text
    assert "refreshWorkflows" in script.text


def test_security_layer_has_a_dedicated_tab_and_enforced_policy():
    page = client.get("/static/index.html")
    script = client.get("/static/app.js")
    posture = client.get("/api/security/posture")

    assert posture.status_code == 200
    data = posture.json()
    assert data["status"] == "enforced"
    assert data["controls"]["atlas_read_only"] is True
    assert data["controls"]["sandbox_network"] == "none"
    assert data["sentinel"]["name"] == "Sentinel"
    assert {layer["id"] for layer in data["layers"]} >= {"agent-policy", "authorization", "workspace", "sandbox", "uploads", "audit"}
    assert 'data-view="security"' in page.text
    assert 'id="securityLayers"' in page.text
    assert "refreshSecurity" in script.text


def test_custom_implementation_agent_cannot_bypass_authorization():
    response = client.post(
        "/api/agents",
        json={
            "name": "Unsafe Builder",
            "role": "Implementation",
            "description": "Attempts to run implementation work without an authorization boundary.",
            "tools": ["files_read", "files_write"],
            "read_only": False,
            "requires_user_authorization": False,
        },
    )
    assert response.status_code == 422
    assert "must require explicit user authorization" in response.json()["detail"]


def test_metrics_board_covers_platform_operations_and_refreshes():
    page = client.get("/static/index.html")
    script = client.get("/static/app.js")
    styles = client.get("/static/dashboard-widgets.css")
    for label in ("Platform Metrics", "Task performance", "Service health", "Model runtime", "Agent governance", "Security posture", "Runtime & storage", "Recent tasks", "Tool coverage", "Recent audit activity"):
        assert label in page.text
    assert "refreshMetrics" in script.text
    assert "'/api/metrics'" in script.text
    assert ".metrics-board" in styles.text


def test_command_dashboard_embeds_continuous_text_and_voice_without_a_popup():
    page = client.get("/static/index.html")
    panel = client.get("/static/atlas-chat-panel.html")
    voice = client.get("/static/live-atlas.js")
    assert 'allow="microphone; autoplay"' in page.text
    assert 'id="textInput"' in panel.text
    assert 'id="micButton"' in panel.text
    assert "embedded" in panel.text
    assert "window.AtlasVoice" in voice.text
    assert "Analyzing workspace" not in panel.text
    assert "Analyzing workspace" not in voice.text
    assert 'id="transcript" class="transcript" aria-label="Conversation transcript" aria-live="polite"></div>' in panel.text
    assert "WORKSPACE ANALYSIS" not in panel.text
    assert "I’ve analyzed the current workspace" not in panel.text
    assert 'addMessage("system"' not in voice.text
    assert "Conversation cleared. I’m ready when you are." not in voice.text


def test_detail_bearing_platform_records_are_selectable():
    page = client.get("/static/index.html")
    app_script = client.get("/static/app.js")
    features = client.get("/static/developer-features.js")
    styles = client.get("/static/developer-features.css")

    assert page.status_code == app_script.status_code == features.status_code == styles.status_code == 200
    assert 'id="recordDetailDialog"' in page.text
    assert 'data-record-kind="agent"' in app_script.text
    for record_kind in ("task", "source", "tool", "plan", "lifecycle", "changeSet"):
        assert f'data-record-kind="{record_kind}"' in features.text
    assert "openRegisteredRecord" in features.text
    assert "openWorkspaceFile" in features.text
    assert ".record-selectable" in styles.text


def test_developer_feature_pages_use_registered_tools_and_real_local_sources():
    page = client.get("/static/index.html")
    script = client.get("/static/developer-features.js")
    styles = client.get("/static/developer-features.css")
    tools = client.get("/api/tool-library")
    sources = client.get("/api/sources")

    assert tools.status_code == 200
    assert {item["id"] for item in tools.json()} == set(get_args(ToolId))
    assert all(item["source"] == "Local Atlas Studio capability registry" for item in tools.json())
    assert all(item["audit_required"] for item in tools.json())
    assert sources.status_code == 200
    assert {item["id"] for item in sources.json()} == {
        "atlas-readme", "atlas-security-policy", "atlas-implementation-record"
    }
    assert client.get("/api/sources/atlas-readme/content").status_code == 200
    for section in ("tasksView", "plans", "implementation", "codeView", "toolsView", "knowledge", "sources", "qa", "sandbox", "environments"):
        assert f'id="{section}"' in page.text
    assert script.status_code == 200
    assert styles.status_code == 200


def test_library_projects_plugins_and_guarded_edit_controls_are_exposed():
    page = client.get("/static/index.html")
    features = client.get("/static/developer-features.js")
    app_script = client.get("/static/app.js")
    plugins = client.get("/api/plugins")

    assert page.status_code == features.status_code == app_script.status_code == plugins.status_code == 200
    for section in ("library", "projects", "plugins"):
        assert f'id="{section}"' in page.text
        assert f'data-view="{section}"' in page.text
    for control in ("profileSettingsForm", "agentEditDialog", "requestSourceChange"):
        assert f'id="{control}"' in page.text
    assert "refreshLibrary" in features.text
    assert "saveAgentEdit" in features.text
    assert "initializeLocalProfile" in app_script.text
    plugin_ids = {plugin["id"] for plugin in plugins.json()}
    assert "manage-atlas-platform" in plugin_ids
    assert all(plugin["network_required"] is False for plugin in plugins.json())
    assert Path("skills/manage-atlas-platform/SKILL.md").is_file()


def test_environments_use_draggable_vertical_swimlanes_with_override_modal():
    page = client.get("/static/index.html").text
    script = client.get("/static/developer-features.js").text
    styles = client.get("/static/developer-features.css").text

    assert 'id="environmentSwimlanes"' in page
    assert 'id="environmentOverrideDialog"' in page
    assert "Workspace" in page and "Sandbox" in page and "Production" in page
    assert 'draggable="true"' in script
    assert "submitEnvironmentOverride" in script
    assert 'action: "lifecycle_override"' in script
    assert ".environment-swimlanes { display: grid" in styles
    assert "grid-template-columns: repeat(3" in styles


def test_workspace_explorer_opens_real_project_files_in_read_only_code_view(tmp_path, monkeypatch):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "router.py").write_text("def route():\n    return 'local'\n", encoding="utf-8")
    monkeypatch.setattr(main_module, "workspace_browser", WorkspaceBrowser(tmp_path))

    tree = client.get("/api/workspace/tree")
    source = client.get("/api/workspace/file", params={"path": "backend/router.py"})
    page = client.get("/static/index.html")
    script = client.get("/static/developer-features.js")

    assert tree.status_code == 200
    assert tree.json()["entries"][0]["path"] == "backend"
    assert source.status_code == 200
    assert source.json()["content"].startswith("def route")
    assert source.json()["read_only"] is True
    for element_id in ("workspaceTree", "workspaceBreadcrumb", "codeViewer", "codeFileName"):
        assert f'id="{element_id}"' in page.text
    assert "openWorkspaceFile" in script.text
    assert 'data-view="codeView"' in script.text


def test_tool_and_source_requests_never_silently_grant_authority():
    tool_request = client.post(
        "/api/tool-library/deployment/request",
        json={"environment": "production", "reason": "Review production deployment access"},
    )
    source_request = client.post(
        "/api/sources/requests",
        json={
            "name": "Example policy",
            "authority": "Example organization",
            "source_type": "Organization policy",
            "location": "policies/example.md",
        },
    )

    assert tool_request.status_code == 200
    assert tool_request.json()["status"] == "administrative_review_required"
    assert tool_request.json()["capability_granted"] is False
    assert source_request.status_code == 202
    assert source_request.json()["status"] == "pending_provenance_review"
    assert source_request.json()["source_approved"] is False


def test_worker_and_external_routes_require_visible_passcode_approval():
    forge = next(agent for agent in client.get("/api/agents").json() if agent["name"] == "Forge")
    plan_workspace = PlanWorkspace(plan_id=uuid4(), root="/workspaces/test", status="ready")
    main_module.store.plan_workspaces[plan_workspace.id] = plan_workspace
    blocked = client.post(
        "/api/worker/actions",
        json={
            "agent_id": forge["id"], "action": "file_write", "path": "README.md",
            "content": "write without a scoped approval", "user_authorized": True,
            "workspace_id": str(plan_workspace.id),
        },
    )
    main_module.store.plan_workspaces.pop(plan_workspace.id, None)
    request = client.post(
        "/api/external-approvals",
        json={"action": "internet_search", "purpose": "Verify official documentation", "query": "FastAPI security", "allowed_domains": ["fastapi.tiangolo.com"]},
    )
    approval_id = request.json()["id"]
    denied = client.post(
        f"/api/external-approvals/{approval_id}/decision",
        json={"decision": "approved", "user_authorized": True, "approval_passcode": "wrong", "reason": "test"},
    )
    page = client.get("/static/index.html").text

    assert blocked.status_code == 403
    assert request.status_code == 202
    assert request.json()["status"] == "pending"
    assert denied.status_code == 403
    assert 'id="approvalPasscodeDialog"' in page
    assert 'id="workerActionForm"' in page
    assert 'id="externalApprovalForm"' in page


def test_runtime_and_identity_controls_are_grouped_under_settings():
    page = client.get("/static/index.html").text
    navigation = page.split('<nav aria-label="Atlas Studio sections">', 1)[1].split("</nav>", 1)[0]
    settings = page.split('<section id="settings"', 1)[1]

    assert 'data-view="sandbox"' not in navigation
    assert 'data-view="environments"' not in navigation
    for label in ("Sandbox settings", "Environment lifecycle", "User profile", "User management", "Google OAuth"):
        assert label in settings


def test_top_navigation_and_workers_share_the_command_center_theme():
    page = client.get("/static/index.html").text
    script = client.get("/static/app.js").text
    styles = client.get("/static/developer-features.css").text

    assert 'class="top-shell"' in page
    assert 'class="top-navigation"' in page
    assert 'class="profile-logo">JH' in page
    assert "Advanced Tooling, Lifecycle Automation, and Security" in page
    assert "Build smarter. Operate safer. Scale confidently." in page
    for category in ("Build", "Intelligence", "Assurance", "Experience"):
        assert f"<summary>{category}</summary>" in page
    assert "Remove current avatar" in script
    assert ".worker-stage { background: #08121f" in styles
    assert 'class="sidebar-profile"' in page
    assert "display: flex !important" in styles


def test_top_dropdowns_open_on_hover_and_close_when_pointer_leaves():
    script = client.get("/static/app.js").text
    styles = client.get("/static/developer-features.css").text

    assert "initializeHoverMenus" in script
    assert "mouseenter" in script and "mouseleave" in script
    assert "focusin" in script and "focusout" in script
    assert ".nav-category > .nav-menu,.profile-menu > .profile-dropdown { display: none; }" in styles
    assert ".nav-category:hover > .nav-menu" in styles
    assert ".profile-menu:hover > .profile-dropdown" in styles


def test_forge_cannot_change_its_permissions_without_exact_user_approval():
    forge = next(agent for agent in client.get("/api/agents").json() if agent["name"] == "Forge")
    requested_tools = ["memory_read", "files_read", "files_write"]
    blocked = client.patch(f"/api/agents/{forge['id']}", json={"tools": requested_tools})

    assert blocked.status_code == 403
    assert "approval" in blocked.json()["detail"]


def test_workflows_can_be_requested_and_manual_definitions_require_approval():
    requested = client.post("/api/workflows/requests", json={
        "name": "Evaluate a local inference library",
        "goal": "Compare performance, security, licensing, and prototype evidence before adoption.",
        "owner": "Sage",
        "references": ["existing-skill:library-review"],
    })
    assert requested.status_code == 202
    assert requested.json()["status"] == "requested"
    assert requested.json()["active"] is False

    payload = {
        "id": "manual-rd-evaluation", "name": "Manual R&D evaluation", "owner": "Sage",
        "description": "Evaluate a source, create an isolated prototype, and record evidence.",
        "nodes": ["scope", "research", "approve", "prototype", "test", "decide"],
        "source_type": "existing_skill", "source_reference": "skill:library-review",
    }
    blocked = client.post("/api/workflows", json=payload)
    assert blocked.status_code == 403

    approval = main_module.approval_service.request(ProtectedActionRequest(
        action="workflow_definition", purpose="Register manual R&D evaluation workflow",
        target=payload["id"], actor="local-user", payload=payload,
    ))
    main_module.approval_service.decide(approval.id, "approved", passcode_verified=True)
    created = client.post("/api/workflows", json={**payload, "approval_id": str(approval.id)})
    assert created.status_code == 201
    assert created.json()["status"] == "pending_security_review"
    assert created.json()["active"] is False


def test_generated_avatar_removal_requires_exact_passcode_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_root", tmp_path)
    atlas = next(agent for agent in main_module.store.agents.values() if agent.name == "Atlas")
    job = AvatarGeneration(provider_task_id="local-test", agent_id=atlas.id, status="completed")
    filename = f"avatar-{job.id}.glb"
    job.artifact_url = f"/artifacts/{filename}"
    (tmp_path / filename).write_bytes(b"glTF-test")
    main_module.avatar_jobs[job.id] = job

    blocked = client.delete(f"/api/avatar-generations/{job.id}")
    assert blocked.status_code == 403
    assert (tmp_path / filename).exists()

    approval = main_module.approval_service.request(ProtectedActionRequest(
        action="avatar_delete", purpose="Delete generated avatar test artifact",
        target=str(job.id), actor="local-user", payload={"artifact_url": job.artifact_url},
    ))
    main_module.approval_service.decide(approval.id, "approved", passcode_verified=True)
    removed = client.delete(f"/api/avatar-generations/{job.id}", params={"approval_id": str(approval.id)})

    assert removed.status_code == 204
    assert not (tmp_path / filename).exists()
    assert job.status == "removed"
    main_module.avatar_jobs.pop(job.id, None)


@pytest.mark.asyncio
async def test_task_execution_streams_incremental_text(monkeypatch):
    atlas = next(agent for agent in main_module.store.agents.values() if agent.name == "Atlas")
    task = Task(title="stream", prompt="hello", agent_id=atlas.id, model="local-test")
    events = []
    captured_messages = []

    async def fake_stream(messages, _model, _temperature=0.3):
        captured_messages.extend(messages)
        yield "Hello"
        yield " from Atlas."

    async def capture(event):
        events.append(event)

    async def persist(_item):
        return None

    monkeypatch.setattr(main_module.gateway.get(), "stream", fake_stream)
    monkeypatch.setattr(main_module, "broadcast", capture)
    monkeypatch.setattr(main_module.infrastructure, "persist_task", persist)
    monkeypatch.setattr(main_module.infrastructure, "persist_audit", persist)

    await main_module.execute(task)

    assert task.status == "completed"
    assert task.output == "Hello from Atlas."
    deltas = [event for event in events if event["type"] == "task.delta"]
    assert [event["text"] for event in deltas] == ["Hello", "Hello from Atlas."]
    assert events[-1]["type"] == "task.progress"
    assert events[-1]["status"] == "completed"
    system_prompt = captured_messages[0]["content"]
    assert "Do not invent facts, files, requirements, results, permissions, or user preferences" in system_prompt
    assert "ask the user a direct question, and wait" in system_prompt


def test_live_atlas_uses_websocket_deltas_and_sentence_voice():
    script = client.get("/static/live-atlas.js")
    assert script.status_code == 200
    assert 'event.type === "task.delta"' in script.text
    assert "createSentenceSpeaker" in script.text
    assert "onSpokenText" in script.text
    assert "showSpokenWords" in script.text
    assert 'fetch("/api/speech/synthesize"' in script.text


def test_lifecycle_guide_exposes_user_next_step_and_editable_forge_recommendation(monkeypatch):
    async def no_new_reviews(*args, **kwargs):
        return []

    monkeypatch.setattr(main_module, "_queue_plan_reviews", no_new_reviews)
    forge = next(agent for agent in main_module.store.agents.values() if agent.name == "Forge")
    plan = Plan(title="Lifecycle guide test", request="Update a governed user interface", implementation_agent_id=forge.id)
    main_module.store.plans[plan.id] = plan
    reviewers = [agent for agent in main_module.store.agents.values() if agent.name in {"Forge", "Sage", "Blueprint", "Sentinel"}]
    review_tasks = []
    try:
        for agent in reviewers:
            task = Task(
                title=f"Lifecycle review — {agent.name}", prompt="[LIFECYCLE_REVIEW] Review",
                agent_id=agent.id, model="local-test", plan_id=plan.id, status="completed",
                output=f"{agent.name} review complete", grounding_status="grounded",
            )
            main_module.store.tasks[task.id] = task
            review_tasks.append(task)
        guide = client.get("/api/lifecycle-guide")
        assert guide.status_code == 200
        entry = next(item for item in guide.json()["entries"] if item["plan"]["id"] == str(plan.id))
        assert entry["next_action"]["id"] == "review-recommendation"
        assert any(stage["id"] == "reviews" and stage["status"] == "completed" for stage in entry["stages"])

        edited = client.patch(f"/api/plans/{plan.id}/recommendation", json={
            "recommendation": "Change only the approved theme controls and preserve existing behavior.",
            "impact": "Visual behavior only; permissions remain unchanged.",
            "test_plan": "Run UI contract and regression tests.",
            "rollback_plan": "Restore the reviewed prior stylesheet and script hashes.",
            "proposed_files": ["src/atlas_studio/static/styles.css"],
            "reason": "User narrowed the requested change.",
        })
        assert edited.status_code == 200
        assert edited.json()["proposed_files"] == ["src/atlas_studio/static/styles.css"]
    finally:
        main_module.store.plans.pop(plan.id, None)
        for task in review_tasks:
            main_module.store.tasks.pop(task.id, None)


def test_lifecycle_request_delete_is_soft_and_requires_exact_approval():
    forge = next(agent for agent in main_module.store.agents.values() if agent.name == "Forge")
    plan = Plan(title="Delete lifecycle request", request="Remove this request from active work", implementation_agent_id=forge.id)
    main_module.store.plans[plan.id] = plan
    payload = {"operation": "soft_delete", "plan_id": str(plan.id), "title": plan.title}
    try:
        blocked = client.delete(f"/api/plans/{plan.id}")
        assert blocked.status_code == 422
        approval = main_module.approval_service.request(ProtectedActionRequest(
            action="plan_delete", purpose="Delete lifecycle request test", target=str(plan.id), actor="local-user", payload=payload,
        ))
        main_module.approval_service.decide(approval.id, "approved", passcode_verified=True)
        deleted = client.delete(f"/api/plans/{plan.id}", params={"approval_id": str(approval.id)})
        assert deleted.status_code == 204
        assert plan.status == "deleted"
        assert all(item["id"] != str(plan.id) for item in client.get("/api/plans").json())
        assert any(event.action == "plan.delete" and event.target == str(plan.id) for event in main_module.store.audit)
    finally:
        main_module.store.plans.pop(plan.id, None)
        main_module.store.external_approvals.pop(approval.id, None) if "approval" in locals() else None


def test_implementation_delete_is_soft_approval_bound_and_audited():
    digest = "0" * 64
    change_set = ChangeSet(
        task_id=uuid4(), plan_id=uuid4(), workspace_id=uuid4(), title="Removable implementation",
        summary="A reviewable implementation record", files=[ChangeSetFile(
            path="example.py", content="print('updated')\n", expected_sha256=digest,
            before_sha256=digest, after_sha256=digest, diff="+print('updated')",
        )],
    )
    main_module.store.change_sets[change_set.id] = change_set
    payload = {"operation": "soft_delete", "change_set_id": str(change_set.id), "plan_id": str(change_set.plan_id), "status": change_set.status}
    try:
        blocked = client.delete(f"/api/change-sets/{change_set.id}")
        assert blocked.status_code == 422
        approval = main_module.approval_service.request(ProtectedActionRequest(
            action="change_set_delete", purpose="Remove implementation test", target=str(change_set.id), actor="local-user", payload=payload,
        ))
        main_module.approval_service.decide(approval.id, "approved", passcode_verified=True)
        removed = client.delete(f"/api/change-sets/{change_set.id}", params={"approval_id": str(approval.id)})
        assert removed.status_code == 204
        assert change_set.removed_at is not None
        assert all(item["id"] != str(change_set.id) for item in client.get("/api/change-sets").json())
        assert any(event.action == "forge.change_set.delete" and event.target == str(change_set.id) for event in main_module.store.audit)
    finally:
        main_module.store.change_sets.pop(change_set.id, None)
        main_module.store.external_approvals.pop(approval.id, None) if "approval" in locals() else None


def test_lifecycle_guide_page_and_shared_agent_skill_are_present():
    page = client.get("/").text
    script = client.get("/static/developer-features.js").text
    assert 'id="lifecycleGuide"' in page
    assert 'id="lifecycleNotificationCount"' in page
    assert "Review Forge recommendation" in page
    assert "Add reviewer" in script
    assert all("development_lifecycle" in agent.skills for agent in main_module.store.agents.values())
    assert (Path("skills") / "development-lifecycle" / "SKILL.md").exists()


def test_atlas_request_intake_classifies_changes_without_generic_questions():
    assert main_module._atlas_change_request("Fix the light and dark mode toggle.") is True
    assert main_module._atlas_change_request("I need the approval popup added to Atlas.") is True
    assert main_module._atlas_change_request("Explain how the current approval flow works.") is False
    assert main_module._atlas_change_request("Can I add another reviewer later?") is False


def test_atlas_change_request_opens_inline_approval_before_creating_plan(monkeypatch):
    async def no_reviews(*args, **kwargs):
        return []

    monkeypatch.setattr(main_module, "_queue_plan_reviews", no_reviews)
    before = set(main_module.store.plans)
    intake = client.post("/api/atlas/intake", json={"prompt": "Add an approval popup to the Atlas chat."})
    assert intake.status_code == 202
    data = intake.json()
    assert data["mode"] == "approval"
    assert data["approval"]["action"] == "plan_intake"
    assert set(main_module.store.plans) == before

    approval_id = data["approval"]["id"]
    decision = client.post(f"/api/approvals/{approval_id}/decision", json={
        "decision": "approved", "user_authorized": True,
        "approval_passcode": data["approval"]["challenge_code"],
        "reason": "Approved in the inline Atlas popup",
    })
    assert decision.status_code == 200
    created = client.post(f"/api/atlas/intake/{approval_id}/approve")
    try:
        assert created.status_code == 201
        assert created.json()["request"] == "Add an approval popup to the Atlas chat."
        assert any(event.action == "atlas.intake.approved" for event in main_module.store.audit)
    finally:
        if created.status_code == 201:
            main_module.store.plans.pop(UUID(created.json()["id"]), None)
        main_module.store.external_approvals.pop(UUID(approval_id), None)


def test_atlas_request_skill_and_inline_modal_are_bundled():
    atlas = next(agent for agent in main_module.store.agents.values() if agent.name == "Atlas")
    assert "atlas_request_intake" in atlas.skills
    assert (Path("skills") / "atlas-request-intake" / "SKILL.md").exists()
    panel = client.get("/static/atlas-chat-panel.html")
    assert panel.status_code == 200
    assert 'id="atlasApprovalDialog"' in panel.text
