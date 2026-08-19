"""Developer-facing catalogs derived from Atlas Studio's real local registries."""

from pathlib import Path
from typing import get_args

from .models import Agent, ToolId


TOOL_METADATA: dict[str, dict] = {
    "diagnostics": {"category": "Observability", "description": "Read local service health, runtime state, and diagnostic signals.", "capabilities": ["Service health", "Runtime diagnostics", "Failure triage"], "data_access": "Local runtime metadata"},
    "research": {"category": "Knowledge", "description": "Investigate approved local and explicitly enabled research sources.", "capabilities": ["Technical research", "Source comparison", "Finding summaries"], "data_access": "Approved knowledge sources"},
    "investigation": {"category": "Development", "description": "Trace platform behavior across tasks, agents, and local runtime evidence.", "capabilities": ["Root-cause analysis", "Task investigation", "Evidence correlation"], "data_access": "Workspace and audit metadata"},
    "memory_read": {"category": "Knowledge", "description": "Retrieve approved semantic memory and workspace context.", "capabilities": ["Memory retrieval", "Context lookup", "Decision recall"], "data_access": "Approved workspace memory"},
    "files_read": {"category": "Code", "description": "Read files inside the active workspace boundary.", "capabilities": ["File inspection", "Code review", "Document reading"], "data_access": "Active workspace files"},
    "files_write": {"category": "Code", "description": "Create or modify files inside an explicitly authorized workspace.", "capabilities": ["File creation", "Code modification", "Patch application"], "data_access": "Authorized workspace files", "risk": "medium"},
    "code_execute": {"category": "Development", "description": "Run approved code in an isolated, resource-limited sandbox.", "capabilities": ["Local execution", "Build commands", "Script validation"], "data_access": "Sandbox workspace", "risk": "high"},
    "browser": {"category": "Development", "description": "Inspect and test approved browser surfaces when enabled.", "capabilities": ["UI inspection", "Local web testing", "Browser diagnostics"], "data_access": "Approved browser page state", "risk": "medium"},
    "speech": {"category": "Automation", "description": "Use the configured local speech-to-text and text-to-speech services.", "capabilities": ["Speech recognition", "Voice synthesis", "Voice-session feedback"], "data_access": "Session audio and transcript"},
    "avatar": {"category": "Automation", "description": "Control approved local avatar presentation and session state.", "capabilities": ["Avatar state", "Presentation control", "Voice synchronization"], "data_access": "Local avatar assets"},
    "avatar_generate": {"category": "Automation", "description": "Request local avatar generation from approved image assets.", "capabilities": ["Image intake", "Local 3D generation", "Artifact review"], "data_access": "User-approved local images", "risk": "medium"},
    "security_scan": {"category": "Security", "description": "Run approved security inspection and dependency-review workflows.", "capabilities": ["Secure-code review", "Dependency analysis", "Finding triage"], "data_access": "Authorized code and dependency metadata"},
    "compliance_review": {"category": "Compliance", "description": "Evaluate implementations against approved compliance sources and controls.", "capabilities": ["Control mapping", "Gap review", "Evidence planning"], "data_access": "Approved policies, controls, and evidence"},
    "legal_review": {"category": "Compliance", "description": "Perform legal issue spotting and licensing review for qualified human review.", "capabilities": ["License review", "Legal research support", "Issue spotting"], "data_access": "Approved legal and project sources"},
    "test_execute": {"category": "Testing", "description": "Run approved unit, integration, and regression tests in a sandbox.", "capabilities": ["Test execution", "Regression validation", "Result capture"], "data_access": "Sandbox code and test results", "risk": "medium"},
    "document_generate": {"category": "Documentation", "description": "Create approved technical documents and engineering artifacts.", "capabilities": ["Document drafting", "Report generation", "Evidence packaging"], "data_access": "Approved task context", "risk": "medium"},
    "image_generate": {"category": "Documentation", "description": "Create approved visual assets through configured local image tooling.", "capabilities": ["Image generation", "Visual concepts", "Asset export"], "data_access": "Approved prompts and references", "risk": "medium"},
    "blueprint_generate": {"category": "Documentation", "description": "Produce architecture diagrams, data flows, and implementation blueprints.", "capabilities": ["Architecture design", "Workflow diagrams", "Implementation planning"], "data_access": "Approved workspace context"},
    "deployment": {"category": "Cloud", "description": "Perform governed release and deployment operations after human authorization.", "capabilities": ["Release preparation", "Deployment execution", "Rollback coordination"], "data_access": "Authorized environment and release metadata", "risk": "critical", "restricted": True},
    "database_admin": {"category": "Database", "description": "Perform governed schema or administrative data operations after authorization.", "capabilities": ["Schema administration", "Migration execution", "Database diagnostics"], "data_access": "Authorized database environment", "risk": "critical", "restricted": True},
}

MUTATING_TOOLS = {
    "files_write", "code_execute", "avatar_generate", "test_execute",
    "document_generate", "image_generate", "deployment", "database_admin",
}

SOURCE_SPECS = (
    {
        "id": "atlas-readme",
        "name": "Atlas Studio README",
        "authority": "Atlas Studio workspace",
        "source_type": "Approved internal documentation",
        "category": "Internal Documentation",
        "hierarchy_level": 5,
        "version": "workspace",
        "filename": "README.md",
        "relevance": ["Setup", "Architecture", "Local operation"],
    },
    {
        "id": "atlas-security-policy",
        "name": "Atlas Studio Security Policy",
        "authority": "Atlas Studio workspace",
        "source_type": "Organization policy",
        "category": "Organization Policy",
        "hierarchy_level": 4,
        "version": "workspace",
        "filename": "SECURITY.md",
        "relevance": ["Security", "Authorization", "Vulnerability handling"],
    },
    {
        "id": "atlas-implementation-record",
        "name": "Atlas Studio Implementation Record",
        "authority": "Atlas Studio workspace",
        "source_type": "Approved internal documentation",
        "category": "Internal Documentation",
        "hierarchy_level": 5,
        "version": "workspace",
        "filename": "IMPLEMENTATION.md",
        "relevance": ["Implementation", "Architecture", "Validation"],
    },
)


def build_tool_catalog(agents: list[Agent]) -> list[dict]:
    """Return catalog metadata only for capabilities registered by ToolId."""
    catalog = []
    for tool_id in get_args(ToolId):
        metadata = TOOL_METADATA[tool_id]
        assigned_agents = sorted(agent.name for agent in agents if tool_id in agent.tools)
        risk = metadata.get("risk", "low")
        restricted = bool(metadata.get("restricted"))
        environments = ["Workspace", "Sandbox"]
        if restricted:
            environments.append("Production with human authorization")
        catalog.append(
            {
                "id": tool_id,
                "name": tool_id.replace("_", " ").title(),
                "category": metadata["category"],
                "description": metadata["description"],
                "provider": "Atlas Studio",
                "version": "Built-in registry",
                "source": "Local Atlas Studio capability registry",
                "source_type": "Internal tool",
                "capabilities": metadata["capabilities"],
                "required_permissions": ["Agent assignment", "Task scope"] + (["Explicit user authorization"] if tool_id in MUTATING_TOOLS else []),
                "environments": environments,
                "allowed_agents": assigned_agents,
                "assigned_count": len(assigned_agents),
                "risk_level": risk,
                "authorization_required": tool_id in MUTATING_TOOLS or restricted,
                "data_access": metadata["data_access"],
                "audit_required": True,
                "trust_level": "platform_verified",
                "runtime_status": "registered",
                "restricted": restricted,
            }
        )
    return catalog


def source_root() -> Path:
    return Path.cwd().resolve()


def build_source_catalog() -> list[dict]:
    """Expose real local project documents without claiming external verification."""
    root = source_root()
    sources = []
    for spec in SOURCE_SPECS:
        path = (root / spec["filename"]).resolve()
        available = root == path.parent and path.is_file()
        sources.append(
            {
                **{key: value for key, value in spec.items() if key != "filename"},
                "location": spec["filename"],
                "status": "current" if available else "unavailable",
                "trust_level": "approved_internal",
                "jurisdiction": "Atlas Studio workspace",
                "effective_date": None,
                "last_verified": "Local runtime check" if available else None,
                "verification_status": "available" if available else "verification_failed",
                "content_url": f"/api/sources/{spec['id']}/content" if available else None,
            }
        )
    return sources


def source_path(source_id: str) -> Path | None:
    spec = next((item for item in SOURCE_SPECS if item["id"] == source_id), None)
    if not spec:
        return None
    root = source_root()
    path = (root / spec["filename"]).resolve()
    return path if path.parent == root and path.is_file() else None
