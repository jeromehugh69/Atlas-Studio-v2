#!/usr/bin/env python3
"""
Fix #15: Create SQLite migration helper
=========================================
Provides a standalone script to initialize the SQLite database schema
outside of the application lifecycle, useful for first-time setup or
manual recovery.

Usage: python scripts/fix_15_sqlite_migrations.py
"""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "data"
DB_PATH = DB_DIR / "atlas_studio.db"

SCHEMA = """\
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
    description TEXT NOT NULL, tools TEXT NOT NULL DEFAULT '[]',
    read_only INTEGER NOT NULL DEFAULT 0,
    requires_user_authorization INTEGER NOT NULL DEFAULT 0,
    skills TEXT NOT NULL DEFAULT '["development_lifecycle"]'
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
"""


def main():
    print("=" * 50)
    print("Fix #15: SQLite migration helper")
    print("=" * 50)

    DB_DIR.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        size_kb = DB_PATH.stat().st_size / 1024
        print(f"  INFO: Database exists at {DB_PATH} ({size_kb:.1f} KB)")
        resp = input("  Rebuild schema? Tables are preserved. (y/N): ").strip().lower()
        if resp != "y":
            print("  Aborted.")
            return

    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()

    # Verify tables
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    conn.close()

    print(f"  OK:   Schema initialized at {DB_PATH}")
    print(f"  Tables: {', '.join(tables)}")


if __name__ == "__main__":
    main()
