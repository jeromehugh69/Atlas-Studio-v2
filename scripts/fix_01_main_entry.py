#!/usr/bin/env python3
"""
Fix #1: Create __main__.py entry point
=======================================
Allows running Atlas Studio with: python -m atlas_studio

Usage: python scripts/fix_01_main_entry.py
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "atlas_studio" / "__main__.py"

CONTENT = '''\
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
'''


def main():
    print("=" * 50)
    print("Fix #1: Create __main__.py entry point")
    print("=" * 50)

    if TARGET.exists():
        print(f"  SKIP: {TARGET.name} already exists")
        return

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(CONTENT, encoding="utf-8")
    print(f"  OK:   Created {TARGET.relative_to(ROOT)}")
    print()
    print("You can now run: python -m atlas_studio")


if __name__ == "__main__":
    main()
