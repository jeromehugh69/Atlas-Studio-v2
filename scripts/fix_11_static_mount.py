#!/usr/bin/env python3
"""
Fix #11: Add safety check for static directory mounting
=========================================================
Prevents the app from crashing at startup if the static/ directory
is missing (e.g. when installed as a wheel without bundled assets).

Usage: python scripts/fix_11_static_mount.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "main.py"


def main():
    print("=" * 50)
    print("Fix #11: Static directory safety check")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    old = 'app.mount("/static", StaticFiles(directory=STATIC), name="static")'
    new = 'if STATIC.is_dir():\n    app.mount("/static", StaticFiles(directory=STATIC), name="static")'

    if old not in c:
        if "if STATIC.is_dir()" in c:
            print("  SKIP: Already patched")
        else:
            print("  WARN: static mount line not found")
        return

    c = c.replace(old, new, 1)
    FILE.write_text(c, encoding="utf-8")
    print("  OK:   Static directory now checked before mounting")


if __name__ == "__main__":
    main()
