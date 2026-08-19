import json
from collections import deque
from pathlib import Path
from uuid import UUID

from .models import Agent, AuditEvent, ChangeSet, DevelopmentLifecycle, ExternalActionApproval, LibraryChange, Plan, PlanWorkspace, Task, WorkflowDefinition


DEFAULT_AGENTS = [
    Agent(id=UUID("10000000-0000-0000-0000-000000000001"), name="Atlas", role="Platform Intelligence Orchestrator", description="Receives the user's direction, maintains read-only platform awareness, and coordinates approved work without holding implementation permissions.", tools=["diagnostics", "research", "investigation", "memory_read", "files_read"], read_only=True, system=True, skills=["development_lifecycle", "atlas_request_intake", "manage_atlas_platform"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000002"), name="Forge", role="Platform Development AI", description="Primary implementation assistant. Builds and changes platform components only after explicit user authorization and only inside isolated workspaces.", tools=["memory_read", "files_read", "files_write", "code_execute", "test_execute"], requires_user_authorization=True, system=True, skills=["development_lifecycle"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000003"), name="Sentinel", role="Security Engineering", description="Performs threat modeling, secure-code review, dependency analysis, vulnerability triage, and hardening guidance.", tools=["diagnostics", "investigation", "memory_read", "files_read", "security_scan"], read_only=True, requires_user_authorization=True, system=True, skills=["development_lifecycle"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000004"), name="Verity", role="GRC and Compliance", description="Maps controls, evaluates governance and risk, prepares evidence, and reviews compliance obligations for the platform.", tools=["research", "investigation", "memory_read", "files_read", "compliance_review", "document_generate"], read_only=True, system=True, skills=["development_lifecycle"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000005"), name="Quanta", role="Quality and Test Engineering", description="Designs test plans, creates authorized automated tests, validates releases, and tracks regressions and quality gates.", tools=["diagnostics", "memory_read", "files_read", "files_write", "code_execute", "test_execute", "browser"], requires_user_authorization=True, system=True, skills=["development_lifecycle"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000006"), name="Sage", role="Research and Development", description="Investigates technologies, evaluates technical options, runs approved experiments, and turns findings into product recommendations.", tools=["research", "investigation", "memory_read", "files_read", "browser"], read_only=True, system=True, skills=["sage_research"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000007"), name="Counsel", role="AI Legal Advisor", description="Provides legal issue spotting, licensing review, policy research, and draft guidance for qualified human review.", tools=["research", "memory_read", "files_read", "legal_review", "document_generate"], read_only=True, system=True, skills=["counsel_legal"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000008"), name="Scribe", role="Document Engineering", description="Creates technical documentation, operating procedures, specifications, reports, and release documentation from approved sources.", tools=["memory_read", "files_read", "files_write", "document_generate"], requires_user_authorization=True, system=True, skills=["scribe_documents"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000009"), name="Pixel", role="Image and Visual Generation", description="Produces approved interface concepts, product imagery, diagrams, and visual assets through configured local image models.", tools=["memory_read", "files_read", "files_write", "image_generate"], requires_user_authorization=True, system=True, skills=["pixel_visual"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000010"), name="Blueprint", role="Architecture and Blueprint Generation", description="Designs system architecture, data flows, infrastructure diagrams, implementation plans, and engineering blueprints.", tools=["research", "memory_read", "files_read", "document_generate", "blueprint_generate"], read_only=True, system=True, skills=["blueprint_architecture"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000011"), name="Nexus", role="API and Integration Engineering", description="Designs provider-neutral APIs, contracts, connectors, and integration boundaries for authorized implementation.", tools=["memory_read", "files_read", "files_write", "code_execute", "test_execute"], requires_user_authorization=True, system=True, skills=["nexus_integration"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000012"), name="DataCore", role="Data Engineering", description="Designs schemas, migrations, semantic-memory pipelines, retention controls, and safe data operations.", tools=["memory_read", "files_read", "files_write", "code_execute", "database_admin"], requires_user_authorization=True, system=True, skills=["datacore_data"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000013"), name="Interface", role="UX and Frontend Engineering", description="Designs accessible product experiences and implements approved frontend components and interaction systems.", tools=["research", "memory_read", "files_read", "files_write", "code_execute", "browser", "test_execute"], requires_user_authorization=True, system=True, skills=["interface_ux"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000014"), name="Release", role="DevOps and Reliability", description="Maintains build, deployment, observability, recovery, and release processes under explicit user authorization.", tools=["diagnostics", "memory_read", "files_read", "files_write", "code_execute", "deployment"], requires_user_authorization=True, system=True, skills=["development_lifecycle"]),
    Agent(id=UUID("10000000-0000-0000-0000-000000000015"), name="Echo", role="Voice and Experience Coordinator", description="Coordinates local speech, voice-session behavior, and approved avatar experiences for Atlas Studio.", tools=["speech", "avatar", "memory_read", "files_read"], read_only=True, system=True, skills=["echo_voice"]),
]


class MemoryStore:
    """Development-safe store; PostgreSQL remains the production persistence layer."""
    def __init__(self):
        self.agents = {a.id: a for a in DEFAULT_AGENTS}
        self.tasks: dict[UUID, Task] = {}
        self.plans: dict[UUID, Plan] = {}
        self.lifecycles: dict[UUID, DevelopmentLifecycle] = {}
        self.library_changes: dict[UUID, LibraryChange] = {}
        self.external_approvals: dict[UUID, ExternalActionApproval] = {}
        self.plan_workspaces: dict[UUID, PlanWorkspace] = {}
        self.change_sets: dict[UUID, ChangeSet] = {}
        self.workflow_definitions: dict[tuple[str, int], WorkflowDefinition] = {}
        self.audit: deque[AuditEvent] = deque(maxlen=1000)

    def log(self, event: AuditEvent):
        self.audit.appendleft(event)


class ArtifactStore:
    ALLOWED = {
        ".txt", ".md", ".json", ".csv", ".pdf", ".rtf", ".odt",
        ".docx", ".xlsx", ".pptx",
        ".png", ".jpg", ".jpeg", ".webp",
        ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
        ".yaml", ".yml", ".toml", ".sql", ".sh", ".ps1",
        ".glb", ".gltf", ".wav", ".mp3",
    }

    def __init__(self, root: Path, max_mb: int):
        self.root = root.resolve()
        self.max_bytes = max_mb * 1024 * 1024
        self.root.mkdir(parents=True, exist_ok=True)

    def validate(self, filename: str, size: int) -> Path:
        clean = Path(filename).name
        if clean != filename or not clean or Path(clean).suffix.lower() not in self.ALLOWED:
            raise ValueError("unsupported or unsafe filename")
        if size > self.max_bytes:
            raise ValueError("upload exceeds configured size limit")
        destination = (self.root / clean).resolve()
        if self.root not in destination.parents:
            raise ValueError("path traversal rejected")
        return destination
