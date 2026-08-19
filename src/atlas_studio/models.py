import hashlib
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


ToolId = Literal[
    "diagnostics", "research", "investigation", "memory_read", "files_read",
    "files_write", "code_execute", "browser", "speech", "avatar",
    "avatar_generate", "security_scan", "compliance_review", "legal_review",
    "test_execute", "document_generate", "image_generate", "blueprint_generate",
    "deployment", "database_admin",
]


class Agent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=2, max_length=60)
    role: str
    description: str
    tools: list[ToolId]
    read_only: bool = False
    requires_user_authorization: bool = False
    system: bool = False
    skills: list[str] = Field(default_factory=lambda: ["development_lifecycle"])


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    role: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=10, max_length=1_000)
    tools: list[ToolId] = Field(default_factory=lambda: ["memory_read", "files_read"])
    read_only: bool = True
    requires_user_authorization: bool = True
    approval_id: UUID | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    role: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, min_length=10, max_length=1_000)
    tools: list[ToolId] | None = None
    skills: list[str] | None = None
    read_only: bool | None = None
    requires_user_authorization: bool | None = None
    approval_id: UUID | None = None


class ToolAccessRequest(BaseModel):
    agent_id: UUID | None = None
    environment: Literal["workspace", "sandbox", "production"] = "workspace"
    reason: str = Field(default="Developer requested capability review", min_length=5, max_length=500)


class SourceAdditionRequest(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    authority: str = Field(min_length=2, max_length=200)
    source_type: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=3, max_length=1_000)
    jurisdiction: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=100)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=50_000)
    agent_id: UUID
    model: str | None = None
    user_authorized: bool = False
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    plan_id: UUID | None = None
    workspace_id: UUID | None = None


class AtlasIntakeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=50_000)
    title: str | None = Field(default=None, max_length=200)


class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    prompt: str
    agent_id: UUID
    model: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    user_authorized: bool = False
    attempt: int = Field(default=0, ge=0)
    plan_id: UUID | None = None
    workspace_id: UUID | None = None
    output: str | None = None
    reasoning: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    grounding_status: Literal["pending", "grounded", "verification_required", "blocked", "not_applicable"] = "pending"
    grounding_issues: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class PlanCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    request: str = Field(min_length=5, max_length=50_000)
    implementation_agent_id: UUID | None = None
    priority: Literal["critical", "high", "normal", "low"] = "high"


class Plan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    request: str
    implementation_agent_id: UUID
    priority: Literal["critical", "high", "normal", "low"] = "high"
    steps: list[str] = Field(default_factory=lambda: [
        "Atlas scopes the requested change",
        "User approves the implementation plan",
        "Forge implements in Development",
        "Quanta validates in Test",
        "Sentinel and Quanta validate in Sandbox",
        "User authorizes Production promotion",
    ])
    status: Literal["pending_approval", "approved", "rejected", "in_progress", "completed", "deleted"] = "pending_approval"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
    workspace_id: UUID | None = None
    recommendation: str = "Forge recommends a scoped, reviewable change in an isolated workspace. Exact files remain unconfirmed until read-only inspection is complete."
    impact: str = "User-visible behavior and platform controls must remain backward compatible unless the user approves otherwise."
    test_plan: str = "Run the repository test suite, focused regression checks, and lifecycle governance validation in Test."
    rollback_plan: str = "Retain the reviewed diff and prior file hashes so the change can be rejected or reverted before Production."
    proposed_files: list[str] = Field(default_factory=list, max_length=40)


class PlanRecommendationUpdate(BaseModel):
    recommendation: str = Field(min_length=10, max_length=5_000)
    impact: str = Field(min_length=5, max_length=2_000)
    test_plan: str = Field(min_length=5, max_length=2_000)
    rollback_plan: str = Field(min_length=5, max_length=2_000)
    proposed_files: list[str] = Field(default_factory=list, max_length=40)
    reason: str = Field(default="User edited the Forge recommendation", min_length=5, max_length=1_000)


class PlanReviewerRequest(BaseModel):
    agent_id: UUID
    focus: str = Field(default="Provide an additional lifecycle review", min_length=5, max_length=2_000)


class PlanDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="User decision", min_length=2, max_length=1_000)
    user_authorized: bool = False
    approval_passcode: str = Field(default="", max_length=200)
    approval_id: UUID | None = None


class LifecycleCreate(BaseModel):
    plan_id: UUID


class LifecycleTransition(BaseModel):
    target_stage: Literal["development", "test", "sandbox", "production"]
    user_authorized: bool = False
    evidence: str = Field(default="", max_length=2_000)
    evidence_type: Literal["implementation", "test", "security", "sandbox", "release"]
    task_id: UUID | None = None
    approval_id: UUID | None = None


class LifecycleOverride(BaseModel):
    target_environment: Literal["workspace", "sandbox", "production"]
    reason: str = Field(min_length=10, max_length=2_000)
    approval_id: UUID | None = None


class LifecycleNotificationDecision(BaseModel):
    status: Literal["acknowledged", "dismissed"]


class DevelopmentLifecycle(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    title: str
    stage: Literal["development", "test", "sandbox", "production"] = "development"
    status: Literal["active", "blocked", "completed"] = "active"
    gates: dict[str, str] = Field(default_factory=lambda: {
        "development": "active",
        "test": "locked",
        "sandbox": "locked",
        "production": "locked",
    })
    evidence: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LibraryChangeRequest(BaseModel):
    action: Literal["add", "update", "remove"]
    tool_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=10, max_length=1_000)
    reason: str = Field(min_length=5, max_length=1_000)


class LibraryChange(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    action: Literal["add", "update", "remove"]
    tool_id: str
    name: str
    description: str
    reason: str
    status: Literal["pending_security_review", "approved", "rejected"] = "pending_security_review"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowRequestCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    goal: str = Field(min_length=10, max_length=2_000)
    owner: str = Field(min_length=2, max_length=60)
    references: list[str] = Field(default_factory=list, max_length=20)


class WorkflowDefinitionCreate(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    name: str = Field(min_length=3, max_length=120)
    owner: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=10, max_length=2_000)
    nodes: list[str] = Field(min_length=1, max_length=30)
    source_type: Literal["manual", "local_library", "existing_skill", "external_resource"] = "manual"
    source_reference: str = Field(default="", max_length=2_000)
    approval_id: UUID | None = None


class WorkflowDefinition(BaseModel):
    id: str
    version: int = Field(default=1, ge=1)
    name: str
    owner: str
    description: str
    nodes: list[str] = Field(default_factory=list)
    status: Literal["requested", "pending_security_review", "designed", "active", "disabled"] = "requested"
    source_type: Literal["request", "manual", "local_library", "existing_skill", "external_resource"] = "request"
    source_reference: str = ""
    active: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkerActionRequest(BaseModel):
    agent_id: UUID
    action: Literal["preview_write", "file_write", "code_execute", "test_execute"]
    path: str = Field(default="", max_length=1_000)
    content: str | None = Field(default=None, max_length=2_000_000)
    expected_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    command: list[str] = Field(default_factory=list, max_length=32)
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    user_authorized: bool = False
    approval_passcode: str = Field(default="", max_length=200)
    approval_id: UUID | None = None
    workspace_id: UUID | None = None


class PlanWorkspace(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    root: str
    status: Literal["creating", "ready", "blocked", "archived"] = "creating"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChangeSetFile(BaseModel):
    path: str = Field(min_length=1, max_length=1_000)
    content: str = Field(max_length=2_000_000)
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    before_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    after_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    diff: str = Field(default="", max_length=250_000)


class ChangeSet(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    plan_id: UUID
    workspace_id: UUID
    title: str = Field(min_length=2, max_length=200)
    summary: str = Field(min_length=2, max_length=2_000)
    files: list[ChangeSetFile] = Field(min_length=1, max_length=40)
    combined_diff: str = Field(default="", max_length=1_000_000)
    status: Literal["pending_review", "applied", "tests_passed", "committed", "rejected", "failed"] = "pending_review"
    test_result: dict = Field(default_factory=dict)
    branch: str = ""
    commit: str = ""
    removed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChangeSetApproval(BaseModel):
    approval_id: UUID
    user_authorized: bool = False


class ChangeSetTestRequest(ChangeSetApproval):
    command: list[str] = Field(default_factory=lambda: ["python", "-m", "pytest", "-q"], min_length=1, max_length=16)
    timeout_seconds: int = Field(default=180, ge=1, le=300)


class QaPipelineRunRequest(BaseModel):
    plan_id: UUID
    workspace_id: UUID
    approval_id: UUID
    timeout_seconds: Literal[300] = 300


class ChangeSetCommitRequest(ChangeSetApproval):
    branch: str = Field(pattern=r"^atlas/[a-z0-9][a-z0-9._/-]{1,100}$")
    message: str = Field(min_length=5, max_length=500)


ProtectedAction = Literal["file_write", "code_execute", "test_execute", "internet_search", "docker_action", "agent_permission", "source_approval", "sandbox_promotion", "production_promotion", "lifecycle_override", "avatar_delete", "workflow_definition", "change_set_apply", "change_set_delete", "git_commit", "plan_decision", "plan_delete", "plan_intake"]


class ExternalActionRequest(BaseModel):
    action: ProtectedAction
    purpose: str = Field(min_length=5, max_length=1_000)
    query: str = Field(default="", max_length=2_000)
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    ttl_minutes: int = Field(default=15, ge=1, le=60)


class ExternalActionApproval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    action: ProtectedAction
    purpose: str
    target: str = ""
    actor: str = "Atlas"
    payload: dict = Field(default_factory=dict)
    action_hash: str = ""
    query: str = ""
    allowed_domains: list[str] = Field(default_factory=list)
    status: Literal["pending", "approved", "rejected", "used", "expired"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    decided_at: datetime | None = None
    used_at: datetime | None = None


class ApprovalChallengeResponse(ExternalActionApproval):
    challenge_code: str = Field(pattern=r"^\d{6}$")


class ExternalActionDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    user_authorized: bool = False
    reason: str = Field(default="User decision", min_length=2, max_length=1_000)
    approval_passcode: str = Field(default="", max_length=200)


class ApprovedSearchRequest(BaseModel):
    approval_id: UUID


class ProtectedActionRequest(BaseModel):
    action: ProtectedAction
    purpose: str = Field(min_length=5, max_length=1_000)
    target: str = Field(default="", max_length=1_000)
    actor: str = Field(default="Atlas", min_length=2, max_length=100)
    payload: dict = Field(default_factory=dict)
    ttl_minutes: int = Field(default=15, ge=1, le=60)


class SpeechSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)


class AuditEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    action: str
    actor: str
    target: str
    outcome: str
    details: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    previous_hash: str = ""
    current_hash: str = ""

    def compute_hash(self) -> str:
        data = f"{self.action}{self.actor}{self.target}{self.outcome}{self.created_at}{self.previous_hash}"
        self.current_hash = hashlib.sha256(data.encode()).hexdigest()
        return self.current_hash


class AvatarGeneration(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    provider: str = "triposr+blender-local"
    provider_task_id: str
    agent_id: UUID
    status: Literal["queued", "running", "completed", "failed", "removed"] = "queued"
    progress: int = Field(0, ge=0, le=100)
    message: str = "Queued for local generation"
    artifact_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
