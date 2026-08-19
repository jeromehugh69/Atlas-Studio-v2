#!/usr/bin/env python3
"""
Fix #13: Add startup warnings for missing services
=====================================================
Adds logging during the lifespan startup so users can see which services
are unavailable and what fallback mode is active.

Usage: python scripts/fix_13_startup_warnings.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "main.py"


def main():
    print("=" * 50)
    print("Fix #13: Startup warnings for missing services")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    if "_standalone_warnings" in c:
        print("  SKIP: Already patched")
        return

    # Insert warning block before the seeded_agents line in lifespan()
    old = "    seeded_agents = list(store.agents.values())"
    new = """\
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

    seeded_agents = list(store.agents.values())"""

    if old not in c:
        print("  WARN: seeded_agents line not found in lifespan()")
        return

    c = c.replace(old, new, 1)
    FILE.write_text(c, encoding="utf-8")
    print("  OK:   Startup warnings added to lifespan()")


if __name__ == "__main__":
    main()
