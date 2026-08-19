from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class SkillRuntime:
    """Load skills with progressive disclosure (3-tier loading)."""

    def __init__(self, root: Path, max_characters: int = 16_000):
        self.root = root.resolve()
        self.max_characters = max_characters
        self._cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def normalize(skill_id: str) -> str:
        return re.sub(r"[^a-z0-9-]", "", skill_id.strip().casefold().replace("_", "-"))

    def available(self) -> set[str]:
        if not self.root.is_dir():
            return set()
        return {path.parent.name for path in self.root.glob("*/SKILL.md")}

    def _parse_yaml_frontmatter(self, text: str) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter from SKILL.md and return (metadata, body)."""
        if not text.startswith("---"):
            return {}, text

        try:
            end_index = text.index("---", 3)
        except ValueError:
            return {}, text

        yaml_content = text[3:end_index].strip()
        body = text[end_index + 3:].strip()

        try:
            metadata = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError:
            metadata = {}

        return metadata, body

    def _extract_tier1_summary(self, body: str, max_words: int = 500) -> str:
        """Extract first ~500 words from SKILL.md body as Tier 1 summary."""
        words = body.split()
        if len(words) <= max_words:
            return body
        return " ".join(words[:max_words]) + "..."

    def _load_skill(self, skill_id: str) -> dict[str, Any]:
        """Load and cache a skill's metadata and content."""
        if skill_id in self._cache:
            return self._cache[skill_id]

        skill_path = self.root / skill_id / "SKILL.md"
        if not skill_path.exists():
            return {}

        try:
            text = skill_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return {}

        metadata, body = self._parse_yaml_frontmatter(text)

        skill_data = {
            "id": skill_id,
            "metadata": metadata,
            "body": body,
            "tier1_summary": self._extract_tier1_summary(body),
            "references": self._load_references(skill_id),
        }

        self._cache[skill_id] = skill_data
        return skill_data

    def _load_references(self, skill_id: str) -> dict[str, str]:
        """Load all reference files for a skill."""
        references = {}
        refs_dir = self.root / skill_id / "references"
        if not refs_dir.is_dir():
            return references

        for ref_path in refs_dir.glob("*.md"):
            try:
                content = ref_path.read_text(encoding="utf-8", errors="replace").strip()
                references[ref_path.stem] = content
            except OSError:
                continue

        return references

    def render_tier1(self, skill_ids: list[str]) -> str:
        """Render Tier 1 (always-loaded summary) for specified skills."""
        sections: list[str] = []
        remaining = self.max_characters

        for raw_id in dict.fromkeys(skill_ids):
            skill_id = self.normalize(raw_id)
            if not skill_id or skill_id not in self.available():
                continue

            skill_data = self._load_skill(skill_id)
            if not skill_data:
                continue

            header = f"\n\nASSIGNED SKILL: {skill_id}\n"
            summary = skill_data["tier1_summary"]
            block = header + summary[: max(0, remaining - len(header))]
            sections.append(block)
            remaining -= len(block)

            if remaining <= 0:
                break

        return "".join(sections)

    def render_tier2(self, skill_ids: list[str]) -> str:
        """Render Tier 2 (full SKILL.md body) for specified skills."""
        sections: list[str] = []
        remaining = self.max_characters

        for raw_id in dict.fromkeys(skill_ids):
            skill_id = self.normalize(raw_id)
            if not skill_id or skill_id not in self.available():
                continue

            skill_data = self._load_skill(skill_id)
            if not skill_data:
                continue

            header = f"\n\nASSIGNED SKILL: {skill_id}\n"
            body = skill_data["body"]
            block = header + body[: max(0, remaining - len(header))]
            sections.append(block)
            remaining -= len(block)

            if remaining <= 0:
                break

        return "".join(sections)

    def render_tier3(self, skill_id: str, reference_name: str) -> str:
        """Render Tier 3 (reference file) for a specific skill."""
        skill_id = self.normalize(skill_id)
        if not skill_id or skill_id not in self.available():
            return ""

        skill_data = self._load_skill(skill_id)
        if not skill_data:
            return ""

        references = skill_data.get("references", {})
        return references.get(reference_name, "")

    def render(self, skill_ids: list[str], tier: int = 2) -> str:
        """Render skill content at the specified tier level.

        Tier 1: Always-loaded summary (~500 words)
        Tier 2: Full SKILL.md body (on-demand)
        Tier 3: Reference files (just-in-time, use render_tier3 instead)
        """
        if tier == 1:
            return self.render_tier1(skill_ids)
        return self.render_tier2(skill_ids)

    def get_skill_info(self, skill_id: str) -> dict[str, Any]:
        """Get metadata about a skill without loading full content."""
        skill_id = self.normalize(skill_id)
        if skill_id not in self.available():
            return {}

        skill_data = self._load_skill(skill_id)
        return {
            "id": skill_id,
            "metadata": skill_data.get("metadata", {}),
            "has_references": bool(skill_data.get("references")),
            "reference_names": list(skill_data.get("references", {}).keys()),
        }

    def list_skills(self) -> list[dict[str, Any]]:
        """List all available skills with basic metadata."""
        skills = []
        for skill_id in sorted(self.available()):
            info = self.get_skill_info(skill_id)
            if info:
                skills.append(info)
        return skills
