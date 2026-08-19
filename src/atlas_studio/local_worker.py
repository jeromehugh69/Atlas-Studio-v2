"""In-process implementation worker fallback for standalone mode."""
from __future__ import annotations

import asyncio
from difflib import unified_diff
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time


WORKSPACE = Path(os.getenv("ATLAS_STUDIO_WORKSPACE_ROOT", ".")).resolve()
PLAN_WORKSPACES = Path(os.getenv("ATLAS_STUDIO_PLAN_WORKSPACES", "./data/plan_workspaces")).resolve()
ALLOWED_FILE_SUFFIXES = {
    ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".md", ".txt", ".ps1", ".sh",
}
ALLOWED_EXECUTABLES = {"python", "python3", "pytest"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolve(value: str, workspace_id: str | None = None) -> Path:
    base = (PLAN_WORKSPACES / workspace_id).resolve() if workspace_id else WORKSPACE
    target = (base / value).resolve()
    target.relative_to(base)
    return target


async def execute_action(payload: dict) -> dict:
    """Execute a worker action in-process. Mirrors services/worker/app.py."""
    action = payload.get("action", "")
    started = time.perf_counter()
    wid = payload.get("workspace_id")

    if action == "workspace_create":
        if not wid:
            raise ValueError("workspace_create requires a plan workspace identifier")
        dest = PLAN_WORKSPACES / wid
        if dest.exists():
            return {"action": action, "workspace_id": wid, "root": str(dest), "status": "ready", "duration_ms": 0}
        PLAN_WORKSPACES.mkdir(parents=True, exist_ok=True)
        ignored = shutil.ignore_patterns(".git", ".env", ".venv", "__pycache__", "node_modules", ".pytest_cache", "data", "outputs", "*.pyc")
        await asyncio.to_thread(shutil.copytree, WORKSPACE, dest, ignore=ignored)
        return {"action": action, "workspace_id": wid, "root": str(dest), "status": "ready", "duration_ms": int((time.perf_counter() - started) * 1000)}

    if action == "list_workspace":
        base = (PLAN_WORKSPACES / wid).resolve() if wid else WORKSPACE
        entries = []
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(base)
            if any(part.startswith(".") or part in {"node_modules", "__pycache__"} for part in rel.parts):
                continue
            entries.append({"path": rel.as_posix(), "type": "directory" if p.is_dir() else "file"})
            if len(entries) >= 2000:
                break
        return {"action": action, "entries": entries, "truncated": len(entries) >= 2000}

    if action == "read_file":
        target = _resolve(payload.get("path", ""), wid)
        if not target.is_file():
            raise FileNotFoundError("workspace file not found")
        data = target.read_bytes()
        if len(data) > 512_000:
            raise ValueError("file exceeds read limit")
        return {"action": action, "path": payload.get("path"), "content": data.decode("utf-8", errors="replace"), "sha256": _digest(data)}

    if action == "search_workspace":
        query = payload.get("query", "").casefold()
        if len(query.strip()) < 2:
            raise ValueError("a search query is required")
        base = (PLAN_WORKSPACES / wid).resolve() if wid else WORKSPACE
        matches = []
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in ALLOWED_FILE_SUFFIXES:
                continue
            if any(part.startswith(".") for part in p.relative_to(base).parts):
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for num, line in enumerate(lines, 1):
                if query in line.casefold():
                    matches.append({"path": p.relative_to(base).as_posix(), "line": num, "text": line[:500]})
                    if len(matches) >= 200:
                        return {"action": action, "matches": matches, "truncated": True}
        return {"action": action, "matches": matches, "truncated": False}

    if action in {"preview_write", "file_write"}:
        target = _resolve(payload.get("path", ""), wid)
        before = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        before_bytes = before.encode("utf-8")
        expected = payload.get("expected_sha256")
        if expected and _digest(before_bytes) != expected:
            raise ValueError("file changed after approval")
        after = payload.get("content", "")
        diff = "".join(unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile="a/" + payload.get("path", ""), tofile="b/" + payload.get("path", ""),
        ))
        result = {"action": action, "path": payload.get("path"), "changed": before != after,
                  "before_sha256": _digest(before_bytes), "after_sha256": _digest(after.encode("utf-8")),
                  "diff": diff[:250_000]}
        if action == "file_write" and before != after:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".atlas-write-", dir=target.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as h:
                    h.write(after)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        result["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    if action in {"code_execute", "test_execute"}:
        command = payload.get("command", [])
        if not command:
            raise ValueError("a command is required")
        exe = Path(command[0]).name.lower()
        if exe not in ALLOWED_EXECUTABLES:
            raise ValueError(f"executable '{exe}' is not allowed")
        cwd = _resolve(payload.get("path", "."), wid)
        if not cwd.is_dir():
            raise FileNotFoundError("working directory does not exist")
        timeout = payload.get("timeout_seconds", 60)
        proc = await asyncio.create_subprocess_exec(
            *command, cwd=cwd, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError("command timed out")
        return {"action": action, "command": command, "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[-200_000:],
                "stderr": stderr.decode("utf-8", errors="replace")[-200_000:],
                "duration_ms": int((time.perf_counter() - started) * 1000)}

    raise ValueError(f"unsupported action: {action}")
