import asyncio
import hashlib
import json
import logging
import os
import sqlite3
from pathlib import Path
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

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

logger = logging.getLogger("atlas_studio.infrastructure")


class SQLiteEncryption:
    """Encrypt sensitive data before writing to SQLite."""

    def __init__(self, key: str | None = None):
        if Fernet is None:
            raise ImportError("cryptography package required for SQLite encryption")
        if key:
            self._key = hashlib.sha256(key.encode()).digest()
            self._fernet = Fernet(hashlib.sha256(key.encode()).urlsafe_b64digest()[:32])
        else:
            self._key = Fernet.generate_key()
            self._fernet = Fernet(self._key)

    def encrypt(self, data: str) -> str:
        return self._fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        return self._fernet.decrypt(encrypted_data.encode()).decode()

    def encrypt_dict(self, data: dict) -> str:
        return self.encrypt(json.dumps(data))

    def decrypt_dict(self, encrypted_data: str) -> dict:
        return json.loads(self.decrypt(encrypted_data))

from .models import Agent, AuditEvent, ChangeSet, DevelopmentLifecycle, ExternalActionApproval, LibraryChange, Plan, PlanWorkspace, Task, WorkflowDefinition



class SQLiteBackend:
    """File-based persistence fallback when PostgreSQL is unavailable."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._conn = None

    def connect(self):
        import sqlite3
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
                description TEXT NOT NULL, tools TEXT NOT NULL DEFAULT '[]',
                read_only INTEGER NOT NULL DEFAULT 0,
                requires_user_authorization INTEGER NOT NULL DEFAULT 0,
                skills TEXT NOT NULL DEFAULT '[\"\"development_lifecycle\"\" \"]'
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, workspace_id TEXT, agent_id TEXT NOT NULL,
                title TEXT, prompt TEXT, model TEXT, status TEXT DEFAULT 'queued',
                output TEXT DEFAULT '', priority TEXT DEFAULT 'normal',
                user_authorized INTEGER DEFAULT 0, attempt INTEGER DEFAULT 0,
                completed_at TEXT, duration_ms INTEGER, created_at TEXT,
                updated_at TEXT, plan_id TEXT, execution_workspace_id TEXT,
                grounding_status TEXT DEFAULT 'pending',
                grounding_issues TEXT DEFAULT '[]', evidence_refs TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, request TEXT NOT NULL,
                implementation_agent_id TEXT NOT NULL, priority TEXT NOT NULL,
                steps TEXT DEFAULT '[]', status TEXT NOT NULL,
                created_at TEXT, decided_at TEXT, workspace_id TEXT,
                recommendation TEXT DEFAULT '', impact TEXT DEFAULT '',
                test_plan TEXT DEFAULT '', rollback_plan TEXT DEFAULT '',
                proposed_files TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS development_lifecycles (
                id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, title TEXT NOT NULL,
                stage TEXT NOT NULL, status TEXT NOT NULL,
                gates TEXT DEFAULT '{}', evidence TEXT DEFAULT '[]',
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS library_changes (
                id TEXT PRIMARY KEY, action TEXT NOT NULL, tool_id TEXT NOT NULL,
                name TEXT NOT NULL, description TEXT NOT NULL, reason TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS plan_workspaces (
                id TEXT PRIMARY KEY, plan_id TEXT UNIQUE NOT NULL,
                root TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS external_action_approvals (
                id TEXT PRIMARY KEY, action TEXT NOT NULL, purpose TEXT NOT NULL,
                target TEXT DEFAULT '', actor TEXT DEFAULT 'Atlas',
                payload TEXT DEFAULT '{}', action_hash TEXT DEFAULT '',
                query TEXT DEFAULT '', allowed_domains TEXT DEFAULT '[]',
                status TEXT NOT NULL, created_at TEXT,
                expires_at TEXT DEFAULT '', decided_at TEXT, used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS change_sets (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL, plan_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL,
                files TEXT DEFAULT '[]', combined_diff TEXT DEFAULT '',
                status TEXT NOT NULL, test_result TEXT DEFAULT '{}',
                branch TEXT DEFAULT '', commit_hash TEXT DEFAULT '',
                created_at TEXT, updated_at TEXT, removed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id TEXT NOT NULL, version INTEGER NOT NULL,
                name TEXT NOT NULL, owner_agent TEXT NOT NULL,
                definition TEXT DEFAULT '{}', active INTEGER DEFAULT 1,
                created_at TEXT, PRIMARY KEY (id, version)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
                target TEXT DEFAULT '', outcome TEXT DEFAULT '',
                details TEXT DEFAULT '{}', created_at TEXT,
                previous_hash TEXT DEFAULT '', current_hash TEXT DEFAULT ''
            );
        """)
        self._conn.commit()

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def fetchall(self, sql, params=()):
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def fetchone(self, sql, params=()):
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchval(self, sql, params=()):
        row = self._conn.execute(sql, params).fetchone()
        return row[0] if row else None

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    async def execute_async(self, sql, params=()):
        await asyncio.get_event_loop().run_in_executor(None, lambda: self.execute(sql, params))
        await asyncio.get_event_loop().run_in_executor(None, self.commit)

    async def fetchall_async(self, sql, params=()):
        return await asyncio.get_event_loop().run_in_executor(None, lambda: self.fetchall(sql, params))

    async def fetchone_async(self, sql, params=()):
        return await asyncio.get_event_loop().run_in_executor(None, lambda: self.fetchone(sql, params))

    async def fetchval_async(self, sql, params=()):
        return await asyncio.get_event_loop().run_in_executor(None, lambda: self.fetchval(sql, params))

    async def persist_audit(self, event):
        sql = "INSERT INTO audit_events (id, actor, action, target, outcome, details, created_at, previous_hash, current_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        params = (
            str(event.id),
            event.actor,
            event.action,
            event.target,
            event.outcome,
            json.dumps(event.details),
            event.created_at.isoformat() if hasattr(event.created_at, "isoformat") else str(event.created_at),
            event.previous_hash,
            event.current_hash,
        )
        await self.execute_async(sql, params)


class Infrastructure:
    def __init__(self, database_url: str, redis_url: str):
        self.database_url = database_url
        self.redis_url = redis_url
        self.db = None
        self.sqlite = None
        self.redis = None
        self._backend = "none"

    async def connect(self):
        # --- PostgreSQL ---
        if asyncpg is not None and self.database_url:
            try:
                self.db = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5, timeout=5)
                self._backend = "postgresql"
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
                except Exception:
                    pass
            except Exception as exc:
                logger.warning("PostgreSQL unavailable (%s), trying SQLite", exc)
                self.db = None
        # --- SQLite fallback ---
        if self.db is None:
            db_path = os.getenv("ATLAS_STUDIO_SQLITE_PATH", str(Path("./data/atlas_studio.db").resolve()))
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            try:
                self.sqlite = SQLiteBackend(db_path)
                self.sqlite.connect()
                self._backend = "sqlite"
                logger.info("Using SQLite at %s", db_path)
            except Exception as exc:
                logger.error("SQLite fallback failed (%s)", exc)
                self._backend = "memory"
        # --- Redis ---
        if redis is not None and self.redis_url:
            try:
                self.redis = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=3)
                await self.redis.ping()
            except Exception:
                if self.redis:
                    try:
                        await self.redis.aclose()
                    except Exception:
                        pass
                self.redis = None
        if self.redis is None:
            logger.info("Redis unavailable, using in-memory task queue")

    async def ensure_workflow_schema(self):
        """Apply additive workflow tables to existing persistent volumes.

        Docker init scripts only run for a new PostgreSQL volume. Keeping this
        migration additive lets existing Atlas installations gain LangGraph
        persistence without deleting their local data.
        """
        if not self.db:
            return
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_definitions (
              id text NOT NULL, version integer NOT NULL CHECK (version > 0),
              name text NOT NULL, owner_agent text NOT NULL,
              definition jsonb NOT NULL, active boolean NOT NULL DEFAULT true,
              created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (id, version)
            );
            CREATE TABLE IF NOT EXISTS workflow_runs (
              id uuid PRIMARY KEY, workspace_id uuid REFERENCES workspaces(id) ON DELETE CASCADE,
              task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
              workflow_id text NOT NULL, workflow_version integer NOT NULL,
              status text NOT NULL, risk_tier smallint NOT NULL DEFAULT 0 CHECK (risk_tier BETWEEN 0 AND 3),
              requested_by text NOT NULL DEFAULT 'local-user', state jsonb NOT NULL DEFAULT '{}',
              created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
              FOREIGN KEY (workflow_id, workflow_version) REFERENCES workflow_definitions(id, version)
            );
            CREATE TABLE IF NOT EXISTS workflow_steps (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
              node text NOT NULL, agent_id uuid REFERENCES agents(id) ON DELETE SET NULL,
              attempt integer NOT NULL DEFAULT 1, status text NOT NULL,
              input jsonb NOT NULL DEFAULT '{}', output jsonb NOT NULL DEFAULT '{}',
              started_at timestamptz, completed_at timestamptz
            );
            CREATE TABLE IF NOT EXISTS workflow_approvals (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
              action_hash text NOT NULL, action jsonb NOT NULL,
              decision text CHECK (decision IN ('approved','edited','rejected','expired')),
              decided_by text, reason text, requested_at timestamptz NOT NULL DEFAULT now(),
              decided_at timestamptz, expires_at timestamptz
            );
            CREATE TABLE IF NOT EXISTS workflow_events (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
              sequence bigint NOT NULL, event_type text NOT NULL,
              agent_id uuid REFERENCES agents(id) ON DELETE SET NULL,
              payload jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE (run_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS workflow_runs_updated_idx ON workflow_runs (updated_at DESC);
            CREATE INDEX IF NOT EXISTS workflow_events_run_sequence_idx ON workflow_events (run_id, sequence);
            CREATE INDEX IF NOT EXISTS workflow_approvals_pending_idx ON workflow_approvals (run_id) WHERE decision IS NULL;
            """
        )

    async def ensure_control_plane_schema(self):
        if not self.db:
            return
        await self.db.execute(
            """
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS priority text NOT NULL DEFAULT 'normal';
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_authorized boolean NOT NULL DEFAULT false;
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS attempt integer NOT NULL DEFAULT 0;
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_at timestamptz;
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS duration_ms integer;
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS plan_id uuid;
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_workspace_id uuid;
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS grounding_status text NOT NULL DEFAULT 'pending';
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS grounding_issues jsonb NOT NULL DEFAULT '[]';
            ALTER TABLE tasks ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]';
            CREATE TABLE IF NOT EXISTS plans (
              id uuid PRIMARY KEY, title text NOT NULL, request text NOT NULL,
              implementation_agent_id uuid NOT NULL REFERENCES agents(id), priority text NOT NULL,
              steps jsonb NOT NULL DEFAULT '[]', status text NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now(), decided_at timestamptz
            );
            ALTER TABLE plans ADD COLUMN IF NOT EXISTS workspace_id uuid;
            ALTER TABLE plans ADD COLUMN IF NOT EXISTS recommendation text NOT NULL DEFAULT 'Forge recommends a scoped, reviewable change in an isolated workspace.';
            ALTER TABLE plans ADD COLUMN IF NOT EXISTS impact text NOT NULL DEFAULT 'Review required';
            ALTER TABLE plans ADD COLUMN IF NOT EXISTS test_plan text NOT NULL DEFAULT 'Run repository tests in Test';
            ALTER TABLE plans ADD COLUMN IF NOT EXISTS rollback_plan text NOT NULL DEFAULT 'Retain the reviewed diff and prior file hashes';
            ALTER TABLE plans ADD COLUMN IF NOT EXISTS proposed_files jsonb NOT NULL DEFAULT '[]';
            CREATE TABLE IF NOT EXISTS development_lifecycles (
              id uuid PRIMARY KEY, plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
              title text NOT NULL, stage text NOT NULL, status text NOT NULL,
              gates jsonb NOT NULL DEFAULT '{}', evidence jsonb NOT NULL DEFAULT '[]',
              created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS library_changes (
              id uuid PRIMARY KEY, action text NOT NULL, tool_id text NOT NULL,
              name text NOT NULL, description text NOT NULL, reason text NOT NULL,
              status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS plan_workspaces (
              id uuid PRIMARY KEY, plan_id uuid NOT NULL UNIQUE REFERENCES plans(id) ON DELETE CASCADE,
              root text NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS external_action_approvals (
              id uuid PRIMARY KEY, action text NOT NULL, purpose text NOT NULL,
              target text NOT NULL DEFAULT '', actor text NOT NULL DEFAULT 'Atlas',
              payload jsonb NOT NULL DEFAULT '{}', action_hash text NOT NULL DEFAULT '',
              query text NOT NULL DEFAULT '', allowed_domains jsonb NOT NULL DEFAULT '[]',
              status text NOT NULL, created_at timestamptz NOT NULL,
              expires_at timestamptz NOT NULL, decided_at timestamptz, used_at timestamptz
            );
            ALTER TABLE external_action_approvals DROP CONSTRAINT IF EXISTS external_action_approvals_action_check;
            ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS target text NOT NULL DEFAULT '';
            ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS actor text NOT NULL DEFAULT 'Atlas';
            ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS payload jsonb NOT NULL DEFAULT '{}';
            ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS action_hash text NOT NULL DEFAULT '';
            CREATE TABLE IF NOT EXISTS change_sets (
              id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
              plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
              workspace_id uuid NOT NULL REFERENCES plan_workspaces(id) ON DELETE CASCADE,
              title text NOT NULL, summary text NOT NULL, files jsonb NOT NULL DEFAULT '[]',
              combined_diff text NOT NULL DEFAULT '', status text NOT NULL,
              test_result jsonb NOT NULL DEFAULT '{}', branch text NOT NULL DEFAULT '',
              commit_hash text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(), removed_at timestamptz
            );
            ALTER TABLE change_sets ADD COLUMN IF NOT EXISTS removed_at timestamptz;
            CREATE INDEX IF NOT EXISTS change_sets_plan_updated_idx ON change_sets (plan_id, updated_at DESC);
            """
        )

    async def close(self):
        if self.db:
            await self.db.close()
        if self.sqlite:
            self.sqlite.close()
        if self.redis:
            try:
                await self.redis.aclose()
            except Exception:
                pass

    async def persist_agent(self, agent: Agent):
        if self.db:
            # Early Atlas Studio seeds assigned IDs 003 and 004 to Sage and
            # Echo. The expanded system catalog later assigned those IDs to
            # Sentinel and Verity. Reconcile by the durable workspace/name
            # identity so existing task foreign keys and agent history remain
            # intact, then allocate a deterministic ID for a genuinely new
            # system agent whose preferred ID is already occupied.
            existing_id = await self.db.fetchval(
                "SELECT id FROM agents WHERE workspace_id='00000000-0000-0000-0000-000000000001' AND name=$1",
                agent.name,
            )
            if existing_id:
                agent.id = existing_id
            else:
                occupied_name = await self.db.fetchval("SELECT name FROM agents WHERE id=$1", agent.id)
                if occupied_name and occupied_name != agent.name:
                    agent.id = uuid5(NAMESPACE_URL, f"atlas-studio:system-agent:{agent.name}")
            try:
                await self.db.execute(
                    """INSERT INTO agents (id,workspace_id,name,role,description,tools,read_only,requires_user_authorization,skills)
                    VALUES ($1,'00000000-0000-0000-0000-000000000001',$2,$3,$4,$5::jsonb,$6,$7,$8::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                      name=EXCLUDED.name,role=EXCLUDED.role,description=EXCLUDED.description,
                      tools=EXCLUDED.tools,read_only=EXCLUDED.read_only,
                      requires_user_authorization=EXCLUDED.requires_user_authorization,skills=EXCLUDED.skills""",
                    agent.id, agent.name, agent.role, agent.description,
                    json.dumps(agent.tools), agent.read_only, agent.requires_user_authorization, json.dumps(agent.skills),
                )
            except asyncpg.UndefinedColumnError:
                # Existing installations created before migration 003 continue
                # working until the migration is applied to their database.
                await self.db.execute(
                    """INSERT INTO agents (id,workspace_id,name,role,description,tools,read_only)
                    VALUES ($1,'00000000-0000-0000-0000-000000000001',$2,$3,$4,$5::jsonb,$6)
                    ON CONFLICT (id) DO UPDATE SET
                      name=EXCLUDED.name,role=EXCLUDED.role,description=EXCLUDED.description,
                      tools=EXCLUDED.tools,read_only=EXCLUDED.read_only""",
                    agent.id, agent.name, agent.role, agent.description,
                    json.dumps(agent.tools), agent.read_only,
                )

    async def load_agents(self) -> list[Agent]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch(
                "SELECT id,name,role,description,tools,read_only,requires_user_authorization,skills FROM agents ORDER BY name"
            )
            return [
                Agent(
                    id=row["id"], name=row["name"], role=row["role"],
                    description=row["description"], tools=json.loads(row["tools"]) if isinstance(row["tools"], str) else row["tools"],
                    read_only=row["read_only"],
                    requires_user_authorization=row["requires_user_authorization"],
                    skills=json.loads(row["skills"]) if isinstance(row["skills"], str) else row["skills"],
                )
                for row in rows
            ]
        except asyncpg.UndefinedColumnError:
            rows = await self.db.fetch("SELECT id,name,role,description,tools,read_only FROM agents ORDER BY name")
            return [
                Agent(
                    id=row["id"], name=row["name"], role=row["role"],
                    description=row["description"], tools=json.loads(row["tools"]) if isinstance(row["tools"], str) else row["tools"],
                    read_only=row["read_only"],
                )
                for row in rows
            ]

    async def delete_agent(self, agent_id):
        if self.db:
            await self.db.execute("DELETE FROM agents WHERE id=$1", agent_id)

    async def persist_workflow_definition(self, workflow: WorkflowDefinition):
        if self.db:
            definition = {
                "description": workflow.description, "nodes": workflow.nodes,
                "status": workflow.status, "source_type": workflow.source_type,
                "source_reference": workflow.source_reference,
            }
            await self.db.execute(
                """INSERT INTO workflow_definitions (id,version,name,owner_agent,definition,active,created_at)
                VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7)
                ON CONFLICT (id,version) DO UPDATE SET name=EXCLUDED.name,owner_agent=EXCLUDED.owner_agent,
                definition=EXCLUDED.definition,active=EXCLUDED.active""",
                workflow.id, workflow.version, workflow.name, workflow.owner,
                json.dumps(definition), workflow.active, workflow.created_at,
            )

    async def load_workflow_definitions(self) -> list[WorkflowDefinition]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch("SELECT * FROM workflow_definitions ORDER BY created_at")
        except asyncpg.PostgresError:
            return []
        definitions = []
        for row in rows:
            data = row["definition"] if not isinstance(row["definition"], str) else json.loads(row["definition"])
            definitions.append(WorkflowDefinition(
                id=row["id"], version=row["version"], name=row["name"], owner=row["owner_agent"],
                description=data.get("description", "Imported workflow definition"), nodes=data.get("nodes", []),
                status=data.get("status", "active" if row["active"] else "designed"),
                source_type=data.get("source_type", "manual"), source_reference=data.get("source_reference", ""),
                active=row["active"], created_at=row["created_at"],
            ))
        return definitions

    async def persist_plan(self, plan: Plan):
        if self.db:
            await self.db.execute(
                """INSERT INTO plans (id,title,request,implementation_agent_id,priority,steps,status,created_at,decided_at,workspace_id,recommendation,impact,test_plan,rollback_plan,proposed_files)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                ON CONFLICT (id) DO UPDATE SET request=EXCLUDED.request,priority=EXCLUDED.priority,steps=EXCLUDED.steps,status=EXCLUDED.status,decided_at=EXCLUDED.decided_at,workspace_id=EXCLUDED.workspace_id,recommendation=EXCLUDED.recommendation,impact=EXCLUDED.impact,test_plan=EXCLUDED.test_plan,rollback_plan=EXCLUDED.rollback_plan,proposed_files=EXCLUDED.proposed_files""",
                plan.id, plan.title, plan.request, plan.implementation_agent_id, plan.priority,
                json.dumps(plan.steps), plan.status, plan.created_at, plan.decided_at, plan.workspace_id,
                plan.recommendation, plan.impact, plan.test_plan, plan.rollback_plan, json.dumps(plan.proposed_files),
            )

    async def load_plans(self) -> list[Plan]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch("SELECT * FROM plans ORDER BY created_at")
        except asyncpg.PostgresError:
            return []
        return [Plan(
            id=row["id"], title=row["title"], request=row["request"],
            implementation_agent_id=row["implementation_agent_id"], priority=row["priority"],
            steps=row["steps"] if not isinstance(row["steps"], str) else json.loads(row["steps"]),
            status=row["status"], created_at=row["created_at"], decided_at=row["decided_at"], workspace_id=row["workspace_id"],
            recommendation=row.get("recommendation") or "Forge recommends a scoped, reviewable change in an isolated workspace.",
            impact=row.get("impact") or "Review required",
            test_plan=row.get("test_plan") or "Run repository tests in Test",
            rollback_plan=row.get("rollback_plan") or "Retain the reviewed diff and prior file hashes",
            proposed_files=(row.get("proposed_files") if not isinstance(row.get("proposed_files"), str) else json.loads(row["proposed_files"])) or [],
        ) for row in rows]

    async def persist_plan_workspace(self, workspace: PlanWorkspace):
        if self.db:
            await self.db.execute(
                """INSERT INTO plan_workspaces (id,plan_id,root,status,created_at) VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (id) DO UPDATE SET root=EXCLUDED.root,status=EXCLUDED.status""",
                workspace.id, workspace.plan_id, workspace.root, workspace.status, workspace.created_at,
            )

    async def load_plan_workspaces(self) -> list[PlanWorkspace]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch("SELECT * FROM plan_workspaces ORDER BY created_at")
        except asyncpg.PostgresError:
            return []
        return [PlanWorkspace(**dict(row)) for row in rows]

    async def persist_change_set(self, change_set: ChangeSet):
        if self.db:
            await self.db.execute(
                """INSERT INTO change_sets (id,task_id,plan_id,workspace_id,title,summary,files,combined_diff,status,test_result,branch,commit_hash,created_at,updated_at,removed_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10::jsonb,$11,$12,$13,$14,$15)
                ON CONFLICT (id) DO UPDATE SET files=EXCLUDED.files,combined_diff=EXCLUDED.combined_diff,
                  status=EXCLUDED.status,test_result=EXCLUDED.test_result,branch=EXCLUDED.branch,
                  commit_hash=EXCLUDED.commit_hash,updated_at=EXCLUDED.updated_at,removed_at=EXCLUDED.removed_at""",
                change_set.id, change_set.task_id, change_set.plan_id, change_set.workspace_id,
                change_set.title, change_set.summary,
                json.dumps([item.model_dump(mode="json") for item in change_set.files]),
                change_set.combined_diff, change_set.status, json.dumps(change_set.test_result),
                change_set.branch, change_set.commit, change_set.created_at, change_set.updated_at, change_set.removed_at,
            )

    async def load_change_sets(self) -> list[ChangeSet]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch("SELECT * FROM change_sets ORDER BY updated_at")
        except asyncpg.PostgresError:
            return []
        return [ChangeSet(
            id=row["id"], task_id=row["task_id"], plan_id=row["plan_id"], workspace_id=row["workspace_id"],
            title=row["title"], summary=row["summary"],
            files=row["files"] if not isinstance(row["files"], str) else json.loads(row["files"]),
            combined_diff=row["combined_diff"], status=row["status"],
            test_result=row["test_result"] if not isinstance(row["test_result"], str) else json.loads(row["test_result"]),
            branch=row["branch"], commit=row["commit_hash"], removed_at=row.get("removed_at"), created_at=row["created_at"], updated_at=row["updated_at"],
        ) for row in rows]

    async def persist_lifecycle(self, lifecycle: DevelopmentLifecycle):
        if self.db:
            await self.db.execute(
                """INSERT INTO development_lifecycles (id,plan_id,title,stage,status,gates,evidence,created_at,updated_at)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9)
                ON CONFLICT (id) DO UPDATE SET stage=EXCLUDED.stage,status=EXCLUDED.status,gates=EXCLUDED.gates,evidence=EXCLUDED.evidence,updated_at=EXCLUDED.updated_at""",
                lifecycle.id, lifecycle.plan_id, lifecycle.title, lifecycle.stage, lifecycle.status,
                json.dumps(lifecycle.gates), json.dumps(lifecycle.evidence), lifecycle.created_at, lifecycle.updated_at,
            )

    async def load_lifecycles(self) -> list[DevelopmentLifecycle]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch("SELECT * FROM development_lifecycles ORDER BY created_at")
        except asyncpg.PostgresError:
            return []
        return [DevelopmentLifecycle(
            id=row["id"], plan_id=row["plan_id"], title=row["title"], stage=row["stage"], status=row["status"],
            gates=row["gates"] if not isinstance(row["gates"], str) else json.loads(row["gates"]),
            evidence=row["evidence"] if not isinstance(row["evidence"], str) else json.loads(row["evidence"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        ) for row in rows]

    async def persist_library_change(self, change: LibraryChange):
        if self.db:
            await self.db.execute(
                """INSERT INTO library_changes (id,action,tool_id,name,description,reason,status,created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status""",
                change.id, change.action, change.tool_id, change.name, change.description, change.reason, change.status, change.created_at,
            )

    async def load_library_changes(self) -> list[LibraryChange]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch("SELECT * FROM library_changes ORDER BY created_at")
        except asyncpg.PostgresError:
            return []
        return [LibraryChange(**dict(row)) for row in rows]

    async def persist_external_approval(self, approval: ExternalActionApproval):
        if self.db:
            await self.db.execute(
                """INSERT INTO external_action_approvals (id,action,purpose,target,actor,payload,action_hash,query,allowed_domains,status,created_at,expires_at,decided_at,used_at)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb,$10,$11,$12,$13,$14)
                ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,decided_at=EXCLUDED.decided_at,used_at=EXCLUDED.used_at""",
                approval.id, approval.action, approval.purpose, approval.target, approval.actor, json.dumps(approval.payload),
                approval.action_hash, approval.query, json.dumps(approval.allowed_domains), approval.status,
                approval.created_at, approval.expires_at, approval.decided_at, approval.used_at,
            )

    async def load_external_approvals(self) -> list[ExternalActionApproval]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch("SELECT * FROM external_action_approvals ORDER BY created_at")
        except asyncpg.PostgresError:
            return []
        return [ExternalActionApproval(
            id=row["id"], action=row["action"], purpose=row["purpose"], target=row["target"], actor=row["actor"],
            payload=row["payload"] if not isinstance(row["payload"], str) else json.loads(row["payload"]), action_hash=row["action_hash"], query=row["query"],
            allowed_domains=row["allowed_domains"] if not isinstance(row["allowed_domains"], str) else json.loads(row["allowed_domains"]),
            status=row["status"], created_at=row["created_at"], expires_at=row["expires_at"],
            decided_at=row["decided_at"], used_at=row["used_at"],
        ) for row in rows]

    async def persist_task(self, task: Task):
        if self.db:
            await self.db.execute(
                """INSERT INTO tasks (id,workspace_id,agent_id,title,prompt,model,status,output,created_at,priority,user_authorized,attempt,completed_at,duration_ms,updated_at,plan_id,execution_workspace_id,grounding_status,grounding_issues,evidence_refs)
                VALUES ($1,'00000000-0000-0000-0000-000000000001',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::jsonb,$19::jsonb)
                ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,output=EXCLUDED.output,priority=EXCLUDED.priority,
                  user_authorized=EXCLUDED.user_authorized,attempt=EXCLUDED.attempt,completed_at=EXCLUDED.completed_at,
                  duration_ms=EXCLUDED.duration_ms,updated_at=EXCLUDED.updated_at,plan_id=EXCLUDED.plan_id,
                  execution_workspace_id=EXCLUDED.execution_workspace_id,grounding_status=EXCLUDED.grounding_status,
                  grounding_issues=EXCLUDED.grounding_issues,evidence_refs=EXCLUDED.evidence_refs""",
                task.id, task.agent_id, task.title, task.prompt, task.model, task.status, task.output, task.created_at,
                task.priority, task.user_authorized, task.attempt, task.completed_at, task.duration_ms, task.updated_at,
                task.plan_id, task.workspace_id, task.grounding_status, json.dumps(task.grounding_issues), json.dumps(task.evidence_refs),
            )
        if self.redis:
            await self.redis.setex(f"atlas-studio:task:{task.id}", 86400, task.model_dump_json())

    async def load_tasks(self) -> list[Task]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch(
                """SELECT id,agent_id,title,prompt,model,status,priority,user_authorized,attempt,output,
                created_at,updated_at,completed_at,duration_ms,plan_id,execution_workspace_id,
                grounding_status,grounding_issues,evidence_refs FROM tasks ORDER BY created_at"""
            )
        except asyncpg.PostgresError:
            return []
        return [Task(
            id=row["id"], agent_id=row["agent_id"], title=row["title"], prompt=row["prompt"], model=row["model"],
            status=row["status"], priority=row["priority"], user_authorized=row["user_authorized"], attempt=row["attempt"],
            output=row["output"], created_at=row["created_at"], updated_at=row["updated_at"],
            completed_at=row["completed_at"], duration_ms=row["duration_ms"], plan_id=row["plan_id"], workspace_id=row["execution_workspace_id"],
            grounding_status=row["grounding_status"], grounding_issues=list(row["grounding_issues"] or []), evidence_refs=list(row["evidence_refs"] or []),
        ) for row in rows]

    async def persist_audit(self, event: AuditEvent):
        if self.db:
            await self.db.execute(
                "INSERT INTO audit_events (id,actor,action,target,outcome,details) VALUES ($1,$2,$3,$4,$5,$6::jsonb)",
                event.id, event.actor, event.action, event.target, event.outcome, json.dumps(event.details),
            )

    async def load_audit(self, limit: int = 1000) -> list[AuditEvent]:
        if not self.db:
            return []
        try:
            rows = await self.db.fetch(
                "SELECT id,actor,action,target,outcome,details,created_at FROM audit_events ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        except asyncpg.PostgresError:
            return []
        return [AuditEvent(
            id=row["id"], actor=row["actor"], action=row["action"], target=row["target"], outcome=row["outcome"],
            details=row["details"] if not isinstance(row["details"], str) else json.loads(row["details"]), created_at=row["created_at"],
        ) for row in rows]

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
        if self.redis:
            try:
                if await self.redis.ping():
                    result["redis"] = "ok"
            except Exception:
                pass
        return result
