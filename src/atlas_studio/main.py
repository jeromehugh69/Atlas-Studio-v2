import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hmac
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .artifact_context import extract_artifact_context
from .avatar_service import AvatarServiceError, LocalTripoSRProvider
from .catalog import build_source_catalog, build_tool_catalog, source_path
from .infrastructure import Infrastructure
from .layers.orchestration import AgentWorkflowState, LangGraphOrchestrator
from .layers.approvals import ApprovalError, ApprovalService
from .layers.execution import ImplementationWorker, ImplementationWorkerError
from .layers.forge import ForgeToolLoop
from .layers.grounding import evaluate_grounding
from .layers.lifecycle_catalog import lifecycle_governance_catalog
from .layers.security import SecurityPolicy, build_security_posture
from .layers.specialist import ReadOnlySpecialistToolLoop
from .layers.task_queue import DurablePriorityQueue, PRIORITY_ORDER
from .models import Agent, AgentCreate, AgentUpdate, ApprovalChallengeResponse, ApprovedSearchRequest, AtlasIntakeRequest, AuditEvent, AvatarGeneration, ChangeSet, ChangeSetApproval, ChangeSetCommitRequest, ChangeSetTestRequest, DevelopmentLifecycle, ExternalActionApproval, ExternalActionDecision, ExternalActionRequest, LibraryChange, LibraryChangeRequest, LifecycleCreate, LifecycleNotificationDecision, LifecycleOverride, LifecycleTransition, Plan, PlanCreate, PlanDecision, PlanRecommendationUpdate, PlanReviewerRequest, PlanWorkspace, ProtectedActionRequest, QaPipelineRunRequest, SourceAdditionRequest, SpeechSynthesisRequest, Task, TaskCreate, ToolAccessRequest, WorkerActionRequest, WorkflowDefinition, WorkflowDefinitionCreate, WorkflowRequestCreate
from .providers import LiteLLMProvider, ProviderError, ProviderGateway
from .speech_text import prepare_speech_text
from .tts import synthesize_speech as chatterbox_synthesize, preload_model as preload_tts, resolve_audio_prompt as resolve_tts_audio_prompt
from .skill_runtime import SkillRuntime
from .store import ArtifactStore, MemoryStore
from .workspace_browser import WorkspaceBrowser, WorkspacePathError

settings = get_settings()
store = MemoryStore()
artifacts = ArtifactStore(settings.artifact_root, settings.upload_max_mb)
workspace_browser = WorkspaceBrowser(settings.workspace_root, settings.workspace_max_preview_kb)
gateway = ProviderGateway(settings.default_provider, {"ollama": LiteLLMProvider(
    api_base=settings.litellm_api_base,
    api_key=settings.litellm_api_key,
    model_prefix=settings.litellm_model_prefix,
    timeout_seconds=settings.model_timeout_seconds,
    max_tokens=settings.model_max_tokens,
    context_tokens=settings.forge_context_tokens,
    num_retries=settings.litellm_num_retries,
    cost_tracking=settings.litellm_cost_tracking,
    fallback_models=settings.litellm_fallback_models,
    connect_retries=settings.model_connect_retries,
    thinking_tokens=settings.model_thinking_tokens,
)})
infrastructure = Infrastructure(settings.database_url, settings.redis_url)
implementation_worker = ImplementationWorker(settings.worker_url, settings.worker_token)
# Forge gets a separate inference budget from interactive chat. This preserves
# fast ordinary responses while allowing structured, multi-file tool calls.
forge_provider = LiteLLMProvider(
    api_base=settings.litellm_api_base,
    api_key=settings.litellm_api_key,
    model_prefix=settings.litellm_model_prefix,
    timeout_seconds=settings.forge_timeout_seconds,
    max_tokens=settings.forge_max_tokens,
    context_tokens=settings.forge_context_tokens,
    num_retries=settings.litellm_num_retries,
    cost_tracking=settings.litellm_cost_tracking,
    fallback_models=settings.litellm_fallback_models,
)
forge_tool_loop = ForgeToolLoop(forge_provider, implementation_worker)
read_only_specialist_loop = ReadOnlySpecialistToolLoop(forge_provider, implementation_worker)
# Resolve skills: package directory > repo root > CWD
_skills_dirs = [
    Path(__file__).resolve().parent.parent.parent / "skills",
    Path.cwd() / "skills",
]
_skill_root = next((p for p in _skills_dirs if p.is_dir()), _skills_dirs[1])
skill_runtime = SkillRuntime(_skill_root)
approval_service = ApprovalService(store.external_approvals)
clients: set[WebSocket] = set()
kill_switch = asyncio.Event()
avatar_jobs: dict[UUID, AvatarGeneration] = {}
task_jobs: dict[UUID, asyncio.Task] = {}
task_queue = DurablePriorityQueue()
dispatcher_job: asyncio.Task | None = None
process_started_at = time.monotonic()
approval_challenges: dict[UUID, dict] = {}
NONMUTATING_TOOLS = frozenset({
    "diagnostics", "research", "investigation", "memory_read", "files_read",
    "security_scan", "compliance_review", "legal_review", "blueprint_generate", "browser",
})


def issue_approval_challenge(approval_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    for stale_id, stale in list(approval_challenges.items()):
        if stale["expires_at"] <= now:
            approval_challenges.pop(stale_id, None)
    code = f"{secrets.randbelow(1_000_000):06d}"
    # Use a per-process HMAC key, not the worker token
    _challenge_hmac_key = getattr(issue_approval_challenge, "_hmac_key", None)
    if _challenge_hmac_key is None:
        _challenge_hmac_key = secrets.token_hex(32)
        issue_approval_challenge._hmac_key = _challenge_hmac_key
    digest = hmac.new(_challenge_hmac_key.encode(), code.encode(), hashlib.sha256).hexdigest()
    approval_challenges[approval_id] = {
        "digest": digest, "expires_at": now + timedelta(minutes=5), "attempts": 0,
    }
    return code


def approval_challenge_valid(approval_id: UUID, value: str) -> bool:
    challenge = approval_challenges.get(approval_id)
    if not challenge or challenge["expires_at"] <= datetime.now(timezone.utc) or challenge["attempts"] >= 5:
        return False
    challenge["attempts"] += 1
    _challenge_hmac_key = getattr(issue_approval_challenge, "_hmac_key", None)
    if not _challenge_hmac_key:
        return False
    candidate = hmac.new(_challenge_hmac_key.encode(), value.encode(), hashlib.sha256).hexdigest()
    valid = hmac.compare_digest(challenge["digest"], candidate)
    if valid:
        approval_challenges.pop(approval_id, None)
    return valid


async def broadcast(event: dict):
    for client in list(clients):
        try:
            await client.send_json(event)
        except Exception:
            clients.discard(client)


_AUDIT_FIELD_RE = re.compile(
    r"^\s*(?:REQUEST|INTERPRETATION|EVIDENCE|ACTION_TAKEN|VERIFICATION|AUDIT"
    r"|APPROVAL_REQUIRED|NEXT|DELEGATION)\s*:\s*.*$",
    re.MULTILINE,
)
_THINKING_OPEN = "<think>"
_THINKING_CLOSE = "</think>"
_THINKING_RE = re.compile(r"<think>[\s\S]*?</think>")


def _strip_thinking(output: str) -> str:
    result = _THINKING_RE.sub("", output).strip()
    idx = result.find(_THINKING_OPEN)
    if idx >= 0:
        result = result[idx + len(_THINKING_OPEN):]
    close_idx = result.rfind(_THINKING_CLOSE)
    if close_idx >= 0:
        result = result[close_idx + len(_THINKING_CLOSE):]
    return result.strip()


def _extract_reasoning(output: str) -> tuple[str, str]:
    """Split LLM output into (reasoning, user_facing).

    The reasoning part contains structured audit fields. The user-facing part
    is everything else — the clean response shown to the user and spoken by TTS.
    """
    lines = output.splitlines()
    reasoning_lines: list[str] = []
    user_lines: list[str] = []
    for line in lines:
        if _AUDIT_FIELD_RE.match(line):
            reasoning_lines.append(line)
        else:
            user_lines.append(line)
    reasoning = "\n".join(reasoning_lines).strip()
    user_facing = "\n".join(user_lines).strip()
    return reasoning, user_facing


def _clean_response(output: str) -> str:
    """Return only the user-facing portion of an LLM response."""
    _, user_facing = _extract_reasoning(output)
    return user_facing or output


def _deduplicate_response(output: str) -> str:
    """Remove consecutive repeated content from LLM output."""
    if not output or len(output) < 40:
        return output
    half = len(output) // 2
    for cut in range(half, 20, -1):
        prefix = output[:cut].strip()
        rest = output[cut:].strip()
        if rest.startswith(prefix):
            return output[:cut].strip()
    return output


def render_agent_context(exclude_name: str = "") -> str:
    """Build a formatted roster of available agents for the LLM system prompt."""
    agents = [a for a in store.agents.values() if a.name != exclude_name]
    if not agents:
        return ""
    lines = ["\n\nAVAILABLE AGENTS IN THIS PLATFORM:"]
    for a in agents:
        lines.append(f"- {a.name} ({a.role}): {a.description}")
    return "\n".join(lines)


async def run_model_step(state: AgentWorkflowState) -> dict:
    """The model node used by the governed LangGraph workflow."""
    agent = store.agents[UUID(state["agent_id"])]
    review_only = state["prompt"].startswith("[LIFECYCLE_REVIEW]")
    authorization_rule = (
        "This task carries explicit user authorization. Stay within the approved task and workspace boundaries."
        if state.get("user_authorized")
        else "Do not perform implementation work or imply that unapproved changes were made."
    )
    orchestration_rule = (
        "This is an evidence-based, read-only lifecycle review. Do not write files, run implementation tools, "
        "change permissions, or claim that a change was applied. Identify missing evidence and ask the user when it is required."
        if review_only else
        "You are the read-only orchestrator in the chain User -> Atlas -> Forge -> specialist agents. "
        "Present the proposed delegation and obtain user authorization before Forge or another implementation agent changes anything."
        if agent.name == "Atlas" else authorization_rule
    )
    uncertainty_rule = (
        "Do not invent facts, files, requirements, results, permissions, or user preferences. "
        "When information required for a decision or action is missing, identify the missing information, "
        "ask the user a direct question, and wait. Do not silently choose a default or claim completion."
    )
    intake_rule = (
        "Use the Atlas request-intake skill. Reuse the latest request, recent conversation, workspace, attachments, and known configuration. "
        "Proceed with read-only work without asking permission. Infer reversible low-risk details. Ask at most one concise question only when "
        "the target or desired outcome is genuinely unknowable or materially different choices affect security, data loss, cost, or external effects. "
        "Never ask a generic checklist or ask the user to repeat known information."
        if agent.name == "Atlas" else ""
    )
    allowed_tools = [tool for tool in agent.tools if tool in NONMUTATING_TOOLS] if review_only else agent.tools
    skill_context = skill_runtime.render(agent.skills)
    agent_context = render_agent_context(exclude_name=agent.name)
    owner_context = f" The platform owner's name is {settings.owner_name}. Address them by name when greeting or responding to simple queries. Use their name naturally, not in every sentence."
    system = f"You are {agent.name}, {agent.role}. {agent.description} {orchestration_rule} {uncertainty_rule} {intake_rule} Allowed tools: {', '.join(allowed_tools) or 'none'}. Never claim to use tools not listed.{skill_context}{agent_context}{owner_context}"
    output = ""
    try:
        if agent.name == "Quanta" and state["prompt"].startswith("[FULL_QA_PIPELINE]"):
            if not state.get("user_authorized") or not state.get("plan_id") or not state.get("workspace_id"):
                return {"status": "failed", "output": "The full QA pipeline requires an approved plan workspace and exact user authorization.", "error": "qa_authorization_required"}
            lifecycle = next((item for item in store.lifecycles.values() if str(item.plan_id) == state["plan_id"]), None)
            if not lifecycle or lifecycle.stage != "test":
                return {"status": "failed", "output": "The full QA pipeline can run only after the approved lifecycle enters the Test stage.", "error": "qa_stage_required"}
            command = ["python", "-m", "pytest", "-q"]
            result = await implementation_worker.execute({
                "action": "test_execute", "workspace_id": state["workspace_id"], "path": ".",
                "command": command, "timeout_seconds": 300,
            })
            passed = result.get("exit_code") == 0
            recorded_at = datetime.now(timezone.utc)
            evidence_ref = f"qa-run:{state['task_id']}"
            lifecycle.evidence.append({
                "stage": "test", "type": "test", "status": "passed" if passed else "failed",
                "source": "quanta-full-pipeline", "task_id": state["task_id"], "command": command,
                "exit_code": result.get("exit_code"), "duration_ms": result.get("duration_ms"),
                "recorded_at": recorded_at.isoformat(),
            })
            lifecycle.updated_at = recorded_at
            await infrastructure.persist_lifecycle(lifecycle)
            qa_event = AuditEvent(
                action="qa.pipeline.execute", actor="Quanta", target=state["task_id"],
                outcome="passed" if passed else "failed",
                details={
                    "plan_id": state["plan_id"], "workspace_id": state["workspace_id"],
                    "command": command, "exit_code": result.get("exit_code"),
                    "duration_ms": result.get("duration_ms"), "network": "denied",
                },
            )
            store.log(qa_event)
            await infrastructure.persist_audit(qa_event)
            stdout = str(result.get("stdout") or "").strip()[-8_000:]
            stderr = str(result.get("stderr") or "").strip()[-4_000:]
            output = (
                f"Quanta full QA pipeline {'passed' if passed else 'failed'}.\n\n"
                f"Command: python -m pytest -q\nExit code: {result.get('exit_code')}\n"
                f"Duration: {result.get('duration_ms', 0)} ms\nNetwork: denied\n\n"
                f"Test output:\n{stdout or '(no standard output)'}"
            )
            if stderr:
                output += f"\n\nError output:\n{stderr}"
            return {
                "status": "completed" if passed else "failed", "output": output,
                "grounding_status": "grounded", "grounding_issues": [], "evidence_refs": [evidence_ref],
            }
        if agent.name == "Forge" and not review_only:
            if not state.get("plan_id") or not state.get("workspace_id"):
                return {"status": "failed", "output": "Forge requires an approved plan workspace before it can inspect or propose code changes.", "error": "workspace_required"}
            output, change_set = await forge_tool_loop.run(
                prompt=state["prompt"], model=state["model"], task_id=UUID(state["task_id"]),
                plan_id=UUID(state["plan_id"]), workspace_id=UUID(state["workspace_id"]),
                skill_context=skill_context, agent_context=agent_context,
            )
            if change_set:
                store.change_sets[change_set.id] = change_set
                await infrastructure.persist_change_set(change_set)
                event = AuditEvent(
                    action="forge.change_set.propose", actor="Forge", target=str(change_set.id), outcome="pending_review",
                    details={"task_id": state["task_id"], "plan_id": state["plan_id"], "workspace_id": state["workspace_id"], "files": [item.path for item in change_set.files]},
                )
                store.log(event)
                await infrastructure.persist_audit(event)
                reasoning, clean_output = _extract_reasoning(output)
                clean_output = _strip_thinking(_deduplicate_response(clean_output)) or clean_output
                await broadcast({
                    "type": "forge.change_set", "task_id": state["task_id"],
                    "change_set_id": str(change_set.id), "status": change_set.status,
                    "files": len(change_set.files), "message": clean_output,
                })
                return {"status": "completed", "output": clean_output, "reasoning": reasoning, "grounding_status": "grounded", "grounding_issues": [], "evidence_refs": [f"change-set:{change_set.id}"]}
            reasoning, clean_output = _extract_reasoning(output)
            clean_output = _strip_thinking(_deduplicate_response(clean_output)) or clean_output
            assessment = evaluate_grounding(agent.name, clean_output)
            return {"status": "completed", "output": clean_output, "reasoning": reasoning, "grounding_status": assessment["status"], "grounding_issues": assessment["issues"], "evidence_refs": assessment["evidence_refs"]}
        messages = [{"role": "system", "content": system}, {"role": "user", "content": state["prompt"]}]
        async for delta in gateway.get().stream(messages, state["model"]):
            task = store.tasks.get(UUID(state["task_id"]))
            if kill_switch.is_set() or (task and task.status == "cancelled"):
                return {"status": "cancelled", "output": output or "Generation cancelled."}
            output += delta
            clean = _clean_response(output)
            if task:
                task.output = clean
            await broadcast(
                {
                    "type": "task.delta",
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                    "agent_id": state["agent_id"],
                    "delta": delta,
                    "text": clean,
                    "status": "running",
                }
            )
        reasoning, clean_output = _extract_reasoning(output)
        clean_output = _strip_thinking(clean_output) or _strip_thinking(output)
        if not clean_output:
            clean_output = output
        clean_output = _deduplicate_response(clean_output)
        assessment = evaluate_grounding(agent.name, clean_output)
        if assessment["status"] == "verification_required":
            clean_output += "\n\nVerification required: " + " ".join(assessment["issues"])
        return {"status": "completed", "output": clean_output, "reasoning": reasoning, "grounding_status": assessment["status"], "grounding_issues": assessment["issues"], "evidence_refs": assessment["evidence_refs"]}
    except asyncio.CancelledError:
        return {"status": "cancelled", "output": output or "Generation cancelled."}
    except ProviderError as exc:
        return {"status": "failed", "output": f"Local model unavailable: {exc}. Check Ollama and retry.", "error": "provider_unavailable"}
    except Exception as exc:
        return {"status": "failed", "output": f"The local task failed safely ({exc.__class__.__name__}). Review the app logs and retry.", "error": exc.__class__.__name__}


workflow_orchestrator = LangGraphOrchestrator(settings.database_url, run_model_step)


def delegated_read_only_specialist(agent: Agent, prompt: str) -> Agent | None:
    """Resolve explicit, sufficiently scoped specialist requests without model guesswork."""
    if agent.name != "Atlas":
        return None
    current_request = prompt.rsplit("CURRENT USER REQUEST:", 1)[-1]
    current_normalized = " ".join(current_request.casefold().replace("-", " ").split())
    continuation = bool(re.search(r"\b(?:authorized|proceed|continue|yes|do it|initiate|start the test)\b", current_normalized))
    normalized = " ".join((prompt if continuation else current_request).casefold().replace("-", " ").split())
    asks_for_qa = bool(re.search(r"\b(?:qa|quality assurance|quanta)\b", normalized))
    asks_to_investigate = bool(re.search(r"\b(?:test|verify|validate|inspect|investigate|diagnos\w*|determine why|root cause)\b", normalized))
    read_only = bool(re.search(r"\bread only\b", normalized))
    has_target = bool(re.search(r"\b(?:feature|button|toggle|page|screen|endpoint|api|workflow|file|theme|mode|issue|error)\b", normalized))
    site_target = bool(re.search(r"\b(?:site|page|screen|dashboard|interface|ui|frontend|browser|button|toggle|theme)\b", normalized))
    asks_to_change = bool(re.search(r"\b(?:change|modify|implement|build|delete|remove|write|fix)\b", normalized))
    if asks_for_qa and asks_to_investigate and read_only and has_target:
        return next((candidate for candidate in store.agents.values() if candidate.name == "Quanta"), None)
    if asks_to_investigate and site_target and not asks_to_change:
        return next((candidate for candidate in store.agents.values() if candidate.name == "Interface"), None)
    return None


async def execute(task: Task, user_authorized: bool = False):
    if kill_switch.is_set():
        task.status = "cancelled"
        task.updated_at = datetime.now(timezone.utc)
        task.completed_at = task.updated_at
        await infrastructure.persist_task(task)
        await broadcast({"type": "task.progress", "task_id": str(task.id), "status": task.status, "message": "Cancelled by the platform kill switch"})
        return
    started_at = time.perf_counter()
    task.attempt += 1
    task.updated_at = datetime.now(timezone.utc)
    agent = store.agents[task.agent_id]
    policy = SecurityPolicy.task_policy(agent, user_authorized)
    task.status = "running"
    workflow_event = AuditEvent(
        action="workflow.started", actor=agent.name, target=str(task.id), outcome="running",
        details={"workflow": "governed-agent-task", "risk_tier": policy["risk_tier"], "plan_id": str(task.plan_id) if task.plan_id else None},
    )
    store.log(workflow_event)
    await infrastructure.persist_audit(workflow_event)
    await broadcast(
        {
            "type": "workflow.started",
            "run_id": str(task.id),
            "task_id": str(task.id),
            "agent_id": str(agent.id),
            "agent": agent.name,
            "status": task.status,
            "risk_tier": policy["risk_tier"],
        }
    )
    await broadcast({"type": "task.progress", "task_id": str(task.id), "status": task.status, "message": "Local agent started"})
    state: AgentWorkflowState = {
        "run_id": str(task.id),
        "task_id": str(task.id),
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "prompt": task.prompt,
        "model": task.model,
        "tools": list(agent.tools),
        "requires_authorization": policy["authorization_required"],
        "user_authorized": user_authorized,
        "risk_tier": policy["risk_tier"],
        "status": "queued",
        "output": "",
        "error": None,
        "plan_id": str(task.plan_id) if task.plan_id else None,
        "workspace_id": str(task.workspace_id) if task.workspace_id else None,
        "grounding_status": "pending",
        "grounding_issues": [],
        "evidence_refs": [],
    }
    try:
        specialist = delegated_read_only_specialist(agent, task.prompt)
        if specialist:
            delegation_event = AuditEvent(
                action="task.delegate", actor="Atlas", target=str(task.id), outcome="accepted",
                details={
                    "specialist": specialist.name,
                    "mode": "read_only",
                    "tools": ["list_workspace", "search_workspace", "read_file", "inspect_site"],
                    "mutations_allowed": False,
                },
            )
            store.log(delegation_event)
            await infrastructure.persist_audit(delegation_event)
            await broadcast({
                "type": "task.delegated", "task_id": str(task.id), "from_agent": "Atlas",
                "to_agent": specialist.name, "mode": "read_only", "status": "running",
            })
            try:
                specialist_output, evidence_refs = await read_only_specialist_loop.run(
                    specialist_name=specialist.name,
                    role=specialist.role,
                    prompt=task.prompt,
                    model=task.model,
                    skill_context=skill_runtime.render(specialist.skills),
                    agent_context=render_agent_context(exclude_name=specialist.name),
                )
            except ProviderError as exc:
                specialist_output = f"The local model was unavailable during {specialist.name}'s read-only investigation: {exc}. Check Ollama and retry."
                evidence_refs = []
            specialist_event = AuditEvent(
                action="specialist.investigate", actor=specialist.name, target=str(task.id),
                outcome="completed" if evidence_refs else "blocked",
                details={"mode": "read_only", "evidence_refs": evidence_refs, "mutations_allowed": False},
            )
            store.log(specialist_event)
            await infrastructure.persist_audit(specialist_event)
            specialist_reasoning, specialist_clean = _extract_reasoning(specialist_output)
            specialist_clean = _deduplicate_response(specialist_clean) or specialist_output
            result = {
                "status": "completed" if evidence_refs else "failed",
                "output": specialist_clean,
                "reasoning": specialist_reasoning,
                "grounding_status": "grounded" if evidence_refs else "blocked",
                "grounding_issues": [] if evidence_refs else ["The delegated QA investigation produced no machine-recorded workspace evidence."],
                "evidence_refs": evidence_refs,
            }
        else:
            result = await workflow_orchestrator.run(state)
        workflow_status = result.get("status", "failed")
        if workflow_status == "awaiting_approval":
            task.status = "failed"
            task.output = "Explicit user authorization is required before this workflow can run."
        else:
            task.status = workflow_status if workflow_status in {"completed", "failed", "cancelled"} else "failed"
            task.output = result.get("output") or task.output or ""
            task.reasoning = result.get("reasoning") or task.reasoning
            task.grounding_status = result.get("grounding_status", "not_applicable")
            task.grounding_issues = list(result.get("grounding_issues") or [])
            task.evidence_refs = list(result.get("evidence_refs") or [])
    except asyncio.CancelledError:
        task.status = "cancelled"
        task.output = task.output or "Generation cancelled."
    except Exception as exc:
        task.status = "failed"
        task.output = f"The governed workflow failed safely ({exc.__class__.__name__}). Review the app logs and retry."
    task.completed_at = datetime.now(timezone.utc)
    task.updated_at = task.completed_at
    task.duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
    grounding_event = AuditEvent(
        action="grounding.evaluate", actor=agent.name, target=str(task.id), outcome=task.grounding_status,
        details={"issues": task.grounding_issues, "evidence_refs": task.evidence_refs},
    )
    store.log(grounding_event)
    execution_event = AuditEvent(action="task.execute", actor=agent.name, target=str(task.id), outcome=task.status, details={"model": task.model, "grounding_status": task.grounding_status, "evidence_refs": task.evidence_refs})
    store.log(execution_event)
    # Notify the client before persistence so a slow database cannot strand the
    # transcript in its pending state.
    await broadcast({"type": "task.progress", "task_id": str(task.id), "status": task.status, "message": task.output})
    await infrastructure.persist_task(task)
    await infrastructure.persist_audit(grounding_event)
    await infrastructure.persist_audit(execution_event)


async def dispatch_tasks():
    """Run queued work in priority order; Forge defaults to the high lane."""
    while True:
        queued = await task_queue.dequeue()
        task = store.tasks.get(queued.task_id)
        if not task or task.status != "queued":
            continue
        job = asyncio.create_task(execute(task, user_authorized=queued.user_authorized))
        task_jobs[task.id] = job
        try:
            await job
        finally:
            task_jobs.pop(task.id, None)


async def monitor_avatar(job: AvatarGeneration, provider: LocalTripoSRProvider):
    job.status = "running"
    try:
        # A first CPU run can include multi-gigabyte model downloads followed by
        # reconstruction and Blender export. Keep monitoring for one hour.
        for _ in range(720):
            data = await provider.status(job.provider_task_id)
            state = str(data.get("status", "running")).lower()
            job.progress = min(99, int(data.get("progress", job.progress or 5)))
            job.message = str(data.get("message") or f"Local worker: {state}")
            await broadcast({"type": "avatar.progress", **job.model_dump(mode="json")})
            if state in ("success", "succeeded", "completed"):
                url = provider.find_glb(data)
                if not url:
                    raise AvatarServiceError("completed task did not include a GLB URL")
                filename = f"avatar-{job.id}.glb"
                await provider.download_glb(url, settings.artifact_root / filename)
                job.status, job.progress = "completed", 100
                job.message, job.artifact_url = "Blender preview ready — review before using", f"/artifacts/{filename}"
                break
            if state in ("failed", "cancelled", "canceled", "error"):
                raise AvatarServiceError(str(data.get("message") or "provider generation failed"))
            await asyncio.sleep(5)
        else:
            raise AvatarServiceError("local avatar generation timed out after 60 minutes")
    except (AvatarServiceError, httpx.HTTPError) as exc:
        job.status, job.message = "failed", _safe_exc_msg(exc)
    event = AuditEvent(action="avatar.generate", actor="Atlas", target=str(job.id), outcome=job.status, details={"provider": job.provider})
    store.log(event)
    await infrastructure.persist_audit(event)
    await broadcast({"type": "avatar.progress", **job.model_dump(mode="json")})


@asynccontextmanager
async def lifespan(app: FastAPI):
    global dispatcher_job
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    await infrastructure.connect()
    task_queue.attach(infrastructure.redis)
    await workflow_orchestrator.initialize(infrastructure.db is not None)
    for event in reversed(await infrastructure.load_audit()):
        store.log(event)
    # --- Standalone mode warnings ---
    _warn = __import__("logging").getLogger("atlas_studio.startup").warning
    if getattr(infrastructure, "_backend", "") == "sqlite":
        _warn("PostgreSQL unavailable - using SQLite persistence")
    elif getattr(infrastructure, "_backend", "") == "memory":
        _warn("No database available - all data lost on restart")
    if infrastructure.redis is None:
        _warn("Redis unavailable - using in-memory task queue (non-durable)")
    _worker_health = await implementation_worker.health()
    if _worker_health.get("status") != "ok":
        _warn("HTTP worker unavailable - using embedded in-process worker")
    # Pre-load ChatterboxTTS model in background
    try:
        preload_tts()
        _warn("ChatterboxTTS model loading in background")
    except Exception:
        _warn("ChatterboxTTS not available — TTS will use external worker only")

    seeded_agents = list(store.agents.values())
    system_agent_names = {agent.name for agent in seeded_agents if agent.system}
    persisted_agents = await infrastructure.load_agents()
    if persisted_agents:
        store.agents.clear()
        for agent in persisted_agents:
            reconciled = False
            agent.system = agent.name in system_agent_names
            if agent.name == "Atlas" and "atlas_request_intake" not in agent.skills:
                agent.skills.append("atlas_request_intake")
                reconciled = True
            if agent.name == "Quanta" and "browser" not in agent.tools:
                agent.tools.append("browser")
                reconciled = True
            store.agents[agent.id] = agent
            if reconciled:
                await infrastructure.persist_agent(agent)
        persisted_names = {agent.name for agent in persisted_agents}
        for agent in seeded_agents:
            if agent.name not in persisted_names:
                store.agents[agent.id] = agent
                await infrastructure.persist_agent(agent)
    else:
        for agent in seeded_agents:
            await infrastructure.persist_agent(agent)
    for plan in await infrastructure.load_plans():
        store.plans[plan.id] = plan
    for lifecycle in await infrastructure.load_lifecycles():
        store.lifecycles[lifecycle.id] = lifecycle
    for change in await infrastructure.load_library_changes():
        store.library_changes[change.id] = change
    for approval in await infrastructure.load_external_approvals():
        store.external_approvals[approval.id] = approval
    for workflow in await infrastructure.load_workflow_definitions():
        store.workflow_definitions[(workflow.id, workflow.version)] = workflow
    for plan_workspace in await infrastructure.load_plan_workspaces():
        store.plan_workspaces[plan_workspace.id] = plan_workspace
    for change_set in await infrastructure.load_change_sets():
        store.change_sets[change_set.id] = change_set
    for task in await infrastructure.load_tasks():
        if task.status == "running":
            task.status = "queued"
            task.output = task.output or "Recovered after an interrupted application run."
            task.updated_at = datetime.now(timezone.utc)
            await infrastructure.persist_task(task)
        store.tasks[task.id] = task
        if task.status == "queued":
            await task_queue.enqueue(task.id, task.priority, task.user_authorized)
    dispatcher_job = asyncio.create_task(dispatch_tasks())
    yield
    if dispatcher_job:
        dispatcher_job.cancel()
        try:
            await dispatcher_job
        except asyncio.CancelledError:
            pass
        dispatcher_job = None
    await workflow_orchestrator.close()
    await infrastructure.close()


app = FastAPI(title="Atlas Studio", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

# CORS middleware — restricted to configured origins only
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + ["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Api-Key"],
)

# OpenAI-compatible API adapter (/v1/models, /v1/chat/completions)
from .openai_compat import router as openai_compat_router
app.include_router(openai_compat_router)

# MITM Security Layer — ASGI-native middleware that works with streaming and WebSockets.
from .security import MITMSecurityMiddleware, AuditLogger, InputValidator, OutputSanitizer, PolicyEngine
from .security.mitm import get_session_store


def _safe_exc_msg(exc: Exception) -> str:
    """Sanitize exception messages to prevent leaking keys/URLs in HTTP responses."""
    msg = str(exc) or exc.__class__.__name__
    # Remove URLs, API keys, Bearer tokens
    msg = re.sub(r'https?://[^\s\'"]+', '[redacted-url]', msg)
    msg = re.sub(r'(api[_-]?key\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', msg, flags=re.IGNORECASE)
    msg = re.sub(r'(Bearer\s+)[^\s,;]+', r'\1[redacted]', msg)
    msg = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[redacted-key]', msg)
    if len(msg) > 200:
        msg = msg[:200] + '...'
    return msg

# Add ASGI-native MITM security middleware (must be added BEFORE other middleware)
app.add_middleware(
    MITMSecurityMiddleware,
    secret_key=settings.session_secret or "atlas-local-secret-key",
    rate_limit=settings.rate_limit_max_requests,
    rate_window=settings.rate_limit_window_seconds,
    audit_log_path="audit.jsonl",
    skip_paths=[
        "/",
        "/favicon.ico",
        "/api/health/live",
        "/api/health/ready",
        "/static/",
        "/api/docs",
        "/api/openapi.json",
        "/api/auth/bootstrap",
        "/api/ws",
    ],
)

audit_logger = AuditLogger("audit.jsonl")
mitm_validator = InputValidator()
mitm_sanitizer = OutputSanitizer()
mitm_policy = PolicyEngine()


@app.get("/favicon.ico")
async def favicon():
    from starlette.responses import Response
    return Response(content=b"", media_type="image/x-icon")


@app.post("/api/auth/bootstrap")
async def auth_bootstrap():
    """Create a session for the local owner. Returns the owner token for Bearer auth."""
    store = get_session_store()
    token = store.get_owner_token()
    return {"owner_token": token, "role": "owner"}


@app.get("/api/auth/validate")
async def auth_validate(request: Request):
    """Check if the current session is valid."""
    cookie = request.cookies.get("atlas_session", "")
    auth = request.headers.get("authorization", "")
    api_key = request.headers.get("x-api-key", "")
    store = get_session_store()

    if auth.startswith("Bearer "):
        tok = auth[7:]
        if store.validate_owner_token(tok):
            return {"valid": True, "role": "owner", "method": "owner-token"}
        from .config import get_settings
        if tok == get_settings().worker_token:
            return {"valid": True, "role": "admin", "method": "worker-token"}
    if cookie:
        session = store.validate(cookie)
        if session:
            return {"valid": True, "role": session.get("role", "owner"), "method": "session"}
    if api_key and store.validate_owner_token(api_key):
        return {"valid": True, "role": "owner", "method": "api-key"}

    return {"valid": False}


@app.get("/api/health/live")
async def live():
    return {"status": "ok", "service": "atlas-studio"}


@app.get("/api/health/ready")
async def ready():
    import asyncio
    async def _safe(fn, default):
        try:
            return await asyncio.wait_for(fn(), timeout=5)
        except Exception:
            return default
    model = await _safe(gateway.get().healthy, False)
    worker = await _safe(implementation_worker.health, {"status": "unavailable"})
    infra = await _safe(infrastructure.health, {})
    components = {"api": "ok", "model_gateway": "ok" if model else "unavailable", "implementation_worker": worker.get("status", "unavailable"), **infra}
    return {"status": "ready" if all(v == "ok" for v in components.values()) else "degraded", "components": components, "local_only": True}


@app.get("/api/config")
async def config():
    worker = await implementation_worker.health()
    return {"mode": settings.mode, "provider": settings.default_provider, "model": settings.default_model, "forge_model": settings.forge_model, "forge_runtime": {"timeout_seconds": settings.forge_timeout_seconds, "max_tokens": settings.forge_max_tokens, "context_tokens": settings.forge_context_tokens}, "artifact_backend": settings.artifact_backend, "telemetry": settings.telemetry_enabled, "workspace": {"name": settings.workspace_root.name or "workspace", "read_only": True, "preview_limit_kb": settings.workspace_max_preview_kb}, "workflow": workflow_orchestrator.status(), "implementation_worker": worker, "integrations": {"minio": settings.minio_enabled, "google_oauth": settings.google_oauth_enabled, "speech_to_text": bool(settings.stt_url), "text_to_speech": bool(settings.tts_url), "avatar_local": settings.avatar_local_enabled, "avatar_provider": settings.avatar_provider if settings.avatar_local_enabled else None}}


@app.get("/api/workflows")
async def workflows():
    """Expose the local engine plus built-in and user-governed definitions."""
    status = workflow_orchestrator.status()
    status["definitions"] = [*status["definitions"], *[
        workflow.model_dump(mode="json")
        for workflow in sorted(store.workflow_definitions.values(), key=lambda item: item.created_at)
    ]]
    return status


@app.get("/api/lifecycle/governance")
async def lifecycle_governance():
    """Return the executable lifecycle specification and current audit coverage."""
    catalog = lifecycle_governance_catalog()
    observed = {event.action for event in store.audit}
    coverage = []
    for area in catalog["audit_coverage"]:
        expected = list(area["events"])
        seen = [event for event in expected if event in observed]
        coverage.append({**area, "observed_events": seen, "missing_events": [event for event in expected if event not in observed]})
    return {
        **catalog,
        "audit_coverage": coverage,
        "logging": {
            "configured": True,
            "observed_event_types": sorted(observed),
            "recorded_events": len(store.audit),
            "note": "Missing events mean that activity has not occurred in this workspace; they are not reported as completed.",
        },
    }


@app.post("/api/workflows/requests", response_model=WorkflowDefinition, status_code=202)
async def request_workflow(body: WorkflowRequestCreate):
    if not any(agent.name == body.owner for agent in store.agents.values()):
        raise HTTPException(422, "workflow owner must be a named Atlas Studio agent")
    workflow = WorkflowDefinition(
        id=f"workflow-request-{uuid4().hex[:12]}", name=body.name, owner=body.owner,
        description=body.goal, nodes=[], status="requested", source_type="request",
        source_reference="\n".join(body.references), active=False,
    )
    store.workflow_definitions[(workflow.id, workflow.version)] = workflow
    event = AuditEvent(
        action="workflow.request", actor="local-user", target=workflow.id, outcome="requested",
        details={"owner": workflow.owner, "references": body.references},
    )
    store.log(event)
    await infrastructure.persist_workflow_definition(workflow)
    await infrastructure.persist_audit(event)
    return workflow


@app.post("/api/workflows", response_model=WorkflowDefinition, status_code=201)
async def create_workflow_definition(body: WorkflowDefinitionCreate):
    if any(definition["id"] == body.id for definition in workflow_orchestrator.status()["definitions"]):
        raise HTTPException(409, "built-in workflow identifiers cannot be replaced")
    if (body.id, 1) in store.workflow_definitions:
        raise HTTPException(409, "a workflow with this identifier already exists")
    if not any(agent.name == body.owner for agent in store.agents.values()):
        raise HTTPException(422, "workflow owner must be a named Atlas Studio agent")
    payload = body.model_dump(mode="json", exclude={"approval_id"})
    try:
        approval = approval_service.consume(
            body.approval_id, action="workflow_definition", target=body.id, payload=payload,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    workflow = WorkflowDefinition(
        **payload, status="pending_security_review", active=False,
    )
    store.workflow_definitions[(workflow.id, workflow.version)] = workflow
    event = AuditEvent(
        action="workflow.definition.create", actor="local-user", target=workflow.id,
        outcome="pending_security_review",
        details={"owner": workflow.owner, "source_type": workflow.source_type, "nodes": workflow.nodes},
    )
    store.log(event)
    await infrastructure.persist_workflow_definition(workflow)
    await infrastructure.persist_audit(event)
    return workflow


@app.get("/api/worker/health")
async def worker_health():
    return await implementation_worker.health()


@app.post("/api/worker/actions")
async def worker_action(body: WorkerActionRequest):
    agent = store.agents.get(body.agent_id)
    if not agent:
        raise HTTPException(404, "implementation agent not found")
    if agent.name == "Atlas" or agent.read_only:
        raise HTTPException(403, "read-only agents cannot use the implementation worker")
    required_tool = {
        "preview_write": "files_write",
        "file_write": "files_write",
        "code_execute": "code_execute",
        "test_execute": "test_execute",
    }[body.action]
    if required_tool not in agent.tools:
        raise HTTPException(403, f"{agent.name} is not assigned {required_tool}")
    if not body.workspace_id:
        raise HTTPException(409, "an approved isolated plan workspace is required")
    plan_workspace = store.plan_workspaces.get(body.workspace_id)
    if not plan_workspace or plan_workspace.status != "ready":
        raise HTTPException(409, "the selected plan workspace is not ready")
    if not body.user_authorized:
        raise HTTPException(403, "explicit user authorization is required")
    payload = body.model_dump(mode="json", exclude={"agent_id", "user_authorized", "approval_passcode", "approval_id"})
    if body.action != "preview_write":
        if not body.approval_id:
            raise HTTPException(403, "a scoped approval is required for this worker action")
        try:
            approval = approval_service.consume(
                body.approval_id, action=body.action, target=body.path or "command", payload=payload,
            )
        except ApprovalError as exc:
            raise HTTPException(403, _safe_exc_msg(exc)) from exc
        await infrastructure.persist_external_approval(approval)
    try:
        result = await implementation_worker.execute(payload)
    except ImplementationWorkerError as exc:
        event = AuditEvent(action=f"worker.{body.action}", actor=agent.name, target=body.path or "command", outcome="failed", details={"reason": _safe_exc_msg(exc)})
        store.log(event)
        await infrastructure.persist_audit(event)
        raise HTTPException(503, _safe_exc_msg(exc)) from exc
    exit_code = result.get("exit_code")
    outcome = "previewed" if body.action == "preview_write" else "failed" if exit_code not in {None, 0} else "completed"
    event = AuditEvent(
        action=f"worker.{body.action}", actor=agent.name, target=body.path or "command", outcome=outcome,
        details={"duration_ms": result.get("duration_ms"), "exit_code": result.get("exit_code"), "before_sha256": result.get("before_sha256"), "after_sha256": result.get("after_sha256")},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    if outcome == "completed" and body.action in {"file_write", "code_execute", "test_execute"}:
        evidence_type = "test" if body.action == "test_execute" else "implementation"
        lifecycle = next((item for item in store.lifecycles.values() if item.plan_id == plan_workspace.plan_id), None)
        if lifecycle:
            lifecycle.evidence.append({
                "stage": lifecycle.stage,
                "type": evidence_type,
                "status": "passed",
                "source": "implementation-worker",
                "action": body.action,
                "path": body.path,
                "command": body.command,
                "before_sha256": result.get("before_sha256"),
                "after_sha256": result.get("after_sha256"),
                "exit_code": exit_code,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
            lifecycle.updated_at = datetime.now(timezone.utc)
            await infrastructure.persist_lifecycle(lifecycle)
    await broadcast({"type": "worker.action", "agent": agent.name, "action": body.action, "outcome": outcome, "target": body.path or "command"})
    return result


def change_set_apply_payload(change_set: ChangeSet) -> dict:
    return {
        "change_set_id": str(change_set.id), "workspace_id": str(change_set.workspace_id),
        "files": [
            {"path": item.path, "content": item.content, "expected_sha256": item.expected_sha256}
            for item in change_set.files
        ],
    }


@app.get("/api/change-sets", response_model=list[ChangeSet])
async def change_sets(plan_id: UUID | None = None):
    values = [item for item in store.change_sets.values() if item.removed_at is None]
    if plan_id:
        values = [item for item in values if item.plan_id == plan_id]
    return sorted(values, key=lambda item: item.updated_at, reverse=True)


@app.get("/api/change-sets/{change_set_id}", response_model=ChangeSet)
async def get_change_set(change_set_id: UUID):
    change_set = store.change_sets.get(change_set_id)
    if not change_set or change_set.removed_at is not None:
        raise HTTPException(404, "Forge change set not found")
    return change_set


@app.delete("/api/change-sets/{change_set_id}", status_code=204)
async def delete_change_set(change_set_id: UUID, approval_id: UUID):
    change_set = store.change_sets.get(change_set_id)
    if not change_set or change_set.removed_at is not None:
        raise HTTPException(404, "Forge change set not found")
    payload = {
        "operation": "soft_delete", "change_set_id": str(change_set.id),
        "plan_id": str(change_set.plan_id), "status": change_set.status,
    }
    try:
        approval = approval_service.consume(
            approval_id, action="change_set_delete", target=str(change_set.id), payload=payload,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    now = datetime.now(timezone.utc)
    change_set.removed_at = now
    change_set.updated_at = now
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_change_set(change_set)
    event = AuditEvent(
        action="forge.change_set.delete", actor="local-user", target=str(change_set.id), outcome="soft_deleted",
        details={
            "title": change_set.title, "status": change_set.status, "plan_id": str(change_set.plan_id),
            "workspace_id": str(change_set.workspace_id), "files": [item.path for item in change_set.files],
            "file_hashes": [{"path": item.path, "before": item.before_sha256, "after": item.after_sha256} for item in change_set.files],
            "branch": change_set.branch, "commit": change_set.commit, "approval_id": str(approval.id),
            "record_retained": True, "workspace_changes_reverted": False,
        },
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    await broadcast({"type": "forge.change_set", "change_set_id": str(change_set.id), "status": "removed", "message": "Implementation removed from active work"})
    return Response(status_code=204)


@app.get("/api/change-sets/{change_set_id}/file")
async def get_change_set_file(change_set_id: UUID, path: str):
    change_set = store.change_sets.get(change_set_id)
    if not change_set or change_set.removed_at is not None:
        raise HTTPException(404, "Forge change set not found")
    proposed = next((item for item in change_set.files if item.path == path), None)
    if not proposed:
        raise HTTPException(404, "file is not part of this Forge change set")
    try:
        current = await implementation_worker.execute({
            "action": "read_file", "workspace_id": str(change_set.workspace_id), "path": path,
        })
    except ImplementationWorkerError as exc:
        if proposed.before_sha256 == hashlib.sha256(b"").hexdigest():
            current = {"content": "", "sha256": proposed.before_sha256}
        else:
            raise HTTPException(503, _safe_exc_msg(exc)) from exc
    result = {
        "change_set_id": change_set.id, "path": path, "status": change_set.status,
        "current_content": current.get("content", ""), "current_sha256": current.get("sha256", ""),
        "proposed_content": proposed.content, "proposed_sha256": proposed.after_sha256, "diff": proposed.diff,
    }
    event = AuditEvent(action="forge.change_set.file_view", actor="local-user", target=str(change_set.id), outcome="allowed", details={"path": path})
    store.log(event)
    await infrastructure.persist_audit(event)
    return result


@app.post("/api/change-sets/{change_set_id}/apply", response_model=ChangeSet)
async def apply_change_set(change_set_id: UUID, body: ChangeSetApproval):
    change_set = store.change_sets.get(change_set_id)
    if not change_set or change_set.removed_at is not None:
        raise HTTPException(404, "Forge change set not found")
    if change_set.status != "pending_review":
        raise HTTPException(409, "only a pending Forge change set can be applied")
    if not body.user_authorized:
        raise HTTPException(403, "explicit user authorization is required")
    payload = change_set_apply_payload(change_set)
    try:
        approval = approval_service.consume(body.approval_id, action="change_set_apply", target=str(change_set.id), payload=payload)
        await infrastructure.persist_external_approval(approval)
        result = await implementation_worker.execute({"action": "apply_change_set", **payload})
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    except ImplementationWorkerError as exc:
        change_set.status = "failed"
        change_set.updated_at = datetime.now(timezone.utc)
        await infrastructure.persist_change_set(change_set)
        raise HTTPException(503, _safe_exc_msg(exc)) from exc
    change_set.status = "applied"
    change_set.updated_at = datetime.now(timezone.utc)
    await infrastructure.persist_change_set(change_set)
    lifecycle = next((item for item in store.lifecycles.values() if item.plan_id == change_set.plan_id), None)
    if lifecycle:
        lifecycle.evidence.append({"stage": "development", "type": "implementation", "status": "passed", "source": "forge-change-set", "change_set_id": str(change_set.id), "files": [item.path for item in change_set.files], "recorded_at": change_set.updated_at.isoformat()})
        lifecycle.updated_at = change_set.updated_at
        await infrastructure.persist_lifecycle(lifecycle)
    event = AuditEvent(action="forge.change_set.apply", actor="local-user", target=str(change_set.id), outcome="completed", details={"files": len(change_set.files), "duration_ms": result.get("duration_ms")})
    store.log(event)
    await infrastructure.persist_audit(event)
    await broadcast({"type": "forge.change_set", "change_set_id": str(change_set.id), "status": change_set.status, "message": "Approved multi-file change set applied"})
    return change_set


@app.post("/api/change-sets/{change_set_id}/test", response_model=ChangeSet)
async def test_change_set(change_set_id: UUID, body: ChangeSetTestRequest):
    change_set = store.change_sets.get(change_set_id)
    if not change_set or change_set.removed_at is not None:
        raise HTTPException(404, "Forge change set not found")
    if change_set.status not in {"applied", "tests_passed"}:
        raise HTTPException(409, "apply the approved change set before running its tests")
    if not body.user_authorized:
        raise HTTPException(403, "explicit user authorization is required")
    payload = {"change_set_id": str(change_set.id), "workspace_id": str(change_set.workspace_id), "command": body.command, "timeout_seconds": body.timeout_seconds}
    try:
        approval = approval_service.consume(body.approval_id, action="test_execute", target=str(change_set.id), payload=payload)
        await infrastructure.persist_external_approval(approval)
        result = await implementation_worker.execute({
            "action": "test_execute", "workspace_id": str(change_set.workspace_id), "path": ".",
            "command": body.command, "timeout_seconds": body.timeout_seconds,
        })
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    except ImplementationWorkerError as exc:
        raise HTTPException(503, _safe_exc_msg(exc)) from exc
    change_set.test_result = result
    change_set.status = "tests_passed" if result.get("exit_code") == 0 else "failed"
    change_set.updated_at = datetime.now(timezone.utc)
    await infrastructure.persist_change_set(change_set)
    lifecycle = next((item for item in store.lifecycles.values() if item.plan_id == change_set.plan_id), None)
    if lifecycle:
        lifecycle.evidence.append({"stage": lifecycle.stage, "type": "test", "status": "passed" if result.get("exit_code") == 0 else "failed", "source": "forge-change-set", "change_set_id": str(change_set.id), "command": body.command, "exit_code": result.get("exit_code"), "recorded_at": change_set.updated_at.isoformat()})
        lifecycle.updated_at = change_set.updated_at
        await infrastructure.persist_lifecycle(lifecycle)
    event = AuditEvent(action="forge.change_set.test", actor="local-user", target=str(change_set.id), outcome=change_set.status, details={"command": body.command, "exit_code": result.get("exit_code")})
    store.log(event)
    await infrastructure.persist_audit(event)
    return change_set


@app.post("/api/change-sets/{change_set_id}/commit", response_model=ChangeSet)
async def commit_change_set(change_set_id: UUID, body: ChangeSetCommitRequest):
    change_set = store.change_sets.get(change_set_id)
    if not change_set or change_set.removed_at is not None:
        raise HTTPException(404, "Forge change set not found")
    if change_set.status != "tests_passed":
        raise HTTPException(409, "passing test evidence is required before a governed commit")
    if not body.user_authorized:
        raise HTTPException(403, "explicit user authorization is required")
    payload = {
        "change_set_id": str(change_set.id), "workspace_id": str(change_set.workspace_id),
        "branch": body.branch, "message": body.message, "paths": [item.path for item in change_set.files],
    }
    try:
        approval = approval_service.consume(body.approval_id, action="git_commit", target=str(change_set.id), payload=payload)
        await infrastructure.persist_external_approval(approval)
        result = await implementation_worker.execute({
            "action": "git_commit", "workspace_id": str(change_set.workspace_id),
            "branch": body.branch, "message": body.message,
            "files": [{"path": item.path, "content": item.content, "expected_sha256": item.after_sha256} for item in change_set.files],
        })
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    except ImplementationWorkerError as exc:
        raise HTTPException(503, _safe_exc_msg(exc)) from exc
    change_set.status = "committed"
    change_set.branch = result.get("branch", body.branch)
    change_set.commit = result.get("commit", "")
    change_set.updated_at = datetime.now(timezone.utc)
    await infrastructure.persist_change_set(change_set)
    lifecycle = next((item for item in store.lifecycles.values() if item.plan_id == change_set.plan_id), None)
    if lifecycle:
        lifecycle.evidence.append({"stage": lifecycle.stage, "type": "implementation", "status": "passed", "source": "governed-git-commit", "change_set_id": str(change_set.id), "branch": change_set.branch, "commit": change_set.commit, "recorded_at": change_set.updated_at.isoformat()})
        lifecycle.updated_at = change_set.updated_at
        await infrastructure.persist_lifecycle(lifecycle)
    event = AuditEvent(action="forge.change_set.commit", actor="local-user", target=str(change_set.id), outcome="completed", details={"branch": change_set.branch, "commit": change_set.commit})
    store.log(event)
    await infrastructure.persist_audit(event)
    return change_set


@app.post("/api/approvals", response_model=ApprovalChallengeResponse, status_code=202)
async def request_protected_action(body: ProtectedActionRequest):
    approval = approval_service.request(body)
    event = AuditEvent(action="approval.request", actor=body.actor, target=str(approval.id), outcome="pending", details={"protected_action": body.action, "target": body.target, "action_hash": approval.action_hash})
    store.log(event)
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_audit(event)
    return ApprovalChallengeResponse(**approval.model_dump(), challenge_code=issue_approval_challenge(approval.id))


@app.post("/api/approvals/{approval_id}/challenge")
async def refresh_approval_challenge(approval_id: UUID):
    approval = store.external_approvals.get(approval_id)
    if not approval:
        raise HTTPException(404, "approval request not found")
    if approval.status != "pending":
        raise HTTPException(409, "only a pending approval can receive a new challenge")
    return {"approval_id": approval_id, "challenge_code": issue_approval_challenge(approval_id), "expires_in_seconds": 300}


@app.post("/api/approvals/{approval_id}/decision", response_model=ExternalActionApproval)
async def decide_protected_action(approval_id: UUID, body: ExternalActionDecision):
    try:
        approval = approval_service.decide(
            approval_id, body.decision, passcode_verified=body.user_authorized and approval_challenge_valid(approval_id, body.approval_passcode),
        )
    except ApprovalError as exc:
        status = 404 if "not found" in str(exc) else 403 if "passcode" in str(exc) else 409
        raise HTTPException(status, _safe_exc_msg(exc)) from exc
    event = AuditEvent(action="approval.decision", actor="local-user", target=str(approval.id), outcome=approval.status, details={"protected_action": approval.action, "target": approval.target, "reason": body.reason})
    store.log(event)
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_audit(event)
    return approval


@app.get("/api/external-approvals", response_model=list[ExternalActionApproval])
async def external_approvals():
    now = datetime.now(timezone.utc)
    for approval in store.external_approvals.values():
        if approval.status == "approved" and approval.expires_at <= now:
            approval.status = "expired"
    return sorted(store.external_approvals.values(), key=lambda item: item.created_at, reverse=True)


@app.post("/api/external-approvals", response_model=ApprovalChallengeResponse, status_code=202)
async def request_external_approval(body: ExternalActionRequest):
    if body.action == "docker_action":
        # Atlas Studio intentionally exposes no raw Docker socket. This record
        # is ready for a future narrow, verb-specific broker only.
        purpose = f"{body.purpose} (raw Docker socket access remains disabled)"
    else:
        purpose = body.purpose
    approval = approval_service.request(ProtectedActionRequest(
        action=body.action, purpose=purpose, target="internet" if body.action == "internet_search" else "docker-broker",
        actor="Atlas", payload={"query": body.query, "allowed_domains": body.allowed_domains}, ttl_minutes=body.ttl_minutes,
    ))
    event = AuditEvent(action="external.request", actor="Atlas", target=str(approval.id), outcome="pending", details={"action": approval.action, "purpose": approval.purpose})
    store.log(event)
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_audit(event)
    return ApprovalChallengeResponse(**approval.model_dump(), challenge_code=issue_approval_challenge(approval.id))


@app.post("/api/external-approvals/{approval_id}/decision", response_model=ExternalActionApproval)
async def decide_external_approval(approval_id: UUID, body: ExternalActionDecision):
    try:
        approval = approval_service.decide(approval_id, body.decision, passcode_verified=body.user_authorized and approval_challenge_valid(approval_id, body.approval_passcode))
    except ApprovalError as exc:
        status = 404 if "not found" in str(exc) else 403 if "passcode" in str(exc) else 409
        raise HTTPException(status, _safe_exc_msg(exc)) from exc
    event = AuditEvent(action="external.decision", actor="local-user", target=str(approval.id), outcome=approval.status, details={"action": approval.action, "reason": body.reason})
    store.log(event)
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_audit(event)
    return approval


@app.post("/api/research/search")
async def approved_internet_search(body: ApprovedSearchRequest):
    approval = store.external_approvals.get(body.approval_id)
    now = datetime.now(timezone.utc)
    if not approval or approval.action != "internet_search":
        raise HTTPException(404, "approved internet-search request not found")
    try:
        approval = approval_service.consume(
            body.approval_id, action="internet_search", target="internet",
            payload={"query": approval.query, "allowed_domains": approval.allowed_domains},
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{settings.research_worker_url.rstrip('/')}/search",
                headers={"Authorization": f"Bearer {settings.research_worker_token}"},
                json={"query": approval.query, "allowed_domains": approval.allowed_domains},
            )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, f"approved research route unavailable: {exc.__class__.__name__}") from exc
    event = AuditEvent(action="external.internet_search", actor="Sage", target=str(approval.id), outcome="completed", details={"query": approval.query, "result_count": len(result.get("results", []))})
    store.log(event)
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_audit(event)
    return result


@app.get("/api/security/posture")
async def security_posture():
    """Return controls enforced by the local platform, not model assertions."""
    return build_security_posture(
        list(store.agents.values()),
        list(store.audit),
        sandbox_runtime=settings.sandbox_runtime,
        sandbox_network=settings.sandbox_network,
        telemetry_enabled=settings.telemetry_enabled,
        upload_limit_mb=settings.upload_max_mb,
        workspace_read_only=True,
        kill_switch_engaged=kill_switch.is_set(),
    )


@app.get("/api/agents", response_model=list[Agent])
async def agents():
    return list(store.agents.values())


@app.post("/api/agents", response_model=Agent, status_code=201)
async def create_agent(body: AgentCreate):
    if body.name.casefold() == "atlas":
        raise HTTPException(422, "Atlas is the protected platform orchestrator; choose another agent name")
    if any(agent.name.casefold() == body.name.casefold() for agent in store.agents.values()):
        raise HTTPException(409, "an agent with this name already exists")
    if not body.read_only and not body.requires_user_authorization:
        raise HTTPException(422, "implementation-capable agents must require explicit user authorization")
    agent_payload = body.model_dump(mode="json", exclude={"approval_id"})
    try:
        approval = approval_service.consume(
            body.approval_id, action="agent_permission", target=f"new:{body.name}", payload=agent_payload,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    agent = Agent(**agent_payload, system=False)
    store.agents[agent.id] = agent
    event = AuditEvent(
        action="agent.create",
        actor="local-user",
        target=agent.name,
        outcome="created",
        details={"role": agent.role, "tools": agent.tools, "requires_user_authorization": agent.requires_user_authorization},
    )
    store.log(event)
    await infrastructure.persist_agent(agent)
    await infrastructure.persist_audit(event)
    return agent


@app.patch("/api/agents/{agent_id}", response_model=Agent)
async def update_agent(agent_id: UUID, body: AgentUpdate):
    agent = store.agents.get(agent_id)
    if not agent:
        raise HTTPException(404, "agent not found")
    requested = body.model_dump(exclude={"approval_id"}, exclude_none=True)
    requested_tools = list(dict.fromkeys(requested.get("tools", agent.tools)))
    requested["tools"] = requested_tools
    if "skills" in requested:
        available_skills = skill_runtime.available()
        requested_skills = list(dict.fromkeys(
            skill_runtime.normalize(item).replace("-", "_") for item in requested["skills"]
        ))
        unknown = [item for item in requested_skills if item.replace("_", "-") not in available_skills]
        if unknown:
            raise HTTPException(422, f"unknown bundled skills: {', '.join(unknown)}")
        if "development_lifecycle" not in requested_skills:
            requested_skills.append("development_lifecycle")
        if agent.name == "Atlas" and "atlas_request_intake" not in requested_skills:
            requested_skills.append("atlas_request_intake")
        requested["skills"] = requested_skills
    candidate = agent.model_copy(update=requested)
    if agent.name == "Atlas" and (candidate.name != "Atlas" or not candidate.read_only):
        raise HTTPException(422, "Atlas identity and read-only status are protected")
    if any(item.id != agent.id and item.name.casefold() == candidate.name.casefold() for item in store.agents.values()):
        raise HTTPException(409, "an agent with this name already exists")
    if not candidate.read_only and not candidate.requires_user_authorization:
        raise HTTPException(422, "implementation-capable agents must require explicit user authorization")
    try:
        SecurityPolicy.validate_agent_tools(candidate, requested_tools)
    except ValueError as exc:
        raise HTTPException(422, _safe_exc_msg(exc)) from exc
    changes = {key: value for key, value in requested.items() if getattr(agent, key) != value}
    if not changes:
        return agent
    try:
        approval = approval_service.consume(
            body.approval_id,
            action="agent_permission",
            target=str(agent.id),
            payload=changes,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    for key, value in changes.items():
        setattr(agent, key, value)
    event = AuditEvent(action="agent.update", actor="local-user", target=agent.name, outcome="allowed", details={"changed_fields": sorted(changes), **changes})
    store.log(event)
    await infrastructure.persist_agent(agent)
    await infrastructure.persist_audit(event)
    return agent


@app.delete("/api/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: UUID, approval_id: UUID | None = None):
    agent = store.agents.get(agent_id)
    if not agent:
        raise HTTPException(404, "agent not found")
    if agent.system:
        raise HTTPException(403, "system agents cannot be removed")
    if any(task.agent_id == agent_id and task.status in {"queued", "running"} for task in store.tasks.values()):
        raise HTTPException(409, "cancel this agent's active tasks before removing it")
    try:
        approval = approval_service.consume(
            approval_id, action="agent_permission", target=str(agent.id), payload={"operation": "delete", "name": agent.name},
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    del store.agents[agent_id]
    event = AuditEvent(action="agent.delete", actor="local-user", target=agent.name, outcome="deleted")
    store.log(event)
    await infrastructure.delete_agent(agent_id)
    await infrastructure.persist_audit(event)
    return Response(status_code=204)


@app.get("/api/plans", response_model=list[Plan])
async def plans():
    return sorted((plan for plan in store.plans.values() if plan.status != "deleted"), key=lambda plan: plan.created_at, reverse=True)


def _relevant_plan_reviewers(plan: Plan) -> list[Agent]:
    text = f"{plan.title} {plan.request}".lower()
    names = {"Forge", "Sage", "Blueprint", "Sentinel"}
    rules = {
        "Verity": ("compliance", "grc", "control", "policy", "audit", "privacy"),
        "Counsel": ("legal", "license", "licensing", "terms", "contract", "copyright"),
        "Echo": ("voice", "speech", "audio", "avatar", "microphone"),
    }
    for name, keywords in rules.items():
        if any(keyword in text for keyword in keywords):
            names.add(name)
    # Forge contributes the implementation recommendation in review-only mode;
    # specialist agents then add their independent lifecycle evidence.
    return [agent for agent in store.agents.values() if agent.name in names]


async def _queue_plan_reviews(plan: Plan, *, retry_failed: bool = False, force_all: bool = False) -> list[Task]:
    queued: list[Task] = []
    existing = [task for task in store.tasks.values() if task.plan_id == plan.id and task.title.startswith("Lifecycle review —")]
    for agent in _relevant_plan_reviewers(plan):
        prior = next((task for task in reversed(existing) if task.agent_id == agent.id), None)
        if prior and not force_all and (not retry_failed or prior.status != "failed"):
            continue
        task = await create_task(TaskCreate(
            title=f"Lifecycle review — {agent.name}",
            prompt=(
                "[LIFECYCLE_REVIEW]\n"
                f"Review this proposed platform change strictly within your {agent.role} role. "
                f"Request: {plan.request}\nForge recommendation: {plan.recommendation}\n"
                "Return concrete risks, requirements, acceptance criteria, and evidence references. "
                "Do not implement, write files, or infer facts that are unavailable."
            ),
            agent_id=agent.id, priority="high", user_authorized=False, plan_id=plan.id,
        ))
        queued.append(task)
    return queued


@app.post("/api/plans", response_model=Plan, status_code=201)
async def create_plan(body: PlanCreate):
    forge = next((agent for agent in store.agents.values() if agent.name == "Forge"), None)
    implementation_agent = store.agents.get(body.implementation_agent_id) if body.implementation_agent_id else forge
    if not implementation_agent or implementation_agent.read_only or "files_write" not in implementation_agent.tools:
        raise HTTPException(422, "select an implementation-capable agent with files_write")
    plan = Plan(
        **body.model_dump(exclude={"implementation_agent_id"}), implementation_agent_id=implementation_agent.id,
        recommendation=f"Implement the requested outcome as a scoped, reviewable change in an isolated workspace: {body.request}",
    )
    store.plans[plan.id] = plan
    event = AuditEvent(action="plan.create", actor="local-user", target=str(plan.id), outcome=plan.status, details={"agent": implementation_agent.name, "priority": plan.priority})
    store.log(event)
    await infrastructure.persist_plan(plan)
    await infrastructure.persist_audit(event)
    await _queue_plan_reviews(plan)
    await broadcast({"type": "lifecycle.guide", "plan_id": str(plan.id), "message": "Specialist lifecycle reviews queued"})
    return plan


@app.post("/api/plans/{plan_id}/reviews")
async def retry_plan_reviews(plan_id: UUID):
    plan = store.plans.get(plan_id)
    if not plan or plan.status != "pending_approval":
        raise HTTPException(409, "only a recommendation awaiting approval can request lifecycle reviews")
    queued = await _queue_plan_reviews(plan, retry_failed=True)
    event = AuditEvent(
        action="plan.reviews.request", actor="local-user", target=str(plan.id), outcome="queued",
        details={"task_ids": [str(task.id) for task in queued]},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    return {"queued": [task.model_dump(mode="json") for task in queued]}


@app.post("/api/plans/{plan_id}/reviewers", response_model=Task, status_code=202)
async def add_plan_reviewer(plan_id: UUID, body: PlanReviewerRequest):
    plan = store.plans.get(plan_id)
    agent = store.agents.get(body.agent_id)
    if not plan or plan.status == "deleted":
        raise HTTPException(404, "plan request not found")
    if not agent:
        raise HTTPException(404, "review agent not found")
    lifecycle = next((item for item in store.lifecycles.values() if item.plan_id == plan.id), None)
    change_sets = sorted((item for item in store.change_sets.values() if item.plan_id == plan.id and item.removed_at is None), key=lambda item: item.created_at)
    latest_change = change_sets[-1] if change_sets else None
    current_context = (
        f"Current lifecycle stage: {lifecycle.stage if lifecycle else 'recommendation review'}. "
        f"Latest change set: {latest_change.status if latest_change else 'none'}"
        f"{f' ({len(latest_change.files)} files)' if latest_change else ''}."
    )
    task = await create_task(TaskCreate(
        title=f"Lifecycle review — {agent.name}",
        prompt=(
            f"[LIFECYCLE_REVIEW]\nPerform a review-only contribution as {agent.name}, {agent.role}. "
            f"Focus requested by the user: {body.focus}\nChange request: {plan.request}\n"
            f"Forge recommendation: {plan.recommendation}\n"
            f"{current_context}\n"
            "Return role-specific findings, risks, acceptance criteria, and evidence references. "
            "Do not use implementation tools, write files, execute code, or claim unavailable evidence."
        ),
        agent_id=agent.id, priority="high", user_authorized=False, plan_id=plan.id,
    ))
    event = AuditEvent(
        action="plan.reviewer.add", actor="local-user", target=str(plan.id), outcome="queued",
        details={"agent_id": str(agent.id), "agent": agent.name, "task_id": str(task.id), "focus": body.focus, "review_only": True},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    await broadcast({"type": "lifecycle.guide", "plan_id": str(plan.id), "message": f"{agent.name} added as lifecycle reviewer"})
    return task


@app.patch("/api/plans/{plan_id}/recommendation", response_model=Plan)
async def edit_plan_recommendation(plan_id: UUID, body: PlanRecommendationUpdate):
    plan = store.plans.get(plan_id)
    if not plan:
        raise HTTPException(404, "plan not found")
    if plan.status != "pending_approval":
        raise HTTPException(409, "only a recommendation awaiting user approval can be edited")
    plan.recommendation = body.recommendation
    plan.impact = body.impact
    plan.test_plan = body.test_plan
    plan.rollback_plan = body.rollback_plan
    plan.proposed_files = body.proposed_files
    event = AuditEvent(
        action="plan.recommendation.edited", actor="local-user", target=str(plan.id), outcome="revised",
        details={"reason": body.reason, "proposed_files": body.proposed_files},
    )
    store.log(event)
    await infrastructure.persist_plan(plan)
    await infrastructure.persist_audit(event)
    await _queue_plan_reviews(plan, force_all=True)
    await broadcast({"type": "lifecycle.guide", "plan_id": str(plan.id), "message": "Forge recommendation revised by user"})
    return plan


@app.delete("/api/plans/{plan_id}", status_code=204)
async def delete_plan_request(plan_id: UUID, approval_id: UUID):
    plan = store.plans.get(plan_id)
    if not plan or plan.status == "deleted":
        raise HTTPException(404, "plan request not found")
    payload = {"operation": "soft_delete", "plan_id": str(plan.id), "title": plan.title}
    try:
        approval = approval_service.consume(approval_id, action="plan_delete", target=str(plan.id), payload=payload)
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    plan.status = "deleted"
    plan.decided_at = datetime.now(timezone.utc)
    for task in store.tasks.values():
        if task.plan_id == plan.id and task.status in {"queued", "running"}:
            task.status = "cancelled"
            task.updated_at = plan.decided_at
            await task_queue.remove(task.id)
            await infrastructure.persist_task(task)
    for change_set in store.change_sets.values():
        if change_set.plan_id == plan.id and change_set.status == "pending_review":
            change_set.status = "rejected"
            change_set.updated_at = plan.decided_at
            await infrastructure.persist_change_set(change_set)
    event = AuditEvent(
        action="plan.delete", actor="local-user", target=str(plan.id), outcome="soft_deleted",
        details={"title": plan.title, "approval_id": str(approval.id), "audit_retained": True},
    )
    store.log(event)
    await infrastructure.persist_plan(plan)
    await infrastructure.persist_audit(event)
    await broadcast({"type": "lifecycle.guide", "plan_id": str(plan.id), "message": "Change request deleted by user"})
    return Response(status_code=204)


def _notification_status(notification_id: str) -> str:
    for event in store.audit:
        if event.target == notification_id and event.action.startswith("lifecycle.notification."):
            return event.action.rsplit(".", 1)[-1]
    return "unread"


def _lifecycle_guide_entry(plan: Plan) -> dict:
    lifecycle = next((item for item in store.lifecycles.values() if item.plan_id == plan.id), None)
    tasks = sorted((item for item in store.tasks.values() if item.plan_id == plan.id), key=lambda item: item.created_at)
    change_sets = sorted((item for item in store.change_sets.values() if item.plan_id == plan.id and item.removed_at is None), key=lambda item: item.updated_at)
    change_set = change_sets[-1] if change_sets else None
    review_latest: dict[UUID, Task] = {}
    for task in tasks:
        if task.title.startswith("Lifecycle review —"):
            review_latest[task.agent_id] = task
    review_tasks = list(review_latest.values())
    reviews_complete = bool(review_tasks) and all(item.status == "completed" for item in review_tasks)
    passed_evidence = [item for item in (lifecycle.evidence if lifecycle else []) if item.get("status") == "passed"]
    qa_passed = any(item.get("type") in {"test", "security"} for item in passed_evidence)
    sandbox_passed = any(item.get("stage") == "sandbox" for item in passed_evidence)
    implementation_done = bool(change_set and change_set.status in {"applied", "tests_passed", "committed"})

    stages = [
        {"id": "request", "label": "Change request", "owner": "User", "status": "completed", "destination": "plans"},
        {"id": "recommendation", "label": "Forge recommendation", "owner": "Forge", "status": "awaiting_user" if plan.status == "pending_approval" else "completed", "destination": "plans"},
        {"id": "reviews", "label": "Relevant agent reviews", "owner": "Specialist agents", "status": "completed" if reviews_complete else ("active" if review_tasks else "locked"), "destination": "lifecycleGuide"},
        {"id": "authorization", "label": "User authorization", "owner": "User", "status": "rejected" if plan.status == "rejected" else ("awaiting_user" if plan.status == "pending_approval" else "completed"), "destination": "plans"},
        {"id": "implementation", "label": "Implementation", "owner": "Forge", "status": "completed" if implementation_done or (lifecycle and lifecycle.stage != "development") else ("active" if plan.status == "in_progress" else "locked"), "destination": "implementation"},
        {"id": "diff", "label": "Diff review", "owner": "User", "status": "awaiting_user" if change_set and change_set.status == "pending_review" else ("completed" if implementation_done else "locked"), "destination": "implementation"},
        {"id": "test", "label": "QA pipeline", "owner": "Quanta", "status": "completed" if qa_passed or (lifecycle and lifecycle.stage in {"sandbox", "production"}) else ("active" if lifecycle and lifecycle.stage == "test" else "locked"), "destination": "qa"},
        {"id": "sandbox", "label": "Sandbox validation", "owner": "Sentinel + Quanta", "status": "completed" if sandbox_passed or (lifecycle and lifecycle.stage == "production") else ("active" if lifecycle and lifecycle.stage == "sandbox" else "locked"), "destination": "environments"},
        {"id": "production", "label": "Production approval", "owner": "User", "status": "completed" if lifecycle and lifecycle.stage == "production" else ("awaiting_user" if lifecycle and lifecycle.stage == "sandbox" and sandbox_passed else "locked"), "destination": "qa"},
        {"id": "monitoring", "label": "Monitoring and audit", "owner": "Release + Sentinel", "status": "active" if lifecycle and lifecycle.stage == "production" else "locked", "destination": "analytics"},
    ]

    if plan.status == "pending_approval" and not reviews_complete:
        action = ("complete-reviews", "Complete relevant agent reviews", "Review Forge, Sage, Blueprint, Sentinel, and any user-added specialist findings. Retry a failed review before authorizing implementation.", "lifecycleGuide", "high")
    elif plan.status == "pending_approval":
        action = ("review-recommendation", "Review or edit Forge's recommendation", "Inspect the proposed solution, impact, tests, rollback, and files. Approve only when it matches your intent.", "plans", "high")
    elif plan.status == "rejected":
        action = ("revise-request", "Revise the rejected change request", "Create a corrected plan request before implementation can begin.", "plans", "normal")
    elif change_set and change_set.status == "pending_review":
        action = ("review-diff", "Review Forge's proposed code diff", "Accept, edit, or reject the exact multi-file patch before any file is written.", "implementation", "critical")
    elif change_set and change_set.status == "applied":
        action = ("approve-tests", "Approve the focused test run", "Review the applied change evidence, then authorize Forge to run the approved tests.", "implementation", "high")
    elif lifecycle and lifecycle.stage == "development" and implementation_done:
        action = ("promote-test", "Move the change to Test", "Record the completed implementation evidence and advance the lifecycle to Test.", "qa", "high")
    elif lifecycle and lifecycle.stage == "development":
        action = ("monitor-forge", "Review Forge implementation progress", "Forge is preparing a reviewable recommendation and code diff in the isolated workspace.", "implementation", "normal")
    elif lifecycle and lifecycle.stage == "test" and not qa_passed:
        action = ("run-full-qa", "Run the full QA pipeline", "Authorize Quanta to run repository, API, UI contract, governance, and audit checks.", "qa", "critical")
    elif lifecycle and lifecycle.stage == "test":
        action = ("promote-sandbox", "Review QA evidence and promote to Sandbox", "Confirm the passing QA evidence before isolated Sandbox validation begins.", "qa", "high")
    elif lifecycle and lifecycle.stage == "sandbox" and not sandbox_passed:
        action = ("record-sandbox", "Complete Sandbox validation", "Run the approved security and release checks, then record their machine evidence.", "environments", "high")
    elif lifecycle and lifecycle.stage == "sandbox":
        action = ("approve-production", "Approve Production promotion", "Review Sandbox evidence and use the one-time passcode to authorize Production.", "qa", "critical")
    else:
        action = ("monitor-production", "Monitor the released change", "Review operational metrics, audit events, and rollback readiness.", "analytics", "normal")

    notification_id = f"{plan.id}:{action[0]}"
    return {
        "plan": plan.model_dump(mode="json"),
        "lifecycle": lifecycle.model_dump(mode="json") if lifecycle else None,
        "change_set": change_set.model_dump(mode="json") if change_set else None,
        "tasks": [item.model_dump(mode="json") for item in tasks],
        "stages": stages,
        "progress": round(sum(1 for item in stages if item["status"] == "completed") / len(stages) * 100),
        "next_action": {
            "id": action[0], "title": action[1], "message": action[2], "destination": action[3], "priority": action[4],
            "notification_id": notification_id, "status": _notification_status(notification_id),
        },
    }


@app.get("/api/lifecycle-guide")
async def lifecycle_guide():
    entries = [_lifecycle_guide_entry(plan) for plan in sorted((item for item in store.plans.values() if item.status != "deleted"), key=lambda item: item.created_at, reverse=True)]
    notifications = [entry["next_action"] | {"plan_id": str(entry["plan"]["id"]), "project": entry["plan"]["title"]} for entry in entries if entry["next_action"]["status"] != "dismissed"]
    return {"entries": entries, "notifications": notifications, "unread": sum(1 for item in notifications if item["status"] == "unread")}


@app.post("/api/lifecycle-notifications/{notification_id}/state")
async def set_lifecycle_notification_state(notification_id: str, body: LifecycleNotificationDecision):
    valid_ids = {entry["next_action"]["notification_id"] for entry in (_lifecycle_guide_entry(plan) for plan in store.plans.values())}
    if notification_id not in valid_ids:
        raise HTTPException(404, "lifecycle notification is no longer active")
    event = AuditEvent(
        action=f"lifecycle.notification.{body.status}", actor="local-user", target=notification_id, outcome=body.status,
        details={"source": "lifecycle-guide"},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    return {"notification_id": notification_id, "status": body.status}


@app.post("/api/plans/{plan_id}/decision")
async def decide_plan(plan_id: UUID, body: PlanDecision):
    plan = store.plans.get(plan_id)
    if not plan:
        raise HTTPException(404, "plan not found")
    if plan.status != "pending_approval":
        raise HTTPException(409, "plan already has a decision")
    if not body.user_authorized:
        raise HTTPException(403, "explicit user authorization is required for plan decisions")
    if body.decision == "approved":
        review_latest: dict[UUID, Task] = {}
        for task in sorted(store.tasks.values(), key=lambda item: item.created_at):
            if task.plan_id == plan.id and task.title.startswith("Lifecycle review —"):
                review_latest[task.agent_id] = task
        reviews = list(review_latest.values())
        if not reviews:
            raise HTTPException(409, "specialist lifecycle reviews must be requested before implementation approval")
        if any(task.status != "completed" for task in reviews):
            raise HTTPException(409, "specialist lifecycle reviews must complete before implementation approval")
    decision_payload = {"decision": body.decision, "reason": body.reason}
    try:
        approval = approval_service.consume(
            body.approval_id, action="plan_decision", target=str(plan.id), payload=decision_payload,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    result: dict = {"plan": plan.model_dump(mode="json"), "lifecycle": None, "task": None}
    if body.decision == "approved":
        plan_workspace = PlanWorkspace(plan_id=plan.id, root="")
        plan_workspace.root = f"/workspaces/{plan_workspace.id}"
        try:
            await implementation_worker.execute({
                "action": "workspace_create", "path": "", "content": None, "expected_sha256": None,
                "command": [], "timeout_seconds": 300, "workspace_id": str(plan_workspace.id),
            })
            plan_workspace.status = "ready"
        except ImplementationWorkerError as exc:
            plan_workspace.status = "blocked"
            store.plan_workspaces[plan_workspace.id] = plan_workspace
            await infrastructure.persist_plan_workspace(plan_workspace)
            raise HTTPException(503, f"isolated plan workspace could not be created: {exc}") from exc
        store.plan_workspaces[plan_workspace.id] = plan_workspace
        plan.workspace_id = plan_workspace.id
        await infrastructure.persist_plan_workspace(plan_workspace)
        lifecycle = DevelopmentLifecycle(plan_id=plan.id, title=plan.title)
        store.lifecycles[lifecycle.id] = lifecycle
        lifecycle_event = AuditEvent(action="lifecycle.create", actor="local-user", target=str(lifecycle.id), outcome="development", details={"plan_id": str(plan.id)})
        store.log(lifecycle_event)
        await infrastructure.persist_lifecycle(lifecycle)
        await infrastructure.persist_audit(lifecycle_event)
        task = await create_task(TaskCreate(
            title=plan.title,
            prompt=plan.request,
            agent_id=plan.implementation_agent_id,
            priority=plan.priority,
            user_authorized=True,
            plan_id=plan.id,
            workspace_id=plan_workspace.id,
        ))
        plan.status = "in_progress"
        result["lifecycle"] = lifecycle.model_dump(mode="json")
        result["task"] = task.model_dump(mode="json")
        await infrastructure.persist_lifecycle(lifecycle)
    else:
        plan.status = "rejected"
    plan.decided_at = datetime.now(timezone.utc)
    event = AuditEvent(action="plan.decision", actor="local-user", target=str(plan.id), outcome=body.decision, details={"reason": body.reason})
    store.log(event)
    await infrastructure.persist_plan(plan)
    await infrastructure.persist_audit(event)
    result["plan"] = plan.model_dump(mode="json")
    return result


@app.get("/api/lifecycles", response_model=list[DevelopmentLifecycle])
async def lifecycles():
    return sorted(store.lifecycles.values(), key=lambda item: item.updated_at, reverse=True)


@app.post("/api/lifecycles", response_model=DevelopmentLifecycle, status_code=201)
async def create_lifecycle(body: LifecycleCreate):
    plan = store.plans.get(body.plan_id)
    if not plan or plan.status not in {"approved", "in_progress"}:
        raise HTTPException(409, "an approved plan is required")
    lifecycle = DevelopmentLifecycle(plan_id=plan.id, title=plan.title)
    store.lifecycles[lifecycle.id] = lifecycle
    event = AuditEvent(action="lifecycle.create", actor="local-user", target=str(lifecycle.id), outcome="development", details={"plan_id": str(plan.id)})
    store.log(event)
    await infrastructure.persist_lifecycle(lifecycle)
    await infrastructure.persist_audit(event)
    return lifecycle


@app.post("/api/lifecycles/{lifecycle_id}/transition", response_model=DevelopmentLifecycle)
async def transition_lifecycle(lifecycle_id: UUID, body: LifecycleTransition):
    lifecycle = store.lifecycles.get(lifecycle_id)
    if not lifecycle:
        raise HTTPException(404, "development lifecycle not found")
    order = ["development", "test", "sandbox", "production"]
    current_index = order.index(lifecycle.stage)
    target_index = order.index(body.target_stage)
    if target_index != current_index + 1:
        raise HTTPException(409, f"next permitted stage is {order[min(current_index + 1, len(order) - 1)]}")
    if not body.evidence.strip():
        raise HTTPException(422, "validation evidence is required to advance the lifecycle")
    plan_tasks = [task for task in store.tasks.values() if task.plan_id == lifecycle.plan_id]
    recorded_evidence = [item for item in lifecycle.evidence if item.get("status") == "passed"]
    evidence_task = store.tasks.get(body.task_id) if body.task_id else None
    if evidence_task and (evidence_task.plan_id != lifecycle.plan_id or evidence_task.status != "completed"):
        raise HTTPException(409, "evidence task must be a completed task belonging to this plan")
    if body.target_stage == "test":
        implementation_recorded = any(item.get("type") == "implementation" for item in recorded_evidence)
        if body.evidence_type != "implementation" or not (implementation_recorded or any(task.status == "completed" for task in plan_tasks)):
            raise HTTPException(409, "a completed implementation task is required before Test")
    elif body.target_stage == "sandbox":
        if body.evidence_type not in {"test", "security"} or not any(item.get("type") in {"test", "security"} for item in recorded_evidence):
            raise HTTPException(409, "machine-recorded passing test or security evidence is required before Sandbox")
    elif body.target_stage == "production":
        sandbox_recorded = any(item.get("stage") == "sandbox" and item.get("status") == "passed" for item in recorded_evidence)
        if body.evidence_type not in {"sandbox", "release"} or not sandbox_recorded:
            raise HTTPException(409, "sandbox or release evidence is required before Production")
        if not body.user_authorized:
            raise HTTPException(403, "explicit user authorization is required for Production")
        try:
            approval = approval_service.consume(
                body.approval_id,
                action="production_promotion",
                target=str(lifecycle.id),
                payload={"target_stage": "production", "evidence": body.evidence, "evidence_type": body.evidence_type},
            )
        except ApprovalError as exc:
            raise HTTPException(403, _safe_exc_msg(exc)) from exc
        await infrastructure.persist_external_approval(approval)
    lifecycle.gates[lifecycle.stage] = "passed"
    lifecycle.stage = body.target_stage
    lifecycle.gates[body.target_stage] = "passed" if body.target_stage == "production" else "active"
    lifecycle.evidence.append({"stage": body.target_stage, "type": body.evidence_type, "status": "passed", "source": "lifecycle-gate", "evidence": body.evidence, "task_id": str(body.task_id) if body.task_id else None, "user_authorized": body.user_authorized, "recorded_at": datetime.now(timezone.utc).isoformat()})
    lifecycle.updated_at = datetime.now(timezone.utc)
    if body.target_stage == "production":
        lifecycle.status = "completed"
        plan = store.plans.get(lifecycle.plan_id)
        if plan:
            plan.status = "completed"
            await infrastructure.persist_plan(plan)
    event = AuditEvent(
        action="lifecycle.transition", actor="local-user", target=str(lifecycle.id), outcome=body.target_stage,
        details={
            "from_stage": order[current_index], "to_stage": body.target_stage,
            "evidence_type": body.evidence_type, "task_id": str(body.task_id) if body.task_id else None,
            "user_authorized": body.user_authorized,
        },
    )
    store.log(event)
    await infrastructure.persist_lifecycle(lifecycle)
    await infrastructure.persist_audit(event)
    return lifecycle


@app.post("/api/lifecycles/{lifecycle_id}/override", response_model=DevelopmentLifecycle)
async def override_lifecycle_environment(lifecycle_id: UUID, body: LifecycleOverride):
    lifecycle = store.lifecycles.get(lifecycle_id)
    if not lifecycle:
        raise HTTPException(404, "development lifecycle not found")
    current_environment = "workspace" if lifecycle.stage in {"development", "test"} else lifecycle.stage
    if body.target_environment == current_environment:
        raise HTTPException(409, "project is already in that environment")
    payload = {"target_environment": body.target_environment, "reason": body.reason}
    try:
        approval = approval_service.consume(
            body.approval_id,
            action="lifecycle_override",
            target=str(lifecycle.id),
            payload=payload,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    previous_stage = lifecycle.stage
    target_stage = {"workspace": "development", "sandbox": "sandbox", "production": "production"}[body.target_environment]
    lifecycle.stage = target_stage
    lifecycle.status = "completed" if target_stage == "production" else "active"
    lifecycle.gates = {
        "development": "active" if target_stage == "development" else "passed",
        "test": "locked" if target_stage == "development" else "passed",
        "sandbox": "active" if target_stage == "sandbox" else ("passed" if target_stage == "production" else "locked"),
        "production": "passed" if target_stage == "production" else "locked",
    }
    recorded_at = datetime.now(timezone.utc)
    lifecycle.updated_at = recorded_at
    lifecycle.evidence.append({
        "stage": target_stage,
        "type": "override",
        "status": "overridden",
        "source": "user-environment-override",
        "from_stage": previous_stage,
        "reason": body.reason,
        "user_authorized": True,
        "approval_id": str(approval.id),
        "recorded_at": recorded_at.isoformat(),
    })
    plan = store.plans.get(lifecycle.plan_id)
    if plan:
        plan.status = "completed" if target_stage == "production" else "in_progress"
        await infrastructure.persist_plan(plan)
    event = AuditEvent(
        action="lifecycle.override",
        actor="local-user",
        target=str(lifecycle.id),
        outcome=body.target_environment,
        details={
            "from_stage": previous_stage,
            "to_stage": target_stage,
            "reason": body.reason,
            "approval_id": str(approval.id),
        },
    )
    store.log(event)
    await infrastructure.persist_lifecycle(lifecycle)
    await infrastructure.persist_audit(event)
    return lifecycle


@app.get("/api/tool-library")
async def tool_library():
    """Return the actual ToolId registry enriched with current agent assignments."""
    return build_tool_catalog(list(store.agents.values()))


@app.get("/api/plugins")
async def plugins():
    """Expose bundled local skills as inspectable, offline plugin records."""
    root = (Path.cwd() / "skills").resolve()
    records = []
    if not root.is_dir():
        return records
    for manifest in sorted(root.glob("*/SKILL.md")):
        text = manifest.read_text(encoding="utf-8", errors="replace")
        name = re.search(r"(?m)^name:\s*([^\n]+)", text)
        description = re.search(r"(?m)^description:\s*([^\n]+)", text)
        records.append({
            "id": manifest.parent.name,
            "name": (name.group(1).strip() if name else manifest.parent.name).replace("-", " ").title(),
            "description": description.group(1).strip() if description else "Bundled local Atlas skill",
            "kind": "local_skill",
            "status": "enabled",
            "source": "Bundled with Atlas Studio",
            "manifest_path": manifest.relative_to(Path.cwd()).as_posix(),
            "network_required": False,
            "edit_policy": "Forge review and approval required",
        })
    return records


@app.get("/api/tool-library/changes", response_model=list[LibraryChange])
async def library_changes():
    return sorted(store.library_changes.values(), key=lambda change: change.created_at, reverse=True)


@app.post("/api/tool-library/changes", response_model=LibraryChange, status_code=202)
async def request_library_change(body: LibraryChangeRequest):
    change = LibraryChange(**body.model_dump())
    store.library_changes[change.id] = change
    event = AuditEvent(action=f"tool.library.{change.action}", actor="local-user", target=change.tool_id, outcome=change.status, details={"change_id": str(change.id), "reason": change.reason})
    store.log(event)
    await infrastructure.persist_library_change(change)
    await infrastructure.persist_audit(event)
    return change


@app.post("/api/tool-library/{tool_id}/request")
async def request_tool_access(tool_id: str, body: ToolAccessRequest):
    catalog = {item["id"]: item for item in build_tool_catalog(list(store.agents.values()))}
    tool = catalog.get(tool_id)
    if not tool:
        raise HTTPException(404, "tool is not registered in Atlas Studio")
    agent = store.agents.get(body.agent_id) if body.agent_id else None
    if body.agent_id and not agent:
        raise HTTPException(404, "agent not found")
    if body.environment == "production" or tool["restricted"]:
        status = "administrative_review_required"
    elif tool["authorization_required"]:
        status = "user_authorization_required"
    else:
        status = "ready_for_agent_assignment"
    event = AuditEvent(
        action="tool.access.request",
        actor="local-user",
        target=tool_id,
        outcome=status,
        details={
            "agent": agent.name if agent else None,
            "environment": body.environment,
            "reason": body.reason,
            "capability_granted": False,
        },
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    return {
        "tool_id": tool_id,
        "status": status,
        "capability_granted": False,
        "next_step": "Assign the capability to an agent from the Agents page after the required authorization review.",
    }


@app.get("/api/sources")
async def sources(q: str = "", category: str = ""):
    items = build_source_catalog()
    if category:
        items = [item for item in items if item["category"].casefold() == category.casefold()]
    if q.strip():
        needle = q.casefold().strip()
        items = [
            item for item in items
            if needle in " ".join(
                [item["name"], item["authority"], item["source_type"], *item["relevance"]]
            ).casefold()
        ]
    return items


@app.get("/api/sources/{source_id}/content", response_class=PlainTextResponse)
async def source_content(source_id: str):
    path = source_path(source_id)
    if not path:
        raise HTTPException(404, "approved local source is unavailable")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise HTTPException(413, "source exceeds the local preview limit")
    return path.read_text(encoding="utf-8", errors="replace")


@app.post("/api/sources/requests", status_code=202)
async def request_source_addition(body: SourceAdditionRequest):
    event = AuditEvent(
        action="source.addition.request",
        actor="local-user",
        target=body.name,
        outcome="pending_provenance_review",
        details={
            **body.model_dump(),
            "source_approved": False,
            "required_checks": ["provenance", "authority", "version", "effective_date", "scope"],
        },
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    return {
        "status": "pending_provenance_review",
        "source_approved": False,
        "message": "The source request was recorded. It is not authoritative until the required review is completed.",
    }


@app.get("/api/workspace/tree")
async def workspace_tree(path: str = ""):
    try:
        return workspace_browser.list_directory(path)
    except WorkspacePathError as exc:
        raise HTTPException(400, _safe_exc_msg(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, _safe_exc_msg(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "workspace directory is temporarily unavailable") from exc


@app.get("/api/workspace/file")
async def workspace_file(path: str):
    try:
        result = workspace_browser.read_file(path)
    except WorkspacePathError as exc:
        raise HTTPException(400, _safe_exc_msg(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, _safe_exc_msg(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "workspace file is temporarily unavailable") from exc
    event = AuditEvent(
        action="workspace.file.read",
        actor="local-user",
        target=result["path"],
        outcome="allowed",
        details={"read_only": True, "size": result["size"]},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    return result


def _atlas_current_request(prompt: str) -> str:
    current = prompt.rsplit("CURRENT USER REQUEST:", 1)[-1]
    current = current.split("Local attachment context:", 1)[0]
    return current.strip()


def _atlas_change_request(prompt: str) -> bool:
    request = " ".join(_atlas_current_request(prompt).casefold().split())
    if re.match(r"^(?:can|could|should|would) i\b", request) or re.search(r"\b(?:need|want) to know\b", request):
        return False
    change = r"(?:add|build|change|configure|connect|create|delete|develop|fix|implement|install|make|modify|move|remove|replace|set up|update|upgrade|wire)"
    direct = re.match(rf"^(?:please\s+)?(?:(?:can|could|would) you\s+|let'?s\s+|i (?:need|want)(?: you)? to\s+)?{change}\b", request)
    stated_outcome = re.search(rf"\b(?:i (?:need|want)|it (?:needs|should)|there (?:needs|should)|we (?:need|should))\b.*\b{change}\b", request)
    feature_target = re.search(r"\b(?:agent|approval|button|code|dashboard|environment|feature|file|interface|modal|page|permission|platform|plugin|setting|skill|tab|tool|workflow)\b", request)
    requested_state = re.search(r"\b(?:i (?:need|want)|it (?:needs|should|must)|there (?:needs|should|must)|we (?:need|should|must)|atlas (?:needs|should|must))\b", request)
    return bool(direct or stated_outcome or (feature_target and requested_state))


def _atlas_request_title(request: str) -> str:
    clean = re.sub(r"\s+", " ", request).strip(" .")
    words = clean.split()[:12]
    return (" ".join(words) or "Atlas platform request")[:200]


@app.post("/api/atlas/intake", status_code=202)
async def atlas_request_intake(body: AtlasIntakeRequest):
    atlas = next((agent for agent in store.agents.values() if agent.name == "Atlas"), None)
    if not atlas:
        raise HTTPException(503, "Atlas is not configured")
    request = _atlas_current_request(body.prompt)
    if not _atlas_change_request(request):
        task = await create_task(TaskCreate(
            title=body.title or "Atlas request", prompt=body.prompt, agent_id=atlas.id,
        ))
        return {"mode": "task", "task": task.model_dump(mode="json")}

    forge = next((agent for agent in store.agents.values() if agent.name == "Forge"), None)
    if not forge:
        raise HTTPException(503, "Forge is not configured")
    title = body.title or _atlas_request_title(request)
    payload = {
        "request": request, "title": title, "implementation_agent_id": str(forge.id),
        "priority": "high", "operation": "create_governed_plan",
    }
    target = f"atlas-intake:{hashlib.sha256(request.encode()).hexdigest()[:20]}"
    approval = approval_service.request(ProtectedActionRequest(
        action="plan_intake", purpose=f"Begin governed review for: {title}", target=target,
        actor="Atlas", payload=payload, ttl_minutes=15,
    ))
    event = AuditEvent(
        action="atlas.intake", actor="Atlas", target=str(approval.id), outcome="approval_required",
        details={"target": target, "request": request, "implementation_agent": "Forge", "questions_asked": 0},
    )
    store.log(event)
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_audit(event)
    challenge_code = issue_approval_challenge(approval.id)
    message = (
        f"I have enough information to start. I interpreted your request as: {request}. "
        "Approve the request in the popup to begin governed review. No code will be changed by this approval."
    )
    await broadcast({
        "type": "atlas.approval_required", "approval_id": str(approval.id),
        "action": approval.action, "target": approval.target, "purpose": approval.purpose,
    })
    return {
        "mode": "approval", "message": message,
        "approval": ApprovalChallengeResponse(**approval.model_dump(), challenge_code=challenge_code).model_dump(mode="json"),
    }


@app.post("/api/atlas/intake/{approval_id}/approve", response_model=Plan, status_code=201)
async def approve_atlas_request_intake(approval_id: UUID):
    approval = store.external_approvals.get(approval_id)
    if not approval or approval.action != "plan_intake":
        raise HTTPException(404, "Atlas intake approval not found")
    try:
        approval = approval_service.consume(
            approval_id, action="plan_intake", target=approval.target, payload=approval.payload,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    plan = await create_plan(PlanCreate(
        title=str(approval.payload["title"]), request=str(approval.payload["request"]),
        implementation_agent_id=UUID(str(approval.payload["implementation_agent_id"])),
        priority=str(approval.payload.get("priority", "high")),
    ))
    event = AuditEvent(
        action="atlas.intake.approved", actor="local-user", target=str(plan.id), outcome="reviews_queued",
        details={"approval_id": str(approval.id), "questions_asked": 0, "implementation_agent": "Forge"},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    await broadcast({"type": "lifecycle.guide", "plan_id": str(plan.id), "message": "Atlas request approved for governed review"})
    return plan


@app.post("/api/tasks", response_model=Task, status_code=202)
async def create_task(body: TaskCreate):
    if body.agent_id not in store.agents:
        raise HTTPException(404, "agent not found")
    if kill_switch.is_set():
        raise HTTPException(423, "agent execution is stopped; release the kill switch first")
    agent = store.agents[body.agent_id]
    if body.workspace_id:
        plan_workspace = store.plan_workspaces.get(body.workspace_id)
        if not plan_workspace or plan_workspace.status != "ready" or plan_workspace.plan_id != body.plan_id:
            raise HTTPException(409, "task workspace is not a ready workspace for the selected plan")
    review_only = body.prompt.startswith("[LIFECYCLE_REVIEW]") and body.plan_id is not None and body.workspace_id is None
    policy_agent = agent.model_copy(update={"read_only": True, "requires_user_authorization": False, "tools": [tool for tool in agent.tools if tool in NONMUTATING_TOOLS]}) if review_only else agent
    policy = SecurityPolicy.task_policy(policy_agent, body.user_authorized)
    if not policy["allowed"]:
        raise HTTPException(403, policy["reason"])
    if policy["authorization_required"] and (not body.plan_id or not body.workspace_id):
        raise HTTPException(409, "implementation tasks must originate from an approved plan workspace")
    priority = "high" if agent.name == "Forge" and body.priority in {"normal", "low"} else body.priority
    selected_model = body.model or (settings.forge_model if agent.name == "Forge" else settings.default_model)
    task = Task(**body.model_dump(exclude={"model", "user_authorized", "priority"}), model=selected_model, priority=priority, user_authorized=body.user_authorized)
    store.tasks[task.id] = task
    store.log(AuditEvent(action="task.create", actor="local-user", target=str(task.id), outcome="queued", details={"agent": agent.name, "user_authorized": body.user_authorized, "risk_tier": policy["risk_tier"], "priority": task.priority, "workflow": "lifecycle-review" if review_only else "governed-agent-task", "review_only": review_only}))
    await infrastructure.persist_task(task)
    await infrastructure.persist_audit(store.audit[0])
    await task_queue.enqueue(task.id, task.priority, task.user_authorized)
    return task


@app.get("/api/tasks", response_model=list[Task])
async def tasks():
    return sorted(store.tasks.values(), key=lambda t: (PRIORITY_ORDER[t.priority], -t.created_at.timestamp()))


class ChatHistoryStore:
    """Durable per-session chat history persisted as JSONL under data/chat_history."""

    def __init__(self, root: Path, max_messages: int = 200):
        self.root = root
        self.max_messages = max_messages
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)[:64]
        if not safe:
            raise ValueError("invalid chat session id")
        return self.root / f"{safe}.jsonl"

    def append(self, session_id: str, role: str, content: str) -> None:
        entry = {"role": role, "content": content[:20_000], "ts": datetime.now(timezone.utc).isoformat()}
        with self._path(session_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def read(self, session_id: str) -> list[dict]:
        try:
            path = self._path(session_id)
        except ValueError:
            return []
        if not path.exists():
            return []
        messages: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-self.max_messages:]:
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict) and "role" in item and "content" in item:
                messages.append({"role": item["role"], "content": item["content"], "ts": item.get("ts", "")})
        return messages

    def clear(self, session_id: str) -> None:
        try:
            self._path(session_id).unlink(missing_ok=True)
        except ValueError:
            pass


chat_history = ChatHistoryStore(settings.chat_history_dir)


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    history: list[dict] = Field(default_factory=list)
    session_id: str = Field(default="", max_length=64)


def _build_chat_messages(message: str, history: list[dict]) -> list[dict]:
    atlas_context = render_agent_context(exclude_name="Atlas")
    owner_context = f" The platform owner's name is {settings.owner_name}. Address them by name when greeting or responding to simple queries. Use their name naturally, not in every sentence."
    system = f"You are Atlas, a senior platform engineer AI for Atlas Studio. Respond in 1-3 sentences using engineering terminology (refactor, implement, test, deploy, optimize, etc). You are read-only — delegate implementation via [DELEGATE:Forge:task], QA via [DELEGATE:Quanta:task], security via [DELEGATE:Sentinel:task]. Skip pleasantries. Be direct and technical.{owner_context}"
    messages = [{"role": "system", "content": system}]
    for msg in history[-10:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": message})
    return messages


def _finalize_chat_output(output: str) -> tuple[str, dict | None]:
    reasoning, clean_output = _extract_reasoning(output)
    clean_output = _strip_thinking(clean_output) or _strip_thinking(output)
    clean_output = _deduplicate_response(clean_output) or clean_output
    if not clean_output and output.strip():
        clean_output = output.strip()
    delegation = None
    delegation_match = re.search(r"\[DELEGATE:(\w+):(.*?)\]", clean_output, re.DOTALL)
    if delegation_match:
        delegation = {"agent": delegation_match.group(1), "prompt": delegation_match.group(2).strip()}
        clean_output = clean_output[:delegation_match.start()].strip() or clean_output
    return clean_output, delegation


@app.post("/api/chat")
async def chat(body: ChatMessage):
    atlas = next((a for a in store.agents.values() if a.name == "Atlas"), None)
    if not atlas:
        raise HTTPException(503, "Atlas agent is not available")
    task_id = str(uuid4())
    run_id = str(uuid4())
    agent_id = str(atlas.id)
    session_id = body.session_id or uuid4().hex[:12]
    skill_context = skill_runtime.render(atlas.skills)
    agent_context = render_agent_context(exclude_name="Atlas")
    messages = _build_chat_messages(body.message, body.history)
    output = ""
    try:
        async for delta in gateway.get().stream(messages, settings.default_model):
            output += delta
            await broadcast({"type": "task.delta", "task_id": task_id, "run_id": run_id, "agent_id": agent_id, "delta": delta, "text": output, "status": "running"})
        clean_output, delegation = _finalize_chat_output(output)
        assessment = evaluate_grounding("Atlas", clean_output)
        chat_event = AuditEvent(action="chat.message", actor="local-user", target=task_id, outcome="completed", details={"model": settings.default_model, "grounding_status": assessment["status"]})
        store.log(chat_event)
        await broadcast({"type": "task.progress", "task_id": task_id, "status": "completed", "message": clean_output})
        chat_history.append(session_id, "user", body.message)
        chat_history.append(session_id, "assistant", clean_output)
        return {"response": clean_output, "task_id": task_id, "delegation": delegation, "session_id": session_id}
    except ProviderError as exc:
        raise HTTPException(503, f"Local model unavailable: {exc}. Check Ollama and retry.")
    except Exception as exc:
        raise HTTPException(500, f"Chat failed: {exc.__class__.__name__}: {exc}")


@app.post("/api/chat/stream")
async def chat_stream(body: ChatMessage):
    """Server-Sent Events variant of /api/chat that streams deltas as they are generated."""
    atlas = next((a for a in store.agents.values() if a.name == "Atlas"), None)
    if not atlas:
        raise HTTPException(503, "Atlas agent is not available")
    task_id = str(uuid4())
    run_id = str(uuid4())
    agent_id = str(atlas.id)
    session_id = body.session_id or uuid4().hex[:12]
    messages = _build_chat_messages(body.message, body.history)

    async def event_stream():
        yield f"event: start\ndata: {json.dumps({'task_id': task_id, 'session_id': session_id})}\n\n"
        output = ""
        try:
            async for delta in gateway.get().stream(messages, settings.default_model):
                output += delta
                await broadcast({"type": "task.delta", "task_id": task_id, "run_id": run_id, "agent_id": agent_id, "delta": delta, "text": output, "status": "running"})
                yield f"event: delta\ndata: {json.dumps({'text': output})}\n\n"
            clean_output, delegation = _finalize_chat_output(output)
            assessment = evaluate_grounding("Atlas", clean_output)
            chat_event = AuditEvent(action="chat.message", actor="local-user", target=task_id, outcome="completed", details={"model": settings.default_model, "grounding_status": assessment["status"], "transport": "sse"})
            store.log(chat_event)
            await broadcast({"type": "task.progress", "task_id": task_id, "status": "completed", "message": clean_output})
            chat_history.append(session_id, "user", body.message)
            chat_history.append(session_id, "assistant", clean_output)
            yield f"event: done\ndata: {json.dumps({'response': clean_output, 'task_id': task_id, 'delegation': delegation, 'session_id': session_id})}\n\n"
        except ProviderError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': f'Local model unavailable: {exc}. Check Ollama and retry.'})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'detail': f'Chat failed: {exc.__class__.__name__}'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str):
    return {"session_id": session_id, "messages": chat_history.read(session_id)}


@app.delete("/api/chat/history/{session_id}")
async def delete_chat_history(session_id: str):
    chat_history.clear(session_id)
    return {"status": "cleared", "session_id": session_id}


class DelegateRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=60)
    prompt: str = Field(min_length=1, max_length=50_000)


@app.post("/api/chat/delegate", response_model=Task, status_code=202)
async def delegate_from_chat(body: DelegateRequest):
    agent = next((a for a in store.agents.values() if a.name.lower() == body.agent_name.lower()), None)
    if not agent:
        raise HTTPException(404, f"Agent '{body.agent_name}' not found")
    if kill_switch.is_set():
        raise HTTPException(423, "Agent execution is stopped")
    policy = SecurityPolicy.task_policy(agent, True)
    if not policy["allowed"]:
        raise HTTPException(403, policy["reason"])
    selected_model = settings.forge_model if agent.name == "Forge" else settings.default_model
    task = Task(title=f"Chat delegation to {agent.name}", prompt=body.prompt, agent_id=agent.id, model=selected_model, priority="normal", user_authorized=True)
    store.tasks[task.id] = task
    store.log(AuditEvent(action="task.create", actor="local-user", target=str(task.id), outcome="queued", details={"agent": agent.name, "delegated_from": "chat"}))
    await infrastructure.persist_task(task)
    await infrastructure.persist_audit(store.audit[0])
    await task_queue.enqueue(task.id, task.priority, task.user_authorized)
    return task


def _resolve_change_set(identifier: str) -> ChangeSet | None:
    try:
        return store.change_sets.get(UUID(identifier))
    except (ValueError, TypeError):
        pass
    for cs in store.change_sets.values():
        if str(cs.id).startswith(identifier):
            return cs
    return None


class CommitRequest(BaseModel):
    change_set_id: str = Field(min_length=1)
    branch: str = Field(default="main", max_length=100)
    message: str = Field(min_length=1, max_length=500)


@app.post("/api/chat/commit")
async def commit_from_chat(body: CommitRequest):
    change_set = _resolve_change_set(body.change_set_id)
    if not change_set:
        raise HTTPException(404, "Change set not found")
    if change_set.status not in {"tests_passed", "applied"}:
        raise HTTPException(409, f"Change set status '{change_set.status}' is not committable")
    approval = approval_service.request(ProtectedActionRequest(
        action="git_commit",
        purpose=f"Commit change set '{change_set.title}' to {body.branch}",
        target=str(change_set.id),
        actor="local-user",
        payload={"branch": body.branch, "message": body.message},
    ))
    event = AuditEvent(action="approval.request", actor="local-user", target=str(approval.id), outcome="pending", details={"protected_action": "git_commit", "target": str(change_set.id)})
    store.log(event)
    await infrastructure.persist_external_approval(approval)
    await infrastructure.persist_audit(event)
    return {"approval_id": str(approval.id), "challenge_code": issue_approval_challenge(approval.id), "change_set_id": str(change_set.id), "change_set_title": change_set.title}


@app.post("/api/chat/commit/execute")
async def execute_commit(approval_id: UUID, body: CommitRequest):
    change_set = _resolve_change_set(body.change_set_id)
    if not change_set:
        raise HTTPException(404, "Change set not found")
    if change_set.status not in {"tests_passed", "applied"}:
        raise HTTPException(409, f"Change set status '{change_set.status}' is not committable")
    payload = {"change_set_id": str(change_set.id), "workspace_id": str(change_set.workspace_id), "branch": body.branch, "message": body.message}
    try:
        approval = approval_service.consume(approval_id, action="git_commit", target=str(change_set.id), payload=payload)
        await infrastructure.persist_external_approval(approval)
        result = await implementation_worker.execute({
            "action": "git_commit", "workspace_id": str(change_set.workspace_id),
            "branch": body.branch, "message": body.message,
            "files": [{"path": item.path, "content": item.content, "expected_sha256": item.after_sha256} for item in change_set.files],
        })
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    except ImplementationWorkerError as exc:
        raise HTTPException(503, _safe_exc_msg(exc)) from exc
    change_set.status = "committed"
    change_set.branch = result.get("branch", body.branch)
    change_set.commit = result.get("commit", "")
    change_set.updated_at = datetime.now(timezone.utc)
    await infrastructure.persist_change_set(change_set)
    event = AuditEvent(action="forge.change_set.commit", actor="local-user", target=str(change_set.id), outcome="completed", details={"branch": change_set.branch, "commit": change_set.commit})
    store.log(event)
    await infrastructure.persist_audit(event)
    return {"status": "committed", "branch": change_set.branch, "commit": change_set.commit, "change_set_id": str(change_set.id)}


class DevActivityLog(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    status: str = Field(default="completed", max_length=50)
    task_id: str = Field(default="", max_length=100)


@app.post("/api/dev/log")
async def log_dev_activity(body: DevActivityLog):
    """Log a development activity event for the dashboard."""
    event = AuditEvent(
        action="dev.activity",
        actor="local-user",
        target=body.task_id or "cli",
        outcome=body.status,
        details={"message": body.message, "source": "cli"},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    await broadcast({
        "type": "task.progress",
        "task_id": body.task_id or str(uuid4()),
        "status": body.status,
        "message": body.message,
    })
    return {"status": "logged", "message": body.message}


async def start_qa_pipeline(body: QaPipelineRunRequest):
    plan = store.plans.get(body.plan_id)
    workspace = store.plan_workspaces.get(body.workspace_id)
    lifecycle = next((item for item in store.lifecycles.values() if item.plan_id == body.plan_id), None)
    if not plan or plan.status not in {"approved", "in_progress"}:
        raise HTTPException(409, "an approved plan is required for the full QA pipeline")
    if not workspace or workspace.plan_id != body.plan_id or workspace.status != "ready":
        raise HTTPException(409, "the approved plan workspace is not ready")
    if not lifecycle or lifecycle.stage != "test":
        raise HTTPException(409, "move the approved lifecycle to Test before running the full QA pipeline")
    command = ["python", "-m", "pytest", "-q"]
    payload = {
        "plan_id": str(body.plan_id), "workspace_id": str(body.workspace_id),
        "command": command, "timeout_seconds": body.timeout_seconds,
    }
    target = f"qa-pipeline:{body.plan_id}"
    try:
        approval = approval_service.consume(body.approval_id, action="test_execute", target=target, payload=payload)
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    quanta = next((agent for agent in store.agents.values() if agent.name == "Quanta"), None)
    if not quanta:
        raise HTTPException(503, "Quanta is unavailable")
    task = await create_task(TaskCreate(
        title=f"Full QA pipeline — {plan.title}",
        prompt=f"[FULL_QA_PIPELINE]\nRun the complete repository test suite for approved plan {plan.id} inside its isolated Test workspace and record all results.",
        agent_id=quanta.id, priority="high", user_authorized=True,
        plan_id=plan.id, workspace_id=workspace.id,
    ))
    event = AuditEvent(
        action="qa.pipeline.queue", actor="local-user", target=str(task.id), outcome="queued",
        details={"plan_id": str(plan.id), "workspace_id": str(workspace.id), "approval_id": str(approval.id)},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    return task


@app.post("/api/tasks/{task_id}/cancel", response_model=Task)
async def cancel(task_id: UUID):
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    if task.status in ("queued", "running"):
        task.status = "cancelled"
        task.updated_at = datetime.now(timezone.utc)
        await task_queue.remove(task.id)
        job = task_jobs.get(task_id)
        if job and not job.done():
            job.cancel()
        store.log(AuditEvent(action="task.cancel", actor="local-user", target=str(task.id), outcome="cancelled"))
        await infrastructure.persist_task(task)
        await infrastructure.persist_audit(store.audit[0])
    return task


@app.post("/api/control/kill-switch")
async def set_kill_switch(request: Request, enabled: bool = True):
    # Require admin or owner role
    auth_ok = False
    cookie = request.cookies.get("atlas_session", "")
    auth = request.headers.get("authorization", "")
    store_s = get_session_store()
    if auth.startswith("Bearer "):
        if store_s.validate_owner_token(auth[7:]) or auth[7:] == settings.worker_token:
            auth_ok = True
    elif cookie:
        session = store_s.validate(cookie)
        if session and session.get("role") in ("owner", "admin"):
            auth_ok = True
    if not auth_ok:
        raise HTTPException(403, "Kill switch requires admin or owner role")
    if enabled:
        kill_switch.set()
        for task in store.tasks.values():
            if task.status in ("queued", "running"):
                task.status = "cancelled"
                task.updated_at = datetime.now(timezone.utc)
                job = task_jobs.get(task.id)
                if job and not job.done():
                    job.cancel()
                await task_queue.remove(task.id)
                await infrastructure.persist_task(task)
    else:
        kill_switch.clear()
    store.log(AuditEvent(action="platform.kill_switch", actor="local-user", target="all-agents", outcome="engaged" if enabled else "released"))
    await infrastructure.persist_audit(store.audit[0])
    if infrastructure.redis:
        await infrastructure.redis.publish("atlas-studio:control", "kill" if enabled else "release")
    await broadcast({"type": "control.kill_switch", "enabled": enabled})
    return {"enabled": kill_switch.is_set()}


@app.get("/api/audit", response_model=list[AuditEvent])
async def audit(limit: int = 100):
    return list(store.audit)[:min(limit, 500)]


@app.get("/api/metrics")
async def metrics():
    """Return a local operational snapshot for the engineering metrics board."""
    task_items = list(store.tasks.values())
    agent_items = list(store.agents.values())
    audit_items = list(store.audit)
    change_items = [item for item in store.change_sets.values() if item.removed_at is None]
    approval_items = list(store.external_approvals.values())
    task_counts = Counter(task.status for task in task_items)
    grounding_counts = Counter(task.grounding_status for task in task_items)
    durations = [task.duration_ms for task in task_items if task.duration_ms is not None]
    completed = task_counts["completed"]
    failed = task_counts["failed"]
    decided = completed + failed
    infrastructure_health = await infrastructure.health()
    model_ready = await gateway.get().healthy()
    worker_health = await implementation_worker.health()
    durable_queue_depth = await task_queue.depth()
    services = {
        "api": "ok",
        "model_gateway": "ok" if model_ready else "unavailable",
        "implementation_worker": worker_health.get("status", "unavailable"),
        **infrastructure_health,
        "speech_to_text": "configured" if settings.stt_url else "disabled",
        "text_to_speech": "configured" if settings.tts_url else "disabled",
        "avatar_worker": "configured" if settings.avatar_local_enabled else "disabled",
    }

    artifact_count = 0
    artifact_bytes = 0
    try:
        for path in settings.artifact_root.rglob("*"):
            if path.is_file():
                artifact_count += 1
                artifact_bytes += path.stat().st_size
    except OSError:
        pass

    process_memory_mb = None
    try:
        with open("/proc/self/status", encoding="utf-8") as status_file:
            status_text = status_file.read()
        rss_line = next(line for line in status_text.splitlines() if line.startswith("VmRSS:"))
        process_memory_mb = round(int(rss_line.split()[1]) / 1024, 1)
    except (OSError, StopIteration, ValueError):
        pass

    load_average = None
    try:
        load_average = round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        pass

    tool_assignments = Counter(tool for agent in agent_items for tool in agent.tools)
    outcome_counts = Counter(event.outcome for event in audit_items)
    change_counts = Counter(item.status for item in change_items)
    approval_counts = Counter(item.status for item in approval_items)
    atlas = next((agent for agent in agent_items if agent.name == "Atlas"), None)
    ready_services = sum(1 for state in services.values() if state in {"ok", "configured"})

    return {
        "generated_at": datetime.now(timezone.utc),
        "platform": {
            "status": "stopped" if kill_switch.is_set() else ("healthy" if model_ready and all(value == "ok" for value in infrastructure_health.values()) else "degraded"),
            "mode": settings.mode,
            "local_only": settings.mode == "community",
            "uptime_seconds": int(time.monotonic() - process_started_at),
            "kill_switch": kill_switch.is_set(),
            "services_ready": ready_services,
            "services_total": len(services),
        },
        "services": services,
        "tasks": {
            "total": len(task_items),
            "active": task_counts["queued"] + task_counts["running"],
            "queued": task_counts["queued"],
            "running": task_counts["running"],
            "completed": completed,
            "failed": failed,
            "cancelled": task_counts["cancelled"],
            "success_rate": round(completed / decided * 100, 1) if decided else None,
            "average_duration_ms": round(sum(durations) / len(durations)) if durations else None,
            "durable_queue_depth": durable_queue_depth,
            "grounding": {
                "grounded": grounding_counts["grounded"],
                "verification_required": grounding_counts["verification_required"],
                "blocked": grounding_counts["blocked"],
                "pending": grounding_counts["pending"],
                "not_applicable": grounding_counts["not_applicable"],
            },
            "recent": [
                {
                    "id": str(task.id), "title": task.title, "agent": store.agents.get(task.agent_id).name if store.agents.get(task.agent_id) else "Agent",
                    "status": task.status, "grounding_status": task.grounding_status,
                    "evidence_refs": task.evidence_refs, "duration_ms": task.duration_ms, "created_at": task.created_at,
                }
                for task in sorted(task_items, key=lambda item: item.created_at, reverse=True)[:10]
            ],
        },
        "agents": {
            "total": len(agent_items),
            "system": sum(agent.system for agent in agent_items),
            "custom": sum(not agent.system for agent in agent_items),
            "read_only": sum(agent.read_only for agent in agent_items),
            "implementation_capable": sum(not agent.read_only for agent in agent_items),
            "authorization_required": sum(agent.requires_user_authorization for agent in agent_items),
        },
        "model": {
            "provider": settings.default_provider,
            "name": settings.default_model,
            "ready": model_ready,
            "timeout_seconds": settings.model_timeout_seconds,
            "max_tokens": settings.model_max_tokens,
        },
        "security": {
            "atlas_read_only": bool(atlas and atlas.read_only),
            "sandbox_runtime": settings.sandbox_runtime,
            "sandbox_network": settings.sandbox_network,
            "sandbox_memory": settings.sandbox_memory,
            "sandbox_cpus": settings.sandbox_cpus,
            "sandbox_pids": settings.sandbox_pids,
            "telemetry_enabled": settings.telemetry_enabled,
            "authorization_gates": sum(agent.requires_user_authorization for agent in agent_items),
            "audit_events": len(audit_items),
            "allowed_events": outcome_counts["allowed"] + outcome_counts["completed"] + outcome_counts["created"] + outcome_counts["stored"],
            "failed_events": outcome_counts["failed"],
        },
        "storage": {
            "backend": settings.artifact_backend,
            "artifact_count": artifact_count,
            "artifact_bytes": artifact_bytes,
            "upload_limit_mb": settings.upload_max_mb,
            "postgres": infrastructure_health.get("postgres", "unavailable"),
            "redis": infrastructure_health.get("redis", "unavailable"),
        },
        "runtime": {
            "process_memory_mb": process_memory_mb,
            "load_average_1m": load_average,
            "cpu_count": os.cpu_count(),
        },
        "tools": {
            "unique": len(tool_assignments),
            "assignments": sum(tool_assignments.values()),
            "most_assigned": [{"name": name, "agents": count} for name, count in tool_assignments.most_common(8)],
        },
        "changes": {
            "total": len(change_items),
            "pending_review": change_counts["pending_review"],
            "applied": change_counts["applied"],
            "tests_passed": change_counts["tests_passed"],
            "committed": change_counts["committed"],
            "failed": change_counts["failed"],
            "files_proposed": sum(len(item.files) for item in change_items),
            "approvals_pending": approval_counts["pending"],
            "approvals_used": approval_counts["used"],
            "recent": [
                {"id": str(item.id), "title": item.title, "status": item.status, "files": len(item.files), "updated_at": item.updated_at, "branch": item.branch, "commit": item.commit}
                for item in sorted(change_items, key=lambda value: value.updated_at, reverse=True)[:10]
            ],
        },
        "audit": [event.model_dump(mode="json") for event in audit_items[:10]],
    }


@app.post("/api/artifacts")
async def upload(file: UploadFile = File(...)):
    content = await file.read(settings.upload_max_mb * 1024 * 1024 + 1)
    # Prepend UUID to prevent filename collisions
    safe_name = file.filename or "upload"
    from pathlib import Path
    stem = Path(safe_name).stem[:64]
    suffix = Path(safe_name).suffix or ".bin"
    unique_name = f"{secrets.token_hex(6)}_{stem}{suffix}"
    try:
        destination = artifacts.validate(unique_name, len(content))
    except ValueError as exc:
        raise HTTPException(422, _safe_exc_msg(exc)) from exc
    destination.write_bytes(content)
    store.log(AuditEvent(action="artifact.upload", actor="local-user", target=destination.name, outcome="stored", details={"bytes": len(content)}))
    await infrastructure.persist_audit(store.audit[0])
    return {
        "name": destination.name,
        "size": len(content),
        "storage": settings.artifact_backend,
        "context": extract_artifact_context(destination),
    }


@app.post("/api/speech/transcribe")
async def transcribe_local_speech(audio: UploadFile = File(...)):
    """Proxy browser microphone audio to the optional local Whisper service."""
    allowed = {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4"}
    media_type = (audio.content_type or "").split(";", 1)[0].lower()
    if media_type not in allowed:
        raise HTTPException(422, "Microphone audio must be WebM, OGG, WAV, MP3, or MP4.")
    content = await audio.read(15 * 1024 * 1024 + 1)
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(422, "Microphone turn exceeds the 15 MB local limit.")
    if not settings.stt_url:
        raise HTTPException(503, "Local speech recognition is not configured.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0)) as client:
            result = await client.post(
                settings.stt_url,
                files={"audio": (audio.filename or "atlas-turn.webm", content, media_type)},
            )
            result.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Local speech recognition is unavailable.") from exc
    payload = result.json()
    event = AuditEvent(
        action="speech.transcribe",
        actor="local-user",
        target="Atlas",
        outcome="completed",
        details={"bytes": len(content), "local_only": True},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    return {"text": str(payload.get("text") or "").strip(), "language": payload.get("language")}


@app.post("/api/speech/synthesize")
async def synthesize_local_speech(body: SpeechSynthesisRequest):
    """Return Atlas speech as playable audio via ChatterboxTTS (local CPU) or external TTS worker."""
    spoken_text = prepare_speech_text(body.text)
    if not spoken_text:
        raise HTTPException(422, "The response contains no natural-language content to speak.")

    # Try ChatterboxTTS first (local CPU), cloned to the configured female reference voice
    try:
        voice_prompt = resolve_tts_audio_prompt(settings.tts_audio_prompt)
        audio_bytes = await asyncio.to_thread(chatterbox_synthesize, spoken_text, 0.5, 0.5, voice_prompt)
        event = AuditEvent(
            action="speech.synthesize", actor="Atlas", target="local-speaker",
            outcome="completed", details={"source_characters": len(body.text), "spoken_characters": len(spoken_text), "backend": "chatterbox", "voice_prompt": str(voice_prompt or "default")},
        )
        store.log(event)
        await infrastructure.persist_audit(event)
        return Response(content=audio_bytes, media_type="audio/wav", headers={"X-Atlas-Voice-Backend": "chatterbox"})
    except Exception as exc:
        logger.warning("ChatterboxTTS failed, falling back to external TTS: %s", exc)

    # Fallback to external TTS worker
    if not settings.tts_url:
        raise HTTPException(503, "Local speech synthesis is unavailable.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0)) as client:
            result = await client.post(settings.tts_url, json={"text": spoken_text})
            result.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(503, _safe_exc_msg(exc)) from exc
    event = AuditEvent(
        action="speech.synthesize", actor="Atlas", target="local-speaker",
        outcome="completed", details={"source_characters": len(body.text), "spoken_characters": len(spoken_text), "backend": "external"},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    headers = {}
    if backend := result.headers.get("x-atlas-voice-backend"):
        headers["X-Atlas-Voice-Backend"] = backend
    return Response(content=result.content, media_type=result.headers.get("content-type", "audio/wav"), headers=headers)


@app.post("/api/avatar-generations", response_model=AvatarGeneration, status_code=202)
async def create_avatar_generation(agent_id: UUID = Form(...), consent: bool = Form(...), image: UploadFile = File(...), left: UploadFile | None = File(None), right: UploadFile | None = File(None), rear: UploadFile | None = File(None)):
    if not settings.avatar_local_enabled:
        raise HTTPException(503, "Local avatar generation is disabled. Start the open-source avatar worker and enable it first.")
    if not consent:
        raise HTTPException(422, "Confirm that you have permission to process this image.")
    agent = store.agents.get(agent_id)
    if not agent or "avatar_generate" not in agent.tools:
        raise HTTPException(403, "This agent is not permitted to generate avatars.")
    if image.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(422, "Avatar input must be PNG or JPEG.")
    uploads = {"image": image, "left": left, "right": right, "rear": rear}
    provider_files = {}
    for field, upload in uploads.items():
        if upload is None:
            continue
        if upload.content_type not in ("image/png", "image/jpeg"):
            raise HTTPException(422, f"{field.title()} input must be PNG or JPEG.")
        content = await upload.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(422, f"{field.title()} input exceeds 10 MB.")
        provider_files[field] = (upload.filename or f"{field}.png", content, upload.content_type)
    provider = LocalTripoSRProvider(settings.avatar_service_url)
    try:
        provider_task_id = await provider.create(provider_files)
    except (AvatarServiceError, httpx.HTTPError) as exc:
        raise HTTPException(502, _safe_exc_msg(exc)) from exc
    job = AvatarGeneration(provider_task_id=provider_task_id, agent_id=agent_id, provider="triposr+blender-local")
    avatar_jobs[job.id] = job
    asyncio.create_task(monitor_avatar(job, provider))
    return job


@app.get("/api/avatar-generations", response_model=list[AvatarGeneration])
async def list_avatar_generations():
    return sorted(avatar_jobs.values(), key=lambda item: item.created_at, reverse=True)


@app.delete("/api/avatar-generations/{job_id}", status_code=204)
async def delete_avatar_generation(job_id: UUID, approval_id: UUID | None = None):
    job = avatar_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "avatar generation not found")
    if not job.artifact_url:
        raise HTTPException(409, "this avatar generation has no removable artifact")
    expected_url = f"/artifacts/avatar-{job.id}.glb"
    if job.artifact_url != expected_url:
        raise HTTPException(409, "only locally generated avatar artifacts can be removed")
    payload = {"artifact_url": job.artifact_url}
    try:
        approval = approval_service.consume(
            approval_id, action="avatar_delete", target=str(job.id), payload=payload,
        )
    except ApprovalError as exc:
        raise HTTPException(403, _safe_exc_msg(exc)) from exc
    await infrastructure.persist_external_approval(approval)
    artifact_root = settings.artifact_root.resolve()
    artifact_path = (artifact_root / f"avatar-{job.id}.glb").resolve()
    if artifact_path.parent != artifact_root:
        raise HTTPException(409, "avatar artifact path is outside local storage")
    artifact_path.unlink(missing_ok=True)
    job.artifact_url = None
    job.status = "removed"
    job.message = "Generated avatar removed by the platform owner"
    event = AuditEvent(
        action="avatar.delete", actor="local-user", target=str(job.id), outcome="deleted",
        details={"local_only": True, "artifact": expected_url},
    )
    store.log(event)
    await infrastructure.persist_audit(event)
    await broadcast({"type": "avatar.removed", "job_id": str(job.id)})
    return Response(status_code=204)


@app.get("/api/compliance/posture")
async def get_compliance_posture():
    from .compliance.oscal import OSCALGenerator
    controls = OSCALGenerator.list_all_controls()
    audit_events = await infrastructure.load_audit(limit=1000)
    event_dicts = [
        {
            "action": e.action,
            "actor": e.actor,
            "target": e.target,
            "outcome": e.outcome,
        }
        for e in audit_events
    ]
    posture = {}
    for ctrl_id, ctrl_info in controls.items():
        evidence_count = sum(
            1
            for event in event_dicts
            if any(
                et in event.get("action", "")
                for et in ctrl_info.get("evidence_types", [])
            )
        )
        posture[ctrl_id] = {
            "name": ctrl_info["name"],
            "status": "implemented" if evidence_count > 0 else "planned",
            "evidence_count": evidence_count,
        }
    return {
        "frameworks": {
            "SOC-2": {
                "status": "compliant",
                "controls": {k: v for k, v in posture.items() if k.startswith("CC")},
            },
            "ISO-27001": {
                "status": "compliant",
                "controls": {k: v for k, v in posture.items() if k.startswith("A.")},
            },
            "NIST-CSF": {
                "status": "compliant",
                "controls": {
                    k: v
                    for k, v in posture.items()
                    if any(k.startswith(p) for p in ["PR.", "DE.", "RS.", "RC."])
                },
            },
        },
        "total_events": len(audit_events),
    }


@app.get("/api/compliance/evidence")
async def get_compliance_evidence(framework: str = "SOC-2"):
    from .compliance.evidence import EvidenceCollector
    collector = EvidenceCollector()
    audit_events = await infrastructure.load_audit(limit=500)
    for event in audit_events:
        collector.collect_audit_event(
            {
                "action": event.action,
                "actor": event.actor,
                "target": event.target,
                "outcome": event.outcome,
            }
        )
    return collector.package_evidence(framework, [])


@app.get("/api/compliance/ssp")
async def generate_ssp():
    from .compliance.oscal import OSCALGenerator
    audit_events = await infrastructure.load_audit(limit=1000)
    event_dicts = [
        {
            "action": e.action,
            "actor": e.actor,
            "target": e.target,
            "outcome": e.outcome,
        }
        for e in audit_events
    ]
    return OSCALGenerator.generate_ssp("Atlas Studio", event_dicts)


@app.get("/api/compliance/classification/{action}")
async def get_classification(action: str):
    from .compliance.classification import DataClassifier
    classifier = DataClassifier()
    return {
        "action": action,
        "classification": classifier.get_classification_label(action),
        "requires_encryption": classifier.requires_encryption(action),
        "retention_days": classifier.audit_retention_days(action),
    }


@app.get("/api/compliance/controls")
async def list_compliance_controls():
    from .compliance.oscal import OSCALGenerator
    return OSCALGenerator.list_all_controls()


@app.websocket("/api/ws")
async def websocket(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    await websocket.send_json({"type": "connected", "mode": settings.mode})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.discard(websocket)


STATIC = __import__("pathlib").Path(__file__).parent / "static"
if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/artifacts", StaticFiles(directory=settings.artifact_root), name="artifacts")

DOCS_DIR = STATIC.parent.parent / "docs"
if DOCS_DIR.is_dir():
    app.mount("/docs", StaticFiles(directory=DOCS_DIR), name="docs")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC / "index.html")
