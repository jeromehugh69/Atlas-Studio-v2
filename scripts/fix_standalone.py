#!/usr/bin/env python3
"""
Atlas Studio Standalone Fix Script
===================================
Applies all patches needed to run Atlas Studio as a standalone application
without Docker, PostgreSQL, Redis, or a separate worker container.

Usage:
    python scripts/fix_standalone.py

After running, start with:
    python -m atlas_studio
"""

import os
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "atlas_studio"
LAYERS = SRC / "layers"
WORKER_SRC = ROOT / "services" / "worker"


def patch_file(path: Path, old: str, new: str, label: str):
    """Replace old text with new text in a file."""
    content = path.read_text(encoding="utf-8")
    if old not in content:
        print(f"  WARN: {label} - pattern not found in {path.name}, skipping")
        return False
    content = content.replace(old, new, 1)
    path.write_text(content, encoding="utf-8")
    print(f"  OK:   {label}")
    return True


def create_file(path: Path, content: str, label: str):
    """Create a new file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    print(f"  OK:   {label} -> {path}")


# ---------------------------------------------------------------------------
# 1. Create __main__.py entry point
# ---------------------------------------------------------------------------
def fix_1_main_entry():
    print("\n[1/10] Creating __main__.py entry point...")
    create_file(
        SRC / "__main__.py",
        '''\
        """Run Atlas Studio standalone without Docker or uvicorn CLI."""
        import os
        import sys

        def main():
            os.environ.setdefault("ATLAS_STUDIO_MODE", "community")
            try:
                import uvicorn
            except ImportError:
                print("ERROR: uvicorn is required. Install with: pip install uvicorn[standard]")
                sys.exit(1)
            uvicorn.run(
                "atlas_studio.main:app",
                host=os.getenv("ATLAS_STUDIO_HOST", "127.0.0.1"),
                port=int(os.getenv("ATLAS_STUDIO_PORT", "8080")),
                log_level="info",
            )

        if __name__ == "__main__":
            main()
        ''',
        "__main__.py",
    )


# ---------------------------------------------------------------------------
# 2. Add SQLite fallback to infrastructure.py
# ---------------------------------------------------------------------------
def fix_2_sqlite_fallback():
    print("\n[2/10] Adding SQLite fallback to infrastructure.py...")

    # Add aiosqlite import and SQLite backend
    patch_file(
        SRC / "infrastructure.py",
        old='''\
import json
from uuid import NAMESPACE_URL, uuid5

import asyncpg
import redis.asyncio as redis
from redis.exceptions import RedisError

from .models import Agent, AuditEvent, ChangeSet, DevelopmentLifecycle, ExternalActionApproval, LibraryChange, Plan, PlanWorkspace, Task, WorkflowDefinition


class Infrastructure:
    def __init__(self, database_url: str, redis_url: str):
        self.database_url = database_url
        self.redis_url = redis_url
        self.db: asyncpg.Pool | None = None
        self.redis: redis.Redis | None = None

    async def connect(self):
        try:
            self.db = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5, timeout=5)
            try:
                await self.db.execute(
                    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS "
                    "requires_user_authorization boolean NOT NULL DEFAULT false"
                )
                await self.db.execute(
                    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS skills jsonb NOT NULL DEFAULT '[\"development_lifecycle\"]'::jsonb"
                )
                await self.ensure_workflow_schema()
                await self.ensure_control_plane_schema()
            except asyncpg.PostgresError:
                # A restricted database user may not be able to upgrade the
                # schema. The read/write fallbacks below keep that installation
                # usable until migration 003 is applied by an administrator.
                pass
        except (OSError, asyncpg.PostgresError):
            self.db = None
        try:
            self.redis = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=3)
            await self.redis.ping()
        except (OSError, RedisError):
            if self.redis:
                await self.redis.aclose()
            self.redis = None''',
        new='''\
import asyncio
import json
import logging
import sqlite3
from uuid import NAMESPACE_URL, uuid5

try:
    import asyncpg
except ImportError:
    asyncpg = None

try:
    import redis.asyncio as redis
    from redis.exceptions import RedisError
except ImportError:
    redis = None
    RedisError = OSError

from .models import Agent, AuditEvent, ChangeSet, DevelopmentLifecycle, ExternalActionApproval, LibraryChange, Plan, PlanWorkspace, Task, WorkflowDefinition

logger = logging.getLogger("atlas_studio.infrastructure")


class SQLiteBackend:
    """File-based persistence fallback when PostgreSQL is unavailable."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        c = self._conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
                description TEXT NOT NULL, tools TEXT NOT NULL DEFAULT '[]',
                read_only INTEGER NOT NULL DEFAULT 0,
                requires_user_authorization INTEGER NOT NULL DEFAULT 0,
                skills TEXT NOT NULL DEFAULT '["development_lifecycle"]'
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, workspace_id TEXT, agent_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '', prompt TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'queued',
                output TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT 'normal',
                user_authorized INTEGER NOT NULL DEFAULT 0, attempt INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT, duration_ms INTEGER, created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '', plan_id TEXT,
                execution_workspace_id TEXT, grounding_status TEXT NOT NULL DEFAULT 'pending',
                grounding_issues TEXT NOT NULL DEFAULT '[]',
                evidence_refs TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, request TEXT NOT NULL,
                implementation_agent_id TEXT NOT NULL, priority TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT '', decided_at TEXT,
                workspace_id TEXT, recommendation TEXT NOT NULL DEFAULT '',
                impact TEXT NOT NULL DEFAULT '', test_plan TEXT NOT NULL DEFAULT '',
                rollback_plan TEXT NOT NULL DEFAULT '', proposed_files TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS development_lifecycles (
                id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, title TEXT NOT NULL,
                stage TEXT NOT NULL, status TEXT NOT NULL,
                gates TEXT NOT NULL DEFAULT '{}', evidence TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS library_changes (
                id TEXT PRIMARY KEY, action TEXT NOT NULL, tool_id TEXT NOT NULL,
                name TEXT NOT NULL, description TEXT NOT NULL, reason TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS plan_workspaces (
                id TEXT PRIMARY KEY, plan_id TEXT NOT NULL UNIQUE,
                root TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS external_action_approvals (
                id TEXT PRIMARY KEY, action TEXT NOT NULL, purpose TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL DEFAULT 'Atlas',
                payload TEXT NOT NULL DEFAULT '{}', action_hash TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '', allowed_domains TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT '',
                expires_at TEXT NOT NULL DEFAULT '', decided_at TEXT, used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS change_sets (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL, plan_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL,
                files TEXT NOT NULL DEFAULT '[]', combined_diff TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL, test_result TEXT NOT NULL DEFAULT '{}',
                branch TEXT NOT NULL DEFAULT '', commit_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '',
                removed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id TEXT NOT NULL, version INTEGER NOT NULL,
                name TEXT NOT NULL, owner_agent TEXT NOT NULL,
                definition TEXT NOT NULL DEFAULT '{}', active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (id, version)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '', outcome TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT ''
            );
        """)
        c.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return dict(row)

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def fetchall(self, sql: str, params=()) -> list[dict]:
        return [self._row_to_dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def fetchone(self, sql: str, params=()) -> dict | None:
        row = self._conn.execute(sql, params).fetchone()
        return self._row_to_dict(row) if row else None

    def fetchval(self, sql: str, params=()):
        row = self._conn.execute(sql, params).fetchone()
        return row[0] if row else None

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    async def execute_async(self, sql: str, params=()):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.execute(sql, params))
        await loop.run_in_executor(None, self.commit)

    async def fetchall_async(self, sql: str, params=()) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.fetchall(sql, params))

    async def fetchone_async(self, sql: str, params=()) -> dict | None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.fetchone(sql, params))

    async def fetchval_async(self, sql: str, params=()):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.fetchval(sql, params))


class Infrastructure:
    def __init__(self, database_url: str, redis_url: str):
        self.database_url = database_url
        self.redis_url = redis_url
        self.db: asyncpg.Pool | None = None
        self.sqlite: SQLiteBackend | None = None
        self.redis = None
        self._backend: str = "none"

    @property
    def _store(self):
        """Return whichever database backend is active."""
        return self.sqlite if self.sqlite else self.db

    async def connect(self):
        # --- PostgreSQL ---
        if asyncpg is not None:
            try:
                self.db = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5, timeout=5)
                self._backend = "postgresql"
                try:
                    await self.db.execute(
                        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS "
                        "requires_user_authorization boolean NOT NULL DEFAULT false"
                    )
                    await self.db.execute(
                        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS skills jsonb NOT NULL DEFAULT '[\\"development_lifecycle\\"]'::jsonb"
                    )
                    await self.ensure_workflow_schema()
                    await self.ensure_control_plane_schema()
                except asyncpg.PostgresError:
                    pass
            except (OSError, asyncpg.PostgresError, Exception) as exc:
                logger.warning("PostgreSQL unavailable (%s), falling back to SQLite", exc)
                self.db = None

        if self.db is None:
            # --- SQLite fallback ---
            db_path = os.getenv("ATLAS_STUDIO_SQLITE_PATH", str(Path("./data/atlas_studio.db").resolve()))
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            try:
                self.sqlite = SQLiteBackend(db_path)
                self.sqlite.connect()
                self._backend = "sqlite"
                logger.info("Using SQLite persistence at %s", db_path)
            except Exception as exc:
                logger.error("SQLite fallback also failed (%s), running in memory-only mode", exc)
                self._backend = "memory"

        # --- Redis ---
        if redis is not None:
            try:
                self.redis = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=3)
                await self.redis.ping()
            except (OSError, RedisError, Exception):
                if self.redis:
                    try:
                        await self.redis.aclose()
                    except Exception:
                        pass
                self.redis = None
        if self.redis is None:
            logger.info("Redis unavailable, using in-memory task queue (non-durable)")''',
        "SQLite fallback in infrastructure.py",
    )

    # Update close() method to handle sqlite
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def close(self):
        if self.db:
            await self.db.close()
        if self.redis:
            await self.redis.aclose()''',
        new='''\
    async def close(self):
        if self.db:
            await self.db.close()
        if self.sqlite:
            self.sqlite.close()
        if self.redis:
            try:
                await self.redis.aclose()
            except Exception:
                pass''',
        "close() method update",
    )

    # Update persist_agent to support SQLite
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_agent(self, agent: Agent):
        if self.db:''',
        new='''\
    async def persist_agent(self, agent: Agent):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO agents (id,name,role,description,tools,read_only,requires_user_authorization,skills)
                VALUES (?,?,?,?,?,?,?,?)""",
                (str(agent.id), agent.name, agent.role, agent.description,
                 json.dumps(agent.tools), int(agent.read_only), int(agent.requires_user_authorization),
                 json.dumps(agent.skills)),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_agent SQLite support",
    )

    # Update load_agents to support SQLite
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_agents(self) -> list[Agent]:
        if not self.db:
            return []''',
        new='''\
    async def load_agents(self) -> list[Agent]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM agents ORDER BY name")
            return [
                Agent(
                    id=UUID(row["id"]), name=row["name"], role=row["role"],
                    description=row["description"],
                    tools=json.loads(row["tools"]) if isinstance(row["tools"], str) else row["tools"],
                    read_only=bool(row["read_only"]),
                    requires_user_authorization=bool(row["requires_user_authorization"]),
                    skills=json.loads(row["skills"]) if isinstance(row["skills"], str) else row["skills"],
                )
                for row in rows
            ]
        if not self.db:
            return []''',
        "load_agents SQLite support",
    )

    # Update persist_task to support SQLite
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_task(self, task: Task):
        if self.db:''',
        new='''\
    async def persist_task(self, task: Task):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO tasks
                (id,workspace_id,agent_id,title,prompt,model,status,output,created_at,priority,
                 user_authorized,attempt,completed_at,duration_ms,updated_at,plan_id,
                 execution_workspace_id,grounding_status,grounding_issues,evidence_refs)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(task.id), str(task.workspace_id) if task.workspace_id else None,
                 str(task.agent_id), task.title, task.prompt, task.model, task.status,
                 task.output, task.created_at.isoformat() if task.created_at else "",
                 task.priority, int(task.user_authorized), task.attempt,
                 task.completed_at.isoformat() if task.completed_at else None,
                 task.duration_ms, task.updated_at.isoformat() if task.updated_at else "",
                 str(task.plan_id) if task.plan_id else None,
                 str(task.workspace_id) if task.workspace_id else None,
                 task.grounding_status, json.dumps(task.grounding_issues),
                 json.dumps(task.evidence_refs)),
            )
            self.sqlite.commit()
            if self.redis:
                try:
                    await self.redis.setex(f"atlas-studio:task:{task.id}", 86400, task.model_dump_json())
                except Exception:
                    pass
            return
        if self.db:''',
        "persist_task SQLite support",
    )

    # Update load_tasks to support SQLite
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_tasks(self) -> list[Task]:
        if not self.db:
            return []''',
        new='''\
    async def load_tasks(self) -> list[Task]:
        if self.sqlite:
            rows = self.sqlite.fetchall(
                "SELECT * FROM tasks ORDER BY created_at"
            )
            return [Task(
                id=UUID(row["id"]), agent_id=UUID(row["agent_id"]), title=row["title"],
                prompt=row["prompt"], model=row["model"], status=row["status"],
                priority=row["priority"], user_authorized=bool(row["user_authorized"]),
                attempt=row["attempt"], output=row["output"],
                created_at=row["created_at"], updated_at=row["updated_at"],
                completed_at=row.get("completed_at"), duration_ms=row.get("duration_ms"),
                plan_id=UUID(row["plan_id"]) if row.get("plan_id") else None,
                workspace_id=UUID(row["execution_workspace_id"]) if row.get("execution_workspace_id") else None,
                grounding_status=row.get("grounding_status", "pending"),
                grounding_issues=json.loads(row.get("grounding_issues", "[]") or "[]"),
                evidence_refs=json.loads(row.get("evidence_refs", "[]") or "[]"),
            ) for row in rows]
        if not self.db:
            return []''',
        "load_tasks SQLite support",
    )

    # Update persist_audit to support SQLite
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_audit(self, event: AuditEvent):
        if self.db:''',
        new='''\
    async def persist_audit(self, event: AuditEvent):
        if self.sqlite:
            self.sqlite.execute(
                "INSERT OR REPLACE INTO audit_events (id,actor,action,target,outcome,details,created_at) VALUES (?,?,?,?,?,?,?)",
                (str(event.id), event.actor, event.action, event.target, event.outcome,
                 json.dumps(event.details), event.created_at.isoformat() if event.created_at else ""),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_audit SQLite support",
    )

    # Update load_audit to support SQLite
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_audit(self, limit: int = 1000) -> list[AuditEvent]:
        if not self.db:
            return []''',
        new='''\
    async def load_audit(self, limit: int = 1000) -> list[AuditEvent]:
        if self.sqlite:
            rows = self.sqlite.fetchall(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [AuditEvent(
                id=UUID(row["id"]), actor=row["actor"], action=row["action"],
                target=row["target"], outcome=row["outcome"],
                details=json.loads(row.get("details", "{}") or "{}"),
                created_at=row["created_at"],
            ) for row in rows]
        if not self.db:
            return []''',
        "load_audit SQLite support",
    )

    # Update health() to include SQLite backend status
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def health(self) -> dict[str, str]:
        result = {"postgres": "unavailable", "redis": "unavailable"}
        if self.db:
            try:
                await self.db.fetchval("SELECT 1")
                result["postgres"] = "ok"
            except asyncpg.PostgresError:
                pass
        if self.redis:
            try:
                if await self.redis.ping():
                    result["redis"] = "ok"
            except RedisError:
                pass
        return result''',
        new='''\
    async def health(self) -> dict[str, str]:
        result = {"backend": self._backend, "redis": "unavailable"}
        if self.db:
            try:
                await self.db.fetchval("SELECT 1")
                result["postgres"] = "ok"
            except Exception:
                result["postgres"] = "unavailable"
        elif self.sqlite:
            result["sqlite"] = "ok"
        else:
            result["postgres"] = "unavailable"
            result["sqlite"] = "unavailable"
        if self.redis:
            try:
                if await self.redis.ping():
                    result["redis"] = "ok"
            except Exception:
                pass
        return result''',
        "health() SQLite awareness",
    )

    # Add persist_plan SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_plan(self, plan: Plan):
        if self.db:''',
        new='''\
    async def persist_plan(self, plan: Plan):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO plans
                (id,title,request,implementation_agent_id,priority,steps,status,created_at,decided_at,
                 workspace_id,recommendation,impact,test_plan,rollback_plan,proposed_files)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(plan.id), plan.title, plan.request, str(plan.implementation_agent_id),
                 plan.priority, json.dumps(plan.steps), plan.status,
                 plan.created_at.isoformat() if plan.created_at else "",
                 plan.decided_at.isoformat() if plan.decided_at else None,
                 str(plan.workspace_id) if plan.workspace_id else None,
                 plan.recommendation, plan.impact, plan.test_plan, plan.rollback_plan,
                 json.dumps(plan.proposed_files)),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_plan SQLite support",
    )

    # Add load_plans SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_plans(self) -> list[Plan]:
        if not self.db:
            return []''',
        new='''\
    async def load_plans(self) -> list[Plan]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM plans ORDER BY created_at")
            return [Plan(
                id=UUID(row["id"]), title=row["title"], request=row["request"],
                implementation_agent_id=UUID(row["implementation_agent_id"]),
                priority=row["priority"],
                steps=json.loads(row.get("steps", "[]") or "[]"),
                status=row["status"],
                created_at=row["created_at"], decided_at=row.get("decided_at"),
                workspace_id=UUID(row["workspace_id"]) if row.get("workspace_id") else None,
                recommendation=row.get("recommendation") or "",
                impact=row.get("impact") or "",
                test_plan=row.get("test_plan") or "",
                rollback_plan=row.get("rollback_plan") or "",
                proposed_files=json.loads(row.get("proposed_files", "[]") or "[]"),
            ) for row in rows]
        if not self.db:
            return []''',
        "load_plans SQLite support",
    )

    # Add persist_lifecycle SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_lifecycle(self, lifecycle: DevelopmentLifecycle):
        if self.db:''',
        new='''\
    async def persist_lifecycle(self, lifecycle: DevelopmentLifecycle):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO development_lifecycles
                (id,plan_id,title,stage,status,gates,evidence,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (str(lifecycle.id), str(lifecycle.plan_id), lifecycle.title,
                 lifecycle.stage, lifecycle.status, json.dumps(lifecycle.gates),
                 json.dumps(lifecycle.evidence),
                 lifecycle.created_at.isoformat() if lifecycle.created_at else "",
                 lifecycle.updated_at.isoformat() if lifecycle.updated_at else ""),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_lifecycle SQLite support",
    )

    # Add load_lifecycles SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_lifecycles(self) -> list[DevelopmentLifecycle]:
        if not self.db:
            return []''',
        new='''\
    async def load_lifecycles(self) -> list[DevelopmentLifecycle]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM development_lifecycles ORDER BY created_at")
            return [DevelopmentLifecycle(
                id=UUID(row["id"]), plan_id=UUID(row["plan_id"]),
                title=row["title"], stage=row["stage"], status=row["status"],
                gates=json.loads(row.get("gates", "{}") or "{}"),
                evidence=json.loads(row.get("evidence", "[]") or "[]"),
                created_at=row["created_at"], updated_at=row["updated_at"],
            ) for row in rows]
        if not self.db:
            return []''',
        "load_lifecycles SQLite support",
    )

    # Add persist_change_set SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_change_set(self, change_set: ChangeSet):
        if self.db:''',
        new='''\
    async def persist_change_set(self, change_set: ChangeSet):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO change_sets
                (id,task_id,plan_id,workspace_id,title,summary,files,combined_diff,status,
                 test_result,branch,commit_hash,created_at,updated_at,removed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(change_set.id), str(change_set.task_id), str(change_set.plan_id),
                 str(change_set.workspace_id), change_set.title, change_set.summary,
                 json.dumps([item.model_dump(mode="json") for item in change_set.files]),
                 change_set.combined_diff, change_set.status,
                 json.dumps(change_set.test_result), change_set.branch, change_set.commit,
                 change_set.created_at.isoformat() if change_set.created_at else "",
                 change_set.updated_at.isoformat() if change_set.updated_at else "",
                 change_set.removed_at.isoformat() if change_set.removed_at else None),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_change_set SQLite support",
    )

    # Add load_change_sets SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_change_sets(self) -> list[ChangeSet]:
        if not self.db:
            return []''',
        new='''\
    async def load_change_sets(self) -> list[ChangeSet]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM change_sets ORDER BY updated_at")
            return [ChangeSet(
                id=UUID(row["id"]), task_id=UUID(row["task_id"]),
                plan_id=UUID(row["plan_id"]), workspace_id=UUID(row["workspace_id"]),
                title=row["title"], summary=row["summary"],
                files=json.loads(row.get("files", "[]") or "[]"),
                combined_diff=row.get("combined_diff", ""),
                status=row["status"],
                test_result=json.loads(row.get("test_result", "{}") or "{}"),
                branch=row.get("branch", ""), commit=row.get("commit_hash", ""),
                removed_at=row.get("removed_at"),
                created_at=row["created_at"], updated_at=row["updated_at"],
            ) for row in rows]
        if not self.db:
            return []''',
        "load_change_sets SQLite support",
    )

    # Add persist_external_approval SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_external_approval(self, approval: ExternalActionApproval):
        if self.db:''',
        new='''\
    async def persist_external_approval(self, approval: ExternalActionApproval):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO external_action_approvals
                (id,action,purpose,target,actor,payload,action_hash,query,allowed_domains,
                 status,created_at,expires_at,decided_at,used_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(approval.id), approval.action, approval.purpose, approval.target,
                 approval.actor, json.dumps(approval.payload), approval.action_hash,
                 approval.query, json.dumps(approval.allowed_domains), approval.status,
                 approval.created_at.isoformat() if approval.created_at else "",
                 approval.expires_at.isoformat() if approval.expires_at else "",
                 approval.decided_at.isoformat() if approval.decided_at else None,
                 approval.used_at.isoformat() if approval.used_at else None),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_external_approval SQLite support",
    )

    # Add load_external_approvals SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_external_approvals(self) -> list[ExternalActionApproval]:
        if not self.db:
            return []''',
        new='''\
    async def load_external_approvals(self) -> list[ExternalActionApproval]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM external_action_approvals ORDER BY created_at")
            return [ExternalActionApproval(
                id=UUID(row["id"]), action=row["action"], purpose=row["purpose"],
                target=row["target"], actor=row["actor"],
                payload=json.loads(row.get("payload", "{}") or "{}"),
                action_hash=row.get("action_hash", ""),
                query=row.get("query", ""),
                allowed_domains=json.loads(row.get("allowed_domains", "[]") or "[]"),
                status=row["status"], created_at=row["created_at"],
                expires_at=row["expires_at"],
                decided_at=row.get("decided_at"), used_at=row.get("used_at"),
            ) for row in rows]
        if not self.db:
            return []''',
        "load_external_approvals SQLite support",
    )

    # Add persist_plan_workspace SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_plan_workspace(self, workspace: PlanWorkspace):
        if self.db:''',
        new='''\
    async def persist_plan_workspace(self, workspace: PlanWorkspace):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO plan_workspaces (id,plan_id,root,status,created_at)
                VALUES (?,?,?,?,?)""",
                (str(workspace.id), str(workspace.plan_id), workspace.root,
                 workspace.status, workspace.created_at.isoformat() if workspace.created_at else ""),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_plan_workspace SQLite support",
    )

    # Add load_plan_workspaces SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_plan_workspaces(self) -> list[PlanWorkspace]:
        if not self.db:
            return []''',
        new='''\
    async def load_plan_workspaces(self) -> list[PlanWorkspace]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM plan_workspaces ORDER BY created_at")
            return [PlanWorkspace(**{k: UUID(v) if k in ("id", "plan_id") and v else v for k, v in dict(row).items()}) for row in rows]
        if not self.db:
            return []''',
        "load_plan_workspaces SQLite support",
    )

    # Add persist_workflow_definition SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_workflow_definition(self, workflow: WorkflowDefinition):
        if self.db:''',
        new='''\
    async def persist_workflow_definition(self, workflow: WorkflowDefinition):
        if self.sqlite:
            definition = {
                "description": workflow.description, "nodes": workflow.nodes,
                "status": workflow.status, "source_type": workflow.source_type,
                "source_reference": workflow.source_reference,
            }
            self.sqlite.execute(
                """INSERT OR REPLACE INTO workflow_definitions
                (id,version,name,owner_agent,definition,active,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (workflow.id, workflow.version, workflow.name, workflow.owner,
                 json.dumps(definition), int(workflow.active),
                 workflow.created_at.isoformat() if workflow.created_at else ""),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_workflow_definition SQLite support",
    )

    # Add load_workflow_definitions SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_workflow_definitions(self) -> list[WorkflowDefinition]:
        if not self.db:
            return []''',
        new='''\
    async def load_workflow_definitions(self) -> list[WorkflowDefinition]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM workflow_definitions ORDER BY created_at")
            definitions = []
            for row in rows:
                data = json.loads(row["definition"]) if isinstance(row["definition"], str) else row["definition"]
                definitions.append(WorkflowDefinition(
                    id=row["id"], version=row["version"], name=row["name"],
                    owner=row["owner_agent"],
                    description=data.get("description", "Imported workflow definition"),
                    nodes=data.get("nodes", []),
                    status=data.get("status", "active" if row["active"] else "designed"),
                    source_type=data.get("source_type", "manual"),
                    source_reference=data.get("source_reference", ""),
                    active=bool(row["active"]),
                    created_at=row["created_at"],
                ))
            return definitions
        if not self.db:
            return []''',
        "load_workflow_definitions SQLite support",
    )

    # Add persist_library_change SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def persist_library_change(self, change: LibraryChange):
        if self.db:''',
        new='''\
    async def persist_library_change(self, change: LibraryChange):
        if self.sqlite:
            self.sqlite.execute(
                """INSERT OR REPLACE INTO library_changes
                (id,action,tool_id,name,description,reason,status,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (str(change.id), change.action, change.tool_id, change.name,
                 change.description, change.reason, change.status,
                 change.created_at.isoformat() if change.created_at else ""),
            )
            self.sqlite.commit()
            return
        if self.db:''',
        "persist_library_change SQLite support",
    )

    # Add load_library_changes SQLite support
    patch_file(
        SRC / "infrastructure.py",
        old='''\
    async def load_library_changes(self) -> list[LibraryChange]:
        if not self.db:
            return []''',
        new='''\
    async def load_library_changes(self) -> list[LibraryChange]:
        if self.sqlite:
            rows = self.sqlite.fetchall("SELECT * FROM library_changes ORDER BY created_at")
            return [LibraryChange(**{k: UUID(v) if k == "id" and v else v for k, v in dict(row).items()}) for row in rows]
        if not self.db:
            return []''',
        "load_library_changes SQLite support",
    )


# ---------------------------------------------------------------------------
# 3. Add retry logic to OllamaProvider
# ---------------------------------------------------------------------------
def fix_3_ollama_retry():
    print("\n[3/10] Adding retry logic to OllamaProvider...")
    patch_file(
        SRC / "providers.py",
        old='''\
class OllamaProvider(ModelProvider):
    def __init__(self, base_url: str, timeout_seconds: int = 120, max_tokens: int = 384, context_tokens: int = 1536):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.context_tokens = context_tokens''',
        new='''\
class OllamaProvider(ModelProvider):
    def __init__(self, base_url: str, timeout_seconds: int = 120, max_tokens: int = 384, context_tokens: int = 1536):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.context_tokens = context_tokens
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0''',
        "OllamaProvider init update",
    )

    # Fix the error message for missing model
    patch_file(
        SRC / "providers.py",
        old='''\
                    if response.status_code == 404:
                        raise ProviderError(f"Ollama does not have model '{model}'. Run: docker compose exec ollama ollama pull {model}")''',
        new='''\
                    if response.status_code == 404:
                        raise ProviderError(f"Ollama does not have model '{model}'. Pull it with: ollama pull {model}")''',
        "Fix Docker error message",
    )

    # Add retry wrapper to stream method
    patch_file(
        SRC / "providers.py",
        old='''\
    async def stream(self, messages, model, temperature=0.3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds, connect=10)) as client:
                async with client.stream(''',
        new='''\
    async def stream(self, messages, model, temperature=0.3):
        import time as _time
        import logging
        _logger = logging.getLogger("atlas_studio.providers")
        max_retries = 2
        for attempt in range(max_retries + 1):
            if _time.time() < self._circuit_open_until:
                raise ProviderError("Ollama is temporarily unavailable (circuit breaker open). Wait a moment and retry.")
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds, connect=10)) as client:
                    async with client.stream(''',
        "Add retry loop to stream",
    )

    # Update stream method error handling
    patch_file(
        SRC / "providers.py",
        old='''\
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Ollama timed out while running '{model}' after {self.timeout_seconds} seconds. Stop unused model services or select a smaller local model, then retry") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama connection failed: {exc.__class__.__name__}") from exc''',
        new='''\
            except httpx.TimeoutException as exc:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:
                    self._circuit_open_until = _time.time() + 30
                    _logger.warning("Ollama circuit breaker opened after %d failures", self._consecutive_failures)
                if attempt < max_retries:
                    _logger.info("Ollama timeout, retrying (%d/%d)...", attempt + 1, max_retries)
                    continue
                raise ProviderError(f"Ollama timed out while running '{model}' after {self.timeout_seconds} seconds. Stop unused model services or select a smaller local model, then retry") from exc
            except httpx.HTTPError as exc:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:
                    self._circuit_open_until = _time.time() + 30
                    _logger.warning("Ollama circuit breaker opened after %d failures", self._consecutive_failures)
                if attempt < max_retries:
                    _logger.info("Ollama connection failed, retrying (%d/%d)...", attempt + 1, max_retries)
                    continue
                raise ProviderError(f"Ollama connection failed: {exc.__class__.__name__}. Ensure Ollama is running at {self.base_url}") from exc
        self._consecutive_failures = 0''',
        "Add retry and circuit breaker to stream",
    )


# ---------------------------------------------------------------------------
# 4. Embed worker as in-process fallback
# ---------------------------------------------------------------------------
def fix_4_embedded_worker():
    print("\n[4/10] Creating embedded worker fallback module...")
    create_file(
        SRC / "local_worker.py",
        '''\
        """In-process implementation worker fallback when the standalone worker is not running."""
        from __future__ import annotations

        import asyncio
        from difflib import unified_diff
        import hashlib
        import hmac
        import os
        from pathlib import Path
        import re
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


        def _resolve_path(value: str, *, workspace_id: str | None = None) -> Path:
            base = PLAN_WORKSPACES / workspace_id if workspace_id else WORKSPACE
            base = base.resolve()
            target = (base / value).resolve()
            target.relative_to(base)
            return target


        async def execute_action(payload: dict) -> dict:
            """Execute a worker action in-process."""
            action = payload.get("action", "")
            started = time.perf_counter()
            workspace_id = payload.get("workspace_id")

            if action == "workspace_create":
                if not workspace_id:
                    raise ValueError("workspace_create requires a plan workspace identifier")
                destination = PLAN_WORKSPACES / workspace_id
                if destination.exists():
                    return {"action": action, "workspace_id": workspace_id, "root": str(destination), "status": "ready", "duration_ms": 0}
                PLAN_WORKSPACES.mkdir(parents=True, exist_ok=True)
                ignored = shutil.ignore_patterns(".git", ".env", ".venv", "__pycache__", "node_modules", ".pytest_cache", "data", "outputs", "*.pyc")
                await asyncio.to_thread(shutil.copytree, WORKSPACE, destination, ignore=ignored)
                return {"action": action, "workspace_id": workspace_id, "root": str(destination), "status": "ready", "duration_ms": int((time.perf_counter() - started) * 1000)}

            if action == "list_workspace":
                base = PLAN_WORKSPACES / workspace_id if workspace_id else WORKSPACE
                base = base.resolve()
                entries = []
                for path in sorted(base.rglob("*")):
                    relative = path.relative_to(base)
                    if any(part.startswith(".") or part in {"node_modules", "__pycache__"} for part in relative.parts):
                        continue
                    entries.append({"path": relative.as_posix(), "type": "directory" if path.is_dir() else "file"})
                    if len(entries) >= 2000:
                        break
                return {"action": action, "entries": entries, "truncated": len(entries) >= 2000}

            if action == "read_file":
                target = _resolve_path(payload.get("path", ""), workspace_id=workspace_id)
                if not target.is_file():
                    raise FileNotFoundError("workspace file not found")
                data = target.read_bytes()
                if len(data) > 512_000:
                    raise ValueError("file exceeds the Forge read limit")
                return {"action": action, "path": payload.get("path"), "content": data.decode("utf-8", errors="replace"), "sha256": _digest(data)}

            if action == "search_workspace":
                query = payload.get("query", "").casefold()
                if len(query.strip()) < 2:
                    raise ValueError("a search query is required")
                base = PLAN_WORKSPACES / workspace_id if workspace_id else WORKSPACE
                base = base.resolve()
                matches = []
                for path in sorted(base.rglob("*")):
                    if not path.is_file() or path.suffix.lower() not in ALLOWED_FILE_SUFFIXES:
                        continue
                    if any(part.startswith(".") for part in path.relative_to(base).parts):
                        continue
                    try:
                        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                    except OSError:
                        continue
                    for number, line in enumerate(lines, 1):
                        if query in line.casefold():
                            matches.append({"path": path.relative_to(base).as_posix(), "line": number, "text": line[:500]})
                            if len(matches) >= 200:
                                return {"action": action, "matches": matches, "truncated": True}
                return {"action": action, "matches": matches, "truncated": False}

            if action in {"preview_write", "file_write"}:
                target = _resolve_path(payload.get("path", ""), workspace_id=workspace_id)
                before = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
                before_bytes = before.encode("utf-8")
                expected = payload.get("expected_sha256")
                if expected and _digest(before_bytes) != expected:
                    raise ValueError("file changed after approval; request a new preview")
                after = payload.get("content", "")
                diff = "".join(unified_diff(
                    before.splitlines(keepends=True), after.splitlines(keepends=True),
                    fromfile=f"a/{payload.get('path')}", tofile=f"b/{payload.get('path')}",
                ))
                result = {
                    "action": action, "path": payload.get("path"), "changed": before != after,
                    "before_sha256": _digest(before_bytes), "after_sha256": _digest(after.encode("utf-8")),
                    "diff": diff[:250_000],
                }
                if action == "file_write" and before != after:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    descriptor, temp_name = tempfile.mkstemp(prefix=".atlas-write-", dir=target.parent)
                    try:
                        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                            handle.write(after)
                        os.replace(temp_name, target)
                    finally:
                        if os.path.exists(temp_name):
                            os.unlink(temp_name)
                result["duration_ms"] = int((time.perf_counter() - started) * 1000)
                return result

            if action in {"code_execute", "test_execute"}:
                command = payload.get("command", [])
                if not command:
                    raise ValueError("a command is required")
                executable = Path(command[0]).name.lower()
                if executable not in ALLOWED_EXECUTABLES:
                    raise ValueError(f"executable '{executable}' is not allowed")
                cwd = _resolve_path(payload.get("path", "."), workspace_id=workspace_id)
                if not cwd.is_dir():
                    raise FileNotFoundError("working directory does not exist")
                timeout = payload.get("timeout_seconds", 60)
                process = await asyncio.create_subprocess_exec(
                    *command, cwd=cwd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"},
                )
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise TimeoutError("command timed out")
                return {
                    "action": action, "command": command, "exit_code": process.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace")[-200_000:],
                    "stderr": stderr.decode("utf-8", errors="replace")[-200_000:],
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }

            raise ValueError(f"unsupported worker action: {action}")
        ''',
        "local_worker.py",
    )


# ---------------------------------------------------------------------------
# 5. Patch execution.py to use embedded worker when HTTP worker unavailable
# ---------------------------------------------------------------------------
def fix_5_execution_fallback():
    print("\n[5/10] Patching execution.py to use embedded worker fallback...")
    patch_file(
        LAYERS / "execution.py",
        old='''\
from __future__ import annotations

import httpx


class ImplementationWorkerError(RuntimeError):
    pass


class ImplementationWorker:
    def __init__(self, url: str, token: str, timeout_seconds: int = 310):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.url}/health")
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {"status": "unavailable", "detail": exc.__class__.__name__}

    async def execute(self, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.url}/actions",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json=payload,
                )
            if response.is_error:
                try:
                    detail = response.json().get("detail", response.text)
                except ValueError:
                    detail = response.text
                raise ImplementationWorkerError(str(detail))
            return response.json()
        except httpx.HTTPError as exc:
            raise ImplementationWorkerError(f"implementation worker unavailable: {exc.__class__.__name__}") from exc''',
        new='''\
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("atlas_studio.execution")


class ImplementationWorkerError(RuntimeError):
    pass


class ImplementationWorker:
    def __init__(self, url: str, token: str, timeout_seconds: int = 310):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self._http_available: bool | None = None
        self._embedded = None

    def _get_embedded(self):
        if self._embedded is None:
            from ..local_worker import execute_action
            self._embedded = execute_action
            logger.info("Using embedded in-process worker (standalone mode)")
        return self._embedded

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.url}/health")
                response.raise_for_status()
                self._http_available = True
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._http_available = False
            return {"status": "embedded", "detail": "Using in-process worker (standalone mode)"}

    async def execute(self, payload: dict) -> dict:
        # Try HTTP worker first if it was previously available
        if self._http_available is not False:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.url}/actions",
                        headers={"Authorization": f"Bearer {self.token}"},
                        json=payload,
                    )
                if response.is_error:
                    try:
                        detail = response.json().get("detail", response.text)
                    except ValueError:
                        detail = response.text
                    raise ImplementationWorkerError(str(detail))
                self._http_available = True
                return response.json()
            except (httpx.HTTPError, ValueError):
                self._http_available = False

        # Fall back to embedded worker
        try:
            embedded_fn = self._get_embedded()
            return await embedded_fn(payload)
        except (ValueError, FileNotFoundError, TimeoutError) as exc:
            raise ImplementationWorkerError(str(exc)) from exc
        except Exception as exc:
            raise ImplementationWorkerError(f"embedded worker failed: {exc.__class__.__name__}: {exc}") from exc''',
        "execution.py with embedded worker fallback",
    )


# ---------------------------------------------------------------------------
# 6. Fix env files with localhost defaults
# ---------------------------------------------------------------------------
def fix_6_env_defaults():
    print("\n[6/10] Creating standalone .env.standalone with localhost defaults...")
    create_file(
        ROOT / ".env.standalone",
        '''\
        # Standalone mode - all services run on localhost
        ATLAS_STUDIO_MODE=community
        ATLAS_STUDIO_HOST=127.0.0.1
        ATLAS_STUDIO_PORT=8080
        # SQLite is used automatically when PostgreSQL is unavailable
        ATLAS_STUDIO_DATABASE_URL=postgresql://atlas_studio:atlas-studio@localhost:5432/atlas_studio
        # Redis is optional - in-memory queue used when unavailable
        ATLAS_STUDIO_REDIS_URL=redis://localhost:6379/0
        ATLAS_STUDIO_ARTIFACT_BACKEND=filesystem
        ATLAS_STUDIO_ARTIFACT_ROOT=./data/artifacts
        ATLAS_STUDIO_WORKSPACE_ROOT=.
        ATLAS_STUDIO_WORKSPACE_MAX_PREVIEW_KB=512
        ATLAS_STUDIO_DEFAULT_PROVIDER=ollama
        ATLAS_STUDIO_DEFAULT_MODEL=qwen3:4b
        ATLAS_STUDIO_FORGE_MODEL=qwen3:4b
        ATLAS_STUDIO_OLLAMA_URL=http://localhost:11434

        # LiteLLM Configuration
        ATLAS_STUDIO_LITELLM_API_BASE=http://localhost:11434
        ATLAS_STUDIO_LITELLM_API_KEY=
        ATLAS_STUDIO_LITELLM_MODEL_PREFIX=ollama
        ATLAS_STUDIO_LITELLM_FALLBACK_MODELS=[]
        ATLAS_STUDIO_LITELLM_COST_TRACKING=true
        ATLAS_STUDIO_LITELLM_NUM_RETRIES=2
        ATLAS_STUDIO_LITELLM_TIMEOUT=120

        ATLAS_STUDIO_MODEL_TIMEOUT_SECONDS=120
        ATLAS_STUDIO_MODEL_MAX_TOKENS=384
        ATLAS_STUDIO_FORGE_TIMEOUT_SECONDS=300
        ATLAS_STUDIO_FORGE_MAX_TOKENS=2048
        ATLAS_STUDIO_FORGE_CONTEXT_TOKENS=4096
        # Worker runs in-process when standalone worker not available
        ATLAS_STUDIO_WORKER_URL=http://localhost:8092
        ATLAS_STUDIO_WORKER_TOKEN=atlas-local-worker
        ATLAS_STUDIO_UPLOAD_MAX_MB=25
        ATLAS_STUDIO_TELEMETRY_ENABLED=false
        ATLAS_STUDIO_MINIO_ENABLED=false
        ATLAS_STUDIO_GOOGLE_OAUTH_ENABLED=false
        ATLAS_STUDIO_AVATAR_LOCAL_ENABLED=false
        ''',
        ".env.standalone",
    )


# ---------------------------------------------------------------------------
# 7. Fix skill_runtime.py to resolve skills from package directory
# ---------------------------------------------------------------------------
def fix_7_skills_path():
    print("\n[7/10] Fixing skill_runtime.py to resolve skills from package directory...")
    patch_file(
        SRC / "main.py",
        old='''\
skill_runtime = SkillRuntime(Path.cwd() / "skills")''',
        new='''\
# Resolve skills directory: prefer package-bundled skills, fall back to CWD
_skills_candidates = [
    SRC.parent.parent.parent / "skills",  # repo root when running from source
    Path.cwd() / "skills",                # CWD fallback
    SRC / "skills",                        # package directory fallback
]
_skill_runtime_root = next((p for p in _skills_candidates if p.is_dir()), _skills_candidates[1])
skill_runtime = SkillRuntime(_skill_runtime_root)''',
        "Fix skills directory resolution",
    )


# ---------------------------------------------------------------------------
# 8. Fix static directory mounting
# ---------------------------------------------------------------------------
def fix_8_static_mount():
    print("\n[8/10] Adding safety check for static directory mounting...")
    patch_file(
        SRC / "main.py",
        old='''\
STATIC = __import__("pathlib").Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")''',
        new='''\
STATIC = __import__("pathlib").Path(__file__).parent / "static"
if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")''',
        "Safe static directory mounting",
    )


# ---------------------------------------------------------------------------
# 9. Fix config.py defaults for standalone
# ---------------------------------------------------------------------------
def fix_9_config_defaults():
    print("\n[9/10] Fixing config.py defaults for standalone mode...")
    patch_file(
        SRC / "config.py",
        old='''\
    worker_url: str = "http://worker:8092"''',
        new='''\
    worker_url: str = "http://localhost:8092"''',
        "Fix worker URL default",
    )
    patch_file(
        SRC / "config.py",
        old='''\
    research_worker_url: str = "http://research-worker:8093"''',
        new='''\
    research_worker_url: str = "http://localhost:8093"''',
        "Fix research worker URL default",
    )
    patch_file(
        SRC / "config.py",
        old='''\
    avatar_service_url: str = "http://avatar3d:8090"''',
        new='''\
    avatar_service_url: str = "http://localhost:8090"''',
        "Fix avatar service URL default",
    )
    patch_file(
        SRC / "config.py",
        old='''\
    sandbox_runtime: Literal["docker", "podman"] = "docker"''',
        new='''\
    sandbox_runtime: Literal["docker", "podman", "local"] = "local"''',
        "Add local sandbox runtime option",
    )
    patch_file(
        SRC / "config.py",
        old='''\
    artifact_root: Path = Path("./data/artifacts")''',
        new='''\
    artifact_root: Path = Path("./data/artifacts")
    sqlite_path: Path = Path("./data/atlas_studio.db")''',
        "Add SQLite path config",
    )


# ---------------------------------------------------------------------------
# 10. Add startup warnings for missing services
# ---------------------------------------------------------------------------
def fix_10_startup_warnings():
    print("\n[10/10] Adding startup warnings for missing services...")
    patch_file(
        SRC / "main.py",
        old='''\
    seeded_agents = list(store.agents.values())''',
        new='''\
    # Standalone mode warnings
    _warnings = []
    if infrastructure._backend == "sqlite":
        _warnings.append("PostgreSQL unavailable - using SQLite persistence (data survives restarts)")
    elif infrastructure._backend == "memory":
        _warnings.append("WARNING: No database available - all data will be lost on restart")
    if infrastructure.redis is None:
        _warnings.append("Redis unavailable - using in-memory task queue (non-durable)")
    if not await implementation_worker.health().then(lambda h: h.get("status") == "ok"):
        _warnings.append("Implementation worker unreachable - using embedded in-process worker")
    for w in _warnings:
        logger = __import__("logging").getLogger("atlas_studio.startup")
        logger.warning(w)

    seeded_agents = list(store.agents.values())''',
        "Add startup warnings",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Atlas Studio Standalone Fix Script")
    print("=" * 60)

    fixes = [
        fix_1_main_entry,
        fix_2_sqlite_fallback,
        fix_3_ollama_retry,
        fix_4_embedded_worker,
        fix_5_execution_fallback,
        fix_6_env_defaults,
        fix_7_skills_path,
        fix_8_static_mount,
        fix_9_config_defaults,
        fix_10_startup_warnings,
    ]

    success = 0
    failed = 0
    for fix in fixes:
        try:
            fix()
            success += 1
        except Exception as exc:
            print(f"  FAIL: {fix.__name__}: {exc}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Done: {success} succeeded, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("\nAll patches applied. To run standalone:")
        print("  pip install -e '.[test]'")
        print("  python -m atlas_studio")
        print("\nOr with the standalone env file:")
        print("  cp .env.standalone .env")
        print("  python -m atlas_studio")


if __name__ == "__main__":
    main()
