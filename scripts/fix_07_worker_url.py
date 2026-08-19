#!/usr/bin/env python3
"""
Fix #7: Change worker URL default to localhost
===============================================
Changes config.py default worker_url from Docker service name to localhost.

Usage: python scripts/fix_07_worker_url.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "config.py"


def main():
    print("=" * 50)
    print("Fix #7: Fix worker URL default")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    changes = [
        ('worker_url: str = "http://worker:8092"',
         'worker_url: str = "http://localhost:8092"',
         "worker_url -> localhost"),
        ('research_worker_url: str = "http://research-worker:8093"',
         'research_worker_url: str = "http://localhost:8093"',
         "research_worker_url -> localhost"),
        ('avatar_service_url: str = "http://avatar3d:8090"',
         'avatar_service_url: str = "http://localhost:8090"',
         "avatar_service_url -> localhost"),
    ]

    for old, new, label in changes:
        if old in c:
            c = c.replace(old, new, 1)
            print(f"  OK:   {label}")
        else:
            print(f"  WARN: {label} - not found")

    FILE.write_text(c, encoding="utf-8")


if __name__ == "__main__":
    main()
