#!/usr/bin/env python3
"""
Fix #2: Add SQLite persistence fallback to infrastructure.py
=============================================================
When PostgreSQL is unavailable, Atlas Studio will use a local SQLite
database instead of silently losing all data.

Usage: python scripts/fix_02_sqlite_fallback.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "infrastructure.py"

SQLITE_BACKEND = '''\


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
                skills TEXT NOT NULL DEFAULT '[\\"\\"development_lifecycle\\"\\" \\"]'
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
                details TEXT DEFAULT '{}', created_at TEXT
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
'''


def read_file():
    return FILE.read_text(encoding="utf-8")


def write_file(content):
    FILE.write_text(content, encoding="utf-8")


def replace_once(content, old, new, label):
    if old not in content:
        print(f"  WARN: {label} - pattern not found")
        return content
    result = content.replace(old, new, 1)
    print(f"  OK:   {label}")
    return result


def main():
    print("=" * 50)
    print("Fix #2: SQLite persistence fallback")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = read_file()

    if "SQLiteBackend" in c:
        print("  SKIP: Already patched")
        return

    # 1. Replace imports
    c = replace_once(c,
        "import json\nfrom uuid import NAMESPACE_URL, uuid5\n\nimport asyncpg\nimport redis.asyncio as redis\nfrom redis.exceptions import RedisError",
        "import asyncio\nimport json\nimport logging\nimport os\nimport sqlite3\nfrom uuid import NAMESPACE_URL, uuid5\n\ntry:\n    import asyncpg\nexcept ImportError:\n    asyncpg = None\n\ntry:\n    import redis.asyncio as redis\n    from redis.exceptions import RedisError\nexcept ImportError:\n    redis = None\n    RedisError = OSError\n\nlogger = logging.getLogger(\"atlas_studio.infrastructure\")",
        "Update imports"
    )

    # 2. Add SQLiteBackend class before Infrastructure
    c = replace_once(c,
        "\nclass Infrastructure:",
        SQLITE_BACKEND + "\n\nclass Infrastructure:",
        "Insert SQLiteBackend class"
    )

    # 3. Update Infrastructure.__init__
    c = replace_once(c,
        "class Infrastructure:\n    def __init__(self, database_url: str, redis_url: str):\n        self.database_url = database_url\n        self.redis_url = redis_url\n        self.db: asyncpg.Pool | None = None\n        self.redis: redis.Redis | None = None",
        "class Infrastructure:\n    def __init__(self, database_url: str, redis_url: str):\n        self.database_url = database_url\n        self.redis_url = redis_url\n        self.db = None\n        self.sqlite = None\n        self.redis = None\n        self._backend = \"none\"",
        "Update __init__"
    )

    # 4. Replace connect() method
    c = replace_once(c,
        "    async def connect(self):\n        try:\n            self.db = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5, timeout=5)\n            try:\n                await self.db.execute(\n                    \"ALTER TABLE agents ADD COLUMN IF NOT EXISTS \"\n                    \"requires_user_authorization boolean NOT NULL DEFAULT false\"\n                )\n                await self.db.execute(\n                    \"ALTER TABLE agents ADD COLUMN IF NOT EXISTS skills jsonb NOT NULL DEFAULT '[\\\\\"development_lifecycle\\\\\"]'::jsonb\"\n                )\n                await self.ensure_workflow_schema()\n                await self.ensure_control_plane_schema()\n            except asyncpg.PostgresError:\n                pass\n        except (OSError, asyncpg.PostgresError):\n            self.db = None\n        try:\n            self.redis = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=3)\n            await self.redis.ping()\n        except (OSError, RedisError):\n            if self.redis:\n                await self.redis.aclose()\n            self.redis = None",
        "    async def connect(self):\n        if asyncpg is not None:\n            try:\n                self.db = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5, timeout=5)\n                self._backend = \"postgresql\"\n                try:\n                    await self.db.execute(\n                        \"ALTER TABLE agents ADD COLUMN IF NOT EXISTS \"\n                        \"requires_user_authorization boolean NOT NULL DEFAULT false\"\n                    )\n                    await self.db.execute(\n                        \"ALTER TABLE agents ADD COLUMN IF NOT EXISTS skills jsonb NOT NULL DEFAULT '[\\\\\"development_lifecycle\\\\\"]'::jsonb\"\n                    )\n                    await self.ensure_workflow_schema()\n                    await self.ensure_control_plane_schema()\n                except Exception:\n                    pass\n            except Exception as exc:\n                logger.warning(\"PostgreSQL unavailable (%s), trying SQLite\", exc)\n                self.db = None\n        if self.db is None:\n            db_path = os.getenv(\"ATLAS_STUDIO_SQLITE_PATH\", str(Path(\"./data/atlas_studio.db\").resolve()))\n            Path(db_path).parent.mkdir(parents=True, exist_ok=True)\n            try:\n                self.sqlite = SQLiteBackend(db_path)\n                self.sqlite.connect()\n                self._backend = \"sqlite\"\n                logger.info(\"Using SQLite at %s\", db_path)\n            except Exception as exc:\n                logger.error(\"SQLite fallback failed (%s)\", exc)\n                self._backend = \"memory\"\n        if redis is not None:\n            try:\n                self.redis = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=3)\n                await self.redis.ping()\n            except Exception:\n                if self.redis:\n                    try:\n                        await self.redis.aclose()\n                    except Exception:\n                        pass\n                self.redis = None\n        if self.redis is None:\n            logger.info(\"Redis unavailable, using in-memory task queue\")",
        "Replace connect() with SQLite fallback"
    )

    # 5. Update close()
    c = replace_once(c,
        "    async def close(self):\n        if self.db:\n            await self.db.close()\n        if self.redis:\n            await self.redis.aclose()",
        "    async def close(self):\n        if self.db:\n            await self.db.close()\n        if self.sqlite:\n            self.sqlite.close()\n        if self.redis:\n            try:\n                await self.redis.aclose()\n            except Exception:\n                pass",
        "Update close()"
    )

    # 6. Update health()
    c = replace_once(c,
        "    async def health(self) -> dict[str, str]:\n        result = {\"postgres\": \"unavailable\", \"redis\": \"unavailable\"}\n        if self.db:\n            try:\n                await self.db.fetchval(\"SELECT 1\")\n                result[\"postgres\"] = \"ok\"\n            except asyncpg.PostgresError:\n                pass\n        if self.redis:\n            try:\n                if await self.redis.ping():\n                    result[\"redis\"] = \"ok\"\n            except RedisError:\n                pass\n        return result",
        "    async def health(self) -> dict[str, str]:\n        result = {\"backend\": self._backend, \"redis\": \"unavailable\"}\n        if self.db:\n            try:\n                await self.db.fetchval(\"SELECT 1\")\n                result[\"postgres\"] = \"ok\"\n            except Exception:\n                result[\"postgres\"] = \"unavailable\"\n        elif self.sqlite:\n            result[\"sqlite\"] = \"ok\"\n        if self.redis:\n            try:\n                if await self.redis.ping():\n                    result[\"redis\"] = \"ok\"\n            except Exception:\n                pass\n        return result",
        "Update health()"
    )

    write_file(c)
    print()
    print("SQLite fallback installed.")
    print("Data persists to ./data/atlas_studio.db when PostgreSQL is unavailable.")


if __name__ == "__main__":
    main()
