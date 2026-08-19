#!/usr/bin/env python3
"""
Fix #10: Fix skills directory resolution
==========================================
Patches main.py so the skills directory is resolved from multiple candidate
paths instead of only CWD. This prevents silent skill loss when running from
a different working directory.

Usage: python scripts/fix_10_skills_path.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src" / "atlas_studio" / "main.py"


def main():
    print("=" * 50)
    print("Fix #10: Fix skills directory resolution")
    print("=" * 50)

    if not FILE.exists():
        print(f"  FAIL: {FILE} not found")
        sys.exit(1)

    c = FILE.read_text(encoding="utf-8")

    old = 'skill_runtime = SkillRuntime(Path.cwd() / "skills")'
    new = (
        "# Resolve skills: package directory > repo root > CWD\n"
        "_skills_dirs = [\n"
        '    Path(__file__).resolve().parent.parent.parent / "skills",\n'
        '    Path.cwd() / "skills",\n'
        ']\n'
        "_skill_root = next((p for p in _skills_dirs if p.is_dir()), _skills_dirs[1])\n"
        "skill_runtime = SkillRuntime(_skill_root)"
    )

    if old not in c:
        if "skill_runtime = SkillRuntime(" in c:
            print("  WARN: skill_runtime line already modified, skipping")
        else:
            print("  FAIL: skill_runtime initialization not found")
        return

    c = c.replace(old, new, 1)
    FILE.write_text(c, encoding="utf-8")
    print("  OK:   Skills directory now resolves from package, repo root, then CWD")
    print()
    print("Candidate paths checked:")
    print("  1. <package_parent>/skills/  (repo root)")
    print("  2. <CWD>/skills/")


if __name__ == "__main__":
    main()
