from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from ..models import ChangeSet, ChangeSetFile
from ..providers import ModelProvider
from .execution import ImplementationWorker


class WorkspacePathArgs(BaseModel):
    path: str = Field(min_length=1, max_length=1_000)


class WorkspaceSearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class ProposedFile(BaseModel):
    path: str = Field(min_length=1, max_length=1_000)
    content: str = Field(max_length=2_000_000)


class ProposedChangeSet(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    summary: str = Field(min_length=2, max_length=2_000)
    files: list[ProposedFile] = Field(min_length=1, max_length=40)


FORGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_workspace",
            "description": "List files and directories in the approved isolated plan workspace.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one UTF-8 text file from the approved isolated plan workspace.",
            "parameters": {
                "type": "object", "required": ["path"],
                "properties": {"path": {"type": "string", "description": "Workspace-relative file path"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_workspace",
            "description": "Search approved workspace text files for a literal string.",
            "parameters": {
                "type": "object", "required": ["query"],
                "properties": {"query": {"type": "string", "description": "Literal text to find"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_change_set",
            "description": "Finish by proposing a complete reviewable multi-file change set. This previews changes only and never writes files.",
            "parameters": {
                "type": "object", "required": ["title", "summary", "files"],
                "properties": {
                    "title": {"type": "string"}, "summary": {"type": "string"},
                    "files": {
                        "type": "array", "minItems": 1, "maxItems": 40,
                        "items": {
                            "type": "object", "required": ["path", "content"],
                            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        },
                    },
                },
            },
        },
    },
]


class ForgeToolLoop:
    """A bounded, read-only model tool loop that ends in a reviewable change set.

    Applying files, running tests, and committing remain API-controlled user
    actions. The model never receives a generic shell, Git, approval, network,
    deployment, or permission-management tool.
    """

    def __init__(self, provider: ModelProvider, worker: ImplementationWorker, max_rounds: int = 8):
        self.provider = provider
        self.worker = worker
        self.max_rounds = max_rounds

    async def run(
        self, *, prompt: str, model: str, task_id: UUID, plan_id: UUID, workspace_id: UUID, skill_context: str = "", agent_context: str = "",
    ) -> tuple[str, ChangeSet | None]:
        system = (
            "You are Forge, Atlas Studio's implementation agent. Work only inside the approved isolated workspace. "
            "Inspect the repository with the supplied read-only tools. Never invent file contents or claim a change was applied. "
            "When information required to make a safe change is missing, respond with one direct question and do not call propose_change_set. "
            "When ready, call propose_change_set exactly once with the complete content of every file that must change. "
            "Keep changes minimal and preserve unrelated behavior. You have no shell, network, Git, deployment, or permission tools."
            f"{skill_context}{agent_context}"
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        last_content = ""
        for _ in range(self.max_rounds):
            message = await self.provider.chat_with_tools(messages, model, FORGE_TOOLS, temperature=0.1)
            messages.append(message)
            last_content = str(message.get("content", "")).strip() or last_content
            calls = message.get("tool_calls") or []
            if not calls:
                return last_content or "Forge needs more information before it can propose a safe change.", None
            for raw_call in calls:
                function = raw_call.get("function", {}) if isinstance(raw_call, dict) else {}
                name = str(function.get("name", ""))
                arguments = function.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                try:
                    if name == "list_workspace":
                        result = await self.worker.execute({"action": name, "workspace_id": str(workspace_id)})
                    elif name == "read_file":
                        args = WorkspacePathArgs.model_validate(arguments)
                        result = await self.worker.execute({"action": name, "path": args.path, "workspace_id": str(workspace_id)})
                    elif name == "search_workspace":
                        args = WorkspaceSearchArgs.model_validate(arguments)
                        result = await self.worker.execute({"action": name, "query": args.query, "workspace_id": str(workspace_id)})
                    elif name == "propose_change_set":
                        proposal = ProposedChangeSet.model_validate(arguments)
                        preview = await self.worker.execute({
                            "action": "preview_change_set", "workspace_id": str(workspace_id),
                            "files": [item.model_dump() for item in proposal.files],
                        })
                        files = [ChangeSetFile(**item) for item in preview["files"] if item.get("changed")]
                        if not files:
                            return "Forge inspected the workspace and found that the requested change is already present.", None
                        change_set = ChangeSet(
                            task_id=task_id, plan_id=plan_id, workspace_id=workspace_id,
                            title=proposal.title, summary=proposal.summary, files=files,
                            combined_diff=preview.get("combined_diff", ""),
                        )
                        return f"Forge prepared change set {change_set.id} with {len(files)} file(s). Review the combined diff before applying it.", change_set
                    else:
                        result = {"error": f"Tool '{name}' is not available to Forge"}
                except (ValidationError, KeyError, TypeError, ValueError) as exc:
                    result = {"error": f"Invalid {name or 'tool'} request: {exc}"}
                messages.append({
                    "role": "tool", "tool_name": name or "invalid_tool",
                    "content": json.dumps(result, ensure_ascii=True, default=str)[:750_000],
                })
        return "Forge stopped after reaching the safe tool-iteration limit. Refine the request or reduce its scope.", None
