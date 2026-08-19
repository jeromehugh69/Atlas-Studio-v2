from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..providers import ModelProvider
from .execution import ImplementationWorker, ImplementationWorkerError
from .forge import WorkspacePathArgs, WorkspaceSearchArgs


READ_ONLY_WORKSPACE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_workspace",
            "description": "List files and directories in the local project workspace without changing anything.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one UTF-8 project file without changing it.",
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string", "description": "Project-relative file path"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_workspace",
            "description": "Search project text files for a literal string without changing anything.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string", "description": "Literal text to find"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_site",
            "description": "Open an allow-listed local Atlas Studio page in a headless browser and return its rendered text and DOM evidence without clicking, typing, or changing the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Allow-listed local Atlas Studio URL; defaults to the main dashboard"}
                },
            },
        },
    },
]


class ReadOnlySpecialistToolLoop:
    """Bounded evidence-gathering loop for delegated read-only investigations."""

    def __init__(self, provider: ModelProvider, worker: ImplementationWorker, max_rounds: int = 8):
        self.provider = provider
        self.worker = worker
        self.max_rounds = max_rounds

    async def run(self, *, specialist_name: str, role: str, prompt: str, model: str, skill_context: str = "", agent_context: str = "") -> tuple[str, list[str]]:
        system = (
            f"You are {specialist_name}, Atlas Studio's {role}. Atlas has delegated a read-only investigation to you. "
            "The local Atlas Studio project is the default workspace and environment. Use the supplied tools to inspect "
            "real files before reaching a conclusion. These tools can only list, search, and read; they cannot modify files, "
            "run code, use external networks, or change permissions. The inspect_site tool may only render allow-listed local "
            "Atlas Studio pages; it cannot click, type, submit forms, or access the internet. A clear user request to inspect or test a named feature is "
            "already authorization to begin this read-only investigation, so do not ask for confirmation again. Ask one "
            "direct question only when the feature or expected behavior is genuinely missing. Distinguish source-based findings "
            "from runtime behavior that was not exercised. Return a concise report with: finding, evidence, likely cause, "
            "read-only limitations, and recommended next step. Never claim a test ran unless machine evidence shows it."
            f"{skill_context}{agent_context}"
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        last_content = ""
        evidence: list[str] = []
        for _ in range(self.max_rounds):
            message = await self.provider.chat_with_tools(messages, model, READ_ONLY_WORKSPACE_TOOLS, temperature=0.1)
            messages.append(message)
            last_content = str(message.get("content", "")).strip() or last_content
            calls = message.get("tool_calls") or []
            if not calls:
                if evidence:
                    return last_content or f"{specialist_name} completed the read-only investigation.", evidence
                return (
                    f"{specialist_name} did not collect workspace evidence, so Atlas will not present an unsupported conclusion. "
                    "Retry the read-only investigation or inspect the feature from the Workspace view.",
                    [],
                )
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
                        result = await self.worker.execute({"action": name})
                        evidence.append("workspace:list")
                    elif name == "read_file":
                        args = WorkspacePathArgs.model_validate(arguments)
                        result = await self.worker.execute({"action": name, "path": args.path})
                        evidence.append(f"workspace:{args.path}")
                    elif name == "search_workspace":
                        args = WorkspaceSearchArgs.model_validate(arguments)
                        result = await self.worker.execute({"action": name, "query": args.query})
                        for match in result.get("matches", [])[:20]:
                            path = str(match.get("path", "")).strip()
                            line = match.get("line")
                            if path:
                                evidence.append(f"workspace:{path}:{line}" if line else f"workspace:{path}")
                    elif name == "inspect_site":
                        url = str(arguments.get("url") or "http://app:8080/")
                        result = await self.worker.execute({"action": name, "url": url})
                        evidence.append(f"site:{result.get('url', url)}")
                    else:
                        result = {"error": f"Tool '{name}' is not available in read-only specialist mode"}
                except (ValidationError, ImplementationWorkerError, KeyError, TypeError, ValueError) as exc:
                    result = {"error": f"Read-only {name or 'tool'} request failed: {exc}"}
                messages.append({
                    "role": "tool",
                    "tool_name": name or "invalid_tool",
                    "content": json.dumps(result, ensure_ascii=True, default=str)[:750_000],
                })
        return (
            f"{specialist_name} reached the read-only investigation limit before producing a supported conclusion.",
            list(dict.fromkeys(evidence)),
        )
