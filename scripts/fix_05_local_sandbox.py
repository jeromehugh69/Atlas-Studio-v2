#!/usr/bin/env python3
"""
Fix #5: Add local sandbox runtime option
==========================================
Adds "local" as a valid sandbox_runtime option in config.py so the
application can run without Docker/Podman.

Usage: python scripts/fix_05_local_sandbox.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "config.py"


def main():
    print("=" * 50)
    print("Fix #5: Add local sandbox runtime option")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    # Patch sandbox_runtime type and default
    c = c.replace(
        'sandbox_runtime: Literal["docker", "podman"] = "docker"',
        'sandbox_runtime: Literal["docker", "podman", "local"] = "local"'
    )

    # Patch sandbox_network default
    c = c.replace(
        'sandbox_network: str = "none"',
        'sandbox_network: str = "none"  # ignored when sandbox_runtime=local'
    )

    FILE.write_text(c, encoding="utf-8")
    print("  OK:   sandbox_runtime now supports 'local' (default)")
    print()
    print("Code execution runs directly as subprocesses without Docker/Podman.")


if __name__ == "__main__":
    main()
