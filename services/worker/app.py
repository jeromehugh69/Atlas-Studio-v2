from __future__ import annotations

import asyncio
from difflib import unified_diff
from html import unescape
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from atlas_studio.site_policy import validate_site_url


WORKSPACE = Path(os.getenv("ATLAS_WORKER_WORKSPACE", "/workspace")).resolve()
WORKSPACES = Path(os.getenv("ATLAS_WORKER_PLAN_WORKSPACES", "/workspaces")).resolve()
TOKEN = os.getenv("ATLAS_WORKER_TOKEN", "atlas-local-worker")
ALLOWED_FILE_SUFFIXES = {
    ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".md", ".txt", ".ps1", ".sh",
}
ALLOWED_EXECUTABLES = {"python", "python3", "pytest"}
MAX_CHANGE_SET_BYTES = 8_000_000
ALLOWED_SITE_ORIGINS = {
    origin.rstrip("/") for origin in os.getenv("ATLAS_WORKER_SITE_ORIGINS", "http://app:8080").split(";") if origin.strip()
}


class WorkerFileChange(BaseModel):
    path: str = Field(min_length=1, max_length=1_000)
    content: str = Field(max_length=2_000_000)
    expected_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class WorkerAction(BaseModel):
    action: Literal[
        "workspace_create", "list_workspace", "read_file", "search_workspace",
        "preview_write", "file_write", "preview_change_set", "apply_change_set",
        "code_execute", "test_execute", "git_status", "git_commit", "inspect_site",
    ]
    path: str = ""
    content: str | None = Field(default=None, max_length=2_000_000)
    expected_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    command: list[str] = Field(default_factory=list, max_length=32)
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    workspace_id: str | None = None
    files: list[WorkerFileChange] = Field(default_factory=list, max_length=40)
    query: str = Field(default="", max_length=500)
    branch: str = Field(default="", max_length=110)
    message: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=1_000)


def authorize(value: str | None) -> None:
    if not value or value != f"Bearer {TOKEN}":
        raise HTTPException(401, "worker authorization failed")


def workspace_base(workspace_id: str | None) -> Path:
    if not workspace_id:
        return WORKSPACE
    if not re.fullmatch(r"[a-f0-9-]{36}", workspace_id):
        raise HTTPException(422, "invalid plan workspace identifier")
    base = (WORKSPACES / workspace_id).resolve()
    try:
        base.relative_to(WORKSPACES)
    except ValueError as exc:
        raise HTTPException(403, "workspace identifier escapes the workspace store") from exc
    return base


def resolve_workspace_path(value: str, *, directory: bool = False, workspace_id: str | None = None) -> Path:
    if not value or "\x00" in value:
        raise HTTPException(422, "a workspace-relative path is required")
    base = workspace_base(workspace_id)
    candidate = (base / value).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise HTTPException(403, "path escapes the approved workspace") from exc
    if not directory and candidate.suffix.lower() not in ALLOWED_FILE_SUFFIXES:
        raise HTTPException(422, "file type is not writable by the implementation worker")
    return candidate


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def allowed_site_url(value: str) -> str:
    try:
        return validate_site_url(value, ALLOWED_SITE_ORIGINS)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc


async def run_process(command: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            "PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
        },
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise HTTPException(408, "worker command timed out") from exc
    return process.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


async def ensure_git_repository(destination: Path) -> None:
    if (destination / ".git").is_dir():
        return
    code, _, stderr = await run_process(["git", "init", "-b", "main"], destination)
    if code != 0:
        code, _, stderr = await run_process(["git", "init"], destination)
    if code != 0:
        raise HTTPException(503, f"unable to initialize the isolated Git workspace: {stderr[-500:]}")
    await run_process(["git", "config", "user.name", "Atlas Forge"], destination)
    await run_process(["git", "config", "user.email", "forge@atlas.local"], destination)
    await run_process(["git", "add", "--all"], destination)
    code, _, stderr = await run_process(["git", "commit", "-m", "Atlas plan workspace baseline"], destination)
    if code != 0:
        raise HTTPException(503, f"unable to create the isolated workspace baseline: {stderr[-500:]}")


def preview_files(files: list[WorkerFileChange], workspace_id: str | None) -> dict:
    if not files:
        raise HTTPException(422, "at least one file is required")
    if sum(len(item.content.encode("utf-8")) for item in files) > MAX_CHANGE_SET_BYTES:
        raise HTTPException(413, "change set exceeds the worker size limit")
    seen: set[str] = set()
    previews = []
    for item in files:
        target = resolve_workspace_path(item.path, workspace_id=workspace_id)
        key = str(target)
        if key in seen:
            raise HTTPException(422, f"duplicate change-set path: {item.path}")
        seen.add(key)
        before = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        before_hash = digest(before.encode("utf-8"))
        if item.expected_sha256 and not hmac.compare_digest(before_hash, item.expected_sha256):
            raise HTTPException(409, f"file changed after review: {item.path}")
        after_hash = digest(item.content.encode("utf-8"))
        diff = "".join(unified_diff(
            before.splitlines(keepends=True), item.content.splitlines(keepends=True),
            fromfile=f"a/{item.path}", tofile=f"b/{item.path}",
        ))
        previews.append({
            "path": item.path, "content": item.content, "changed": before != item.content,
            "before_sha256": before_hash, "expected_sha256": before_hash,
            "after_sha256": after_hash, "diff": diff[:250_000],
        })
    return {"files": previews, "combined_diff": "\n".join(item["diff"] for item in previews)[:1_000_000]}


app = FastAPI(title="Atlas implementation worker", docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    workspace_store_ready = WORKSPACES.is_dir() and os.access(WORKSPACES, os.W_OK)
    return {
        "status": "ok" if WORKSPACE.is_dir() and workspace_store_ready else "degraded",
        "workspace": str(WORKSPACE),
        "writable": os.access(WORKSPACE, os.W_OK),
        "plan_workspaces": str(WORKSPACES),
        "plan_workspaces_writable": workspace_store_ready,
        "external_network": "denied by internal Compose network",
        "site_inspection": "ready" if shutil.which("chromium") else "unavailable",
        "site_origins": sorted(ALLOWED_SITE_ORIGINS),
    }


@app.post("/actions")
async def execute_action(body: WorkerAction, authorization: str | None = Header(default=None)):
    authorize(authorization)
    started = time.perf_counter()
    if body.action == "workspace_create":
        if not body.workspace_id:
            raise HTTPException(422, "workspace_create requires a plan workspace identifier")
        destination = workspace_base(body.workspace_id)
        if destination.exists():
            await ensure_git_repository(destination)
            return {"action": body.action, "workspace_id": body.workspace_id, "root": str(destination), "status": "ready", "duration_ms": 0}
        WORKSPACES.mkdir(parents=True, exist_ok=True)
        ignored = shutil.ignore_patterns(
            ".git", ".env", ".venv", "__pycache__", "node_modules", ".pytest_cache",
            "data", "outputs", "*.pyc", "*.pyo",
        )
        await asyncio.to_thread(shutil.copytree, WORKSPACE, destination, ignore=ignored)
        await ensure_git_repository(destination)
        return {"action": body.action, "workspace_id": body.workspace_id, "root": str(destination), "status": "ready", "duration_ms": int((time.perf_counter() - started) * 1000)}
    if body.action == "list_workspace":
        base = workspace_base(body.workspace_id)
        entries = []
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base)
            if any(part.startswith(".") or part in {"node_modules", "__pycache__"} for part in relative.parts):
                continue
            entries.append({"path": relative.as_posix(), "type": "directory" if path.is_dir() else "file"})
            if len(entries) >= 2_000:
                break
        return {"action": body.action, "entries": entries, "truncated": len(entries) >= 2_000}
    if body.action == "read_file":
        target = resolve_workspace_path(body.path, workspace_id=body.workspace_id)
        if not target.is_file():
            raise HTTPException(404, "workspace file not found")
        data = target.read_bytes()
        if len(data) > 512_000:
            raise HTTPException(413, "file exceeds the Forge read limit")
        return {"action": body.action, "path": body.path, "content": data.decode("utf-8", errors="replace"), "sha256": digest(data)}
    if body.action == "search_workspace":
        if len(body.query.strip()) < 2:
            raise HTTPException(422, "a search query is required")
        base = workspace_base(body.workspace_id)
        query = body.query.casefold()
        matches = []
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_FILE_SUFFIXES or any(part.startswith(".") for part in path.relative_to(base).parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                if query in line.casefold():
                    matches.append({"path": path.relative_to(base).as_posix(), "line": number, "text": line[:500]})
                    if len(matches) >= 200:
                        return {"action": body.action, "matches": matches, "truncated": True}
        return {"action": body.action, "matches": matches, "truncated": False}
    if body.action == "inspect_site":
        url = allowed_site_url(body.url)
        profile = tempfile.mkdtemp(prefix="atlas-browser-", dir="/tmp")
        try:
            code, dom, stderr = await run_process([
                "chromium", "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--disable-background-networking", "--disable-sync", "--metrics-recording-only",
                f"--user-data-dir={profile}", "--virtual-time-budget=4000", "--dump-dom", url,
            ], WORKSPACE, min(body.timeout_seconds, 30))
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        if code != 0:
            raise HTTPException(502, f"local page inspection failed: {stderr[-500:]}")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", dom, flags=re.IGNORECASE | re.DOTALL)
        visible = re.sub(r"<(script|style|svg)\b[^>]*>.*?</\1>", " ", dom, flags=re.IGNORECASE | re.DOTALL)
        visible = unescape(re.sub(r"<[^>]+>", " ", visible))
        visible = re.sub(r"\s+", " ", visible).strip()
        return {
            "action": body.action, "url": url,
            "title": unescape(title_match.group(1)).strip() if title_match else "",
            "text": visible[:100_000], "dom": dom[:500_000],
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "network": "local allow-list only",
        }
    if body.action in {"preview_write", "file_write"}:
        target = resolve_workspace_path(body.path, workspace_id=body.workspace_id)
        before = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        before_bytes = before.encode("utf-8")
        if body.expected_sha256 and digest(before_bytes) != body.expected_sha256:
            raise HTTPException(409, "file changed after approval; request a new preview")
        after = body.content or ""
        diff = "".join(unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{body.path}",
            tofile=f"b/{body.path}",
        ))
        result = {
            "action": body.action,
            "path": body.path,
            "changed": before != after,
            "before_sha256": digest(before_bytes),
            "after_sha256": digest(after.encode("utf-8")),
            "diff": diff[:250_000],
        }
        if body.action == "file_write" and before != after:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=".atlas-write-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                    handle.write(after)
                os.replace(temporary_name, target)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        result["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    if body.action in {"preview_change_set", "apply_change_set"}:
        preview = preview_files(body.files, body.workspace_id)
        if body.action == "apply_change_set":
            backups: list[tuple[Path, bytes | None]] = []
            temporary: list[tuple[Path, str]] = []
            try:
                for item in body.files:
                    target = resolve_workspace_path(item.path, workspace_id=body.workspace_id)
                    backups.append((target, target.read_bytes() if target.exists() else None))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    descriptor, name = tempfile.mkstemp(prefix=".atlas-change-", dir=target.parent)
                    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                        handle.write(item.content)
                    temporary.append((target, name))
                for target, name in temporary:
                    os.replace(name, target)
            except Exception:
                for target, original in backups:
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(original)
                raise
            finally:
                for _, name in temporary:
                    if os.path.exists(name):
                        os.unlink(name)
        return {"action": body.action, **preview, "duration_ms": int((time.perf_counter() - started) * 1000)}

    if body.action == "git_status":
        base = workspace_base(body.workspace_id)
        code, stdout, stderr = await run_process(["git", "status", "--porcelain=v1", "--branch"], base)
        return {"action": body.action, "exit_code": code, "stdout": stdout[-200_000:], "stderr": stderr[-200_000:]}

    if body.action == "git_commit":
        if not re.fullmatch(r"atlas/[a-z0-9][a-z0-9._/-]{1,100}", body.branch):
            raise HTTPException(422, "branch must use the governed atlas/ prefix")
        if len(body.message.strip()) < 5:
            raise HTTPException(422, "a descriptive commit message is required")
        if not body.files:
            raise HTTPException(422, "approved commit paths are required")
        base = workspace_base(body.workspace_id)
        approved_paths = [resolve_workspace_path(item.path, workspace_id=body.workspace_id).relative_to(base).as_posix() for item in body.files]
        code, _, stderr = await run_process(["git", "switch", "-c", body.branch], base)
        if code != 0 and "already exists" not in stderr:
            raise HTTPException(409, f"unable to create governed branch: {stderr[-500:]}")
        if code != 0:
            code, _, stderr = await run_process(["git", "switch", body.branch], base)
            if code != 0:
                raise HTTPException(409, f"unable to select governed branch: {stderr[-500:]}")
        code, _, stderr = await run_process(["git", "add", "--", *approved_paths], base)
        if code != 0:
            raise HTTPException(409, f"unable to stage approved paths: {stderr[-500:]}")
        code, stdout, stderr = await run_process(["git", "commit", "-m", body.message], base)
        if code != 0:
            raise HTTPException(409, f"unable to commit approved change set: {stderr[-500:] or stdout[-500:]}")
        code, commit_hash, stderr = await run_process(["git", "rev-parse", "HEAD"], base)
        if code != 0:
            raise HTTPException(409, f"unable to read commit evidence: {stderr[-500:]}")
        _, stat, _ = await run_process(["git", "show", "--stat", "--oneline", "HEAD"], base)
        return {"action": body.action, "branch": body.branch, "commit": commit_hash.strip(), "summary": stat[-200_000:], "exit_code": 0, "duration_ms": int((time.perf_counter() - started) * 1000)}

    if not body.command:
        raise HTTPException(422, "an allow-listed command is required")
    executable = Path(body.command[0]).name.lower()
    if executable not in ALLOWED_EXECUTABLES:
        raise HTTPException(403, f"executable '{executable}' is not allowed")
    working_directory = resolve_workspace_path(body.path or ".", directory=True, workspace_id=body.workspace_id)
    if not working_directory.is_dir():
        raise HTTPException(404, "working directory does not exist")
    try:
        return_code, stdout, stderr = await run_process(body.command, working_directory, body.timeout_seconds)
    except HTTPException:
        raise
    return {
        "action": body.action,
        "command": body.command,
        "working_directory": body.path or ".",
        "exit_code": return_code,
        "stdout": stdout[-200_000:],
        "stderr": stderr[-200_000:],
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
