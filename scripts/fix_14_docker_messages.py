#!/usr/bin/env python3
"""
Fix #14: Fix Docker-specific error messages
=============================================
Replaces Docker Compose command references in error messages with
standalone-friendly instructions.

Usage: python scripts/fix_14_docker_messages.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "providers.py"


def main():
    print("=" * 50)
    print("Fix #14: Fix Docker error messages")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    # Already handled by fix_12, but check anyway
    docker_msg = "docker compose exec ollama ollama pull"
    if docker_msg not in c:
        print("  SKIP: Docker error messages already fixed (or not found)")
        return

    c = c.replace(
        f"Run: docker compose exec ollama ollama pull {{model}}",
        f"Pull it with: ollama pull {{model}}"
    )
    FILE.write_text(c, encoding="utf-8")
    print("  OK:   Docker Compose command references removed")


if __name__ == "__main__":
    main()
