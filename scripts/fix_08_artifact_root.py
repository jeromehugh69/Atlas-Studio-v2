#!/usr/bin/env python3
"""
Fix #8: Fix artifact root default path
========================================
Changes artifact_root from Docker volume path to local relative path.

Usage: python scripts/fix_08_artifact_root.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "config.py"


def main():
    print("=" * 50)
    print("Fix #8: Fix artifact root path")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    # The config.py default is already ./data/artifacts which is fine.
    # The .env.example overrides it to /var/lib/atlas-studio/artifacts (Docker-only).
    # Fix the .env.example file:
    env_ex = ROOT / ".env.example"
    if env_ex.exists():
        ec = env_ex.read_text(encoding="utf-8")
        ec = ec.replace(
            "ATLAS_STUDIO_ARTIFACT_ROOT=/var/lib/atlas-studio/artifacts",
            "ATLAS_STUDIO_ARTIFACT_ROOT=./data/artifacts"
        )
        ec = ec.replace(
            "ATLAS_STUDIO_WORKSPACE_ROOT=/workspace",
            "ATLAS_STUDIO_WORKSPACE_ROOT=."
        )
        env_ex.write_text(ec, encoding="utf-8")
        print("  OK:   Fixed .env.example artifact and workspace paths")

    # Also fix .env if it exists
    env = ROOT / ".env"
    if env.exists():
        ec = env.read_text(encoding="utf-8")
        ec = ec.replace(
            "ATLAS_STUDIO_ARTIFACT_ROOT=/var/lib/atlas-studio/artifacts",
            "ATLAS_STUDIO_ARTIFACT_ROOT=./data/artifacts"
        )
        ec = ec.replace(
            "ATLAS_STUDIO_WORKSPACE_ROOT=/workspace",
            "ATLAS_STUDIO_WORKSPACE_ROOT=."
        )
        env.write_text(ec, encoding="utf-8")
        print("  OK:   Fixed .env artifact and workspace paths")
    else:
        print("  SKIP: .env not found (use fix_06 to create .env.standalone)")

    print()
    print("Artifact root: ./data/artifacts")
    print("Workspace root: . (current directory)")


if __name__ == "__main__":
    main()
