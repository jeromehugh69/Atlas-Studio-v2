#!/usr/bin/env python3
"""
Fix #9: Make heavy dependencies optional in pyproject.toml
===========================================================
Moves gradio and langgraph-checkpoint-postgres to optional dependency groups
so standalone installs are lighter.

Usage: python scripts/fix_09_optional_deps.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "pyproject.toml"


def main():
    print("=" * 50)
    print("Fix #9: Make heavy deps optional")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    if 'portal = ["gradio' in c:
        print("  SKIP: Already patched")
        return

    # Remove heavy deps from main dependencies
    c = c.replace(
        '  "gradio>=5.49,<7",\n',
        ''
    )
    c = c.replace(
        '  "langgraph-checkpoint-postgres>=3,<4",\n',
        ''
    )
    print("  OK:   Removed gradio and langgraph-checkpoint-postgres from core deps")

    # Add optional dependency groups
    c = c.replace(
        '[project.optional-dependencies]\ntest = ["pytest>=8,<9", "pytest-asyncio>=0.24,<1"]',
        '[project.optional-dependencies]\ntest = ["pytest>=8,<9", "pytest-asyncio>=0.24,<1"]\nportal = ["gradio>=5.49,<7"]\npostgres = ["langgraph-checkpoint-postgres>=3,<4"]\nfull = ["gradio>=5.49,<7", "langgraph-checkpoint-postgres>=3,<4"]'
    )
    print("  OK:   Added optional dependency groups: portal, postgres, full")

    FILE.write_text(c, encoding="utf-8")
    print()
    print("Install with: pip install -e '.[portal]'  (if you need Gradio portal)")
    print("Install with: pip install -e '.[postgres]'  (if you need LangGraph persistence)")
    print("Install with: pip install -e '.[full]'  (all features)")


if __name__ == "__main__":
    main()
