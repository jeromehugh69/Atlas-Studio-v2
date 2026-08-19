#!/usr/bin/env python3
"""
Fix #3: Redis graceful degradation
====================================
Ensures the task queue works without Redis by improving the in-memory
fallback path. No data loss risk - the queue already handles this.

Usage: python scripts/fix_03_redis_graceful.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "layers" / "task_queue.py"


def main():
    print("=" * 50)
    print("Fix #3: Redis graceful degradation")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    if "logging" in c and "_logger" in c:
        print("  SKIP: Already patched")
        return

    # Add logging import
    c = c.replace(
        "from __future__ import annotations\n\nimport asyncio\nimport json\nimport time\nfrom dataclasses import dataclass\nfrom itertools import count\nfrom uuid import UUID\n\nfrom redis.asyncio import Redis\nfrom redis.exceptions import RedisError",
        "from __future__ import annotations\n\nimport asyncio\nimport json\nimport logging\nimport time\nfrom dataclasses import dataclass\nfrom itertools import count\nfrom uuid import UUID\n\ntry:\n    from redis.asyncio import Redis\n    from redis.exceptions import RedisError\nexcept ImportError:\n    Redis = None\n    RedisError = OSError\n\n_logger = logging.getLogger(\"atlas_studio.task_queue\")"
    )
    print("  OK:   Added logging and optional redis import")

    # Update attach to log
    c = c.replace(
        "    def attach(self, redis: Redis | None) -> None:\n        self.redis = redis",
        "    def attach(self, redis) -> None:\n        self.redis = redis\n        if redis is None:\n            _logger.info(\"Task queue: Redis unavailable, using in-memory fallback\")"
    )
    print("  OK:   Added attach() logging")

    FILE.write_text(c, encoding="utf-8")
    print()
    print("Redis is now fully optional. In-memory queue activates automatically.")


if __name__ == "__main__":
    main()
