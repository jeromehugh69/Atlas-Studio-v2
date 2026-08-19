from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class DelegationRule:
    """A rule for delegating between skills."""

    trigger: str
    from_skill: str
    to_skill: str
    priority: int = 1


@dataclass
class SkillCapabilities:
    """Capabilities and triggers for a skill."""

    skill_id: str
    triggers: list[str] = field(default_factory=list)
    delegates_to: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    free: bool = True


class DelegationRouter:
    """Handle cross-skill delegation based on user intent and skill capabilities."""

    def __init__(self, registry_path: Path | None = None):
        self.registry_path = registry_path
        self.skills: dict[str, SkillCapabilities] = {}
        self.rules: list[DelegationRule] = []
        self._load_registry()

    def _load_registry(self) -> None:
        """Load skill registry from YAML file."""
        if not self.registry_path or not self.registry_path.exists():
            return

        try:
            content = self.registry_path.read_text(encoding="utf-8")
            registry = yaml.safe_load(content) or {}
        except (OSError, yaml.YAMLError):
            return

        # Load skills
        for skill_id, skill_data in registry.get("skills", {}).items():
            self.skills[skill_id] = SkillCapabilities(
                skill_id=skill_id,
                triggers=skill_data.get("description_triggers", []),
                delegates_to=skill_data.get("delegates_to", []),
                agents=skill_data.get("agents", []),
                free=skill_data.get("free", True),
            )

        # Load delegation rules
        for rule_data in registry.get("delegation_rules", []):
            self.rules.append(
                DelegationRule(
                    trigger=rule_data.get("trigger", ""),
                    from_skill=rule_data.get("from", ""),
                    to_skill=rule_data.get("to", ""),
                    priority=rule_data.get("priority", 1),
                )
            )

    def match_skill(self, user_input: str) -> Optional[str]:
        """Match user input to the most appropriate skill."""
        user_input_lower = user_input.lower()
        best_match: Optional[str] = None
        best_score = 0

        for skill_id, capabilities in self.skills.items():
            score = 0
            for trigger in capabilities.triggers:
                if trigger.lower() in user_input_lower:
                    # Score based on trigger length (more specific = higher score)
                    score += len(trigger.split())

            if score > best_score:
                best_score = score
                best_match = skill_id

        return best_match if best_score > 0 else None

    def should_delegate(
        self, current_skill: str, user_input: str
    ) -> Optional[str]:
        """Determine if the current skill should delegate to another skill."""
        # Check if user input matches a different skill better
        matched_skill = self.match_skill(user_input)
        if matched_skill and matched_skill != current_skill:
            return matched_skill

        # Check delegation rules
        for rule in self.rules:
            if rule.from_skill == current_skill:
                if rule.trigger.lower() in user_input.lower():
                    return rule.to_skill

        return None

    def get_delegation_target(
        self, current_skill: str, user_input: str
    ) -> Optional[str]:
        """Get the delegation target for a request."""
        return self.should_delegate(current_skill, user_input)

    def get_skill_triggers(self, skill_id: str) -> list[str]:
        """Get the trigger phrases for a skill."""
        if skill_id in self.skills:
            return self.skills[skill_id].triggers
        return []

    def get_skill_delegates_to(self, skill_id: str) -> list[str]:
        """Get the skills that a skill can delegate to."""
        if skill_id in self.skills:
            return self.skills[skill_id].delegates_to
        return []

    def can_use_local_models(self, skill_id: str) -> bool:
        """Check if a skill can use local models only (no API keys)."""
        if skill_id in self.skills:
            return self.skills[skill_id].free
        return False

    def get_all_skills(self) -> list[str]:
        """Get list of all available skill IDs."""
        return list(self.skills.keys())

    def get_skill_agents(self, skill_id: str) -> list[str]:
        """Get the agents that can use a skill."""
        if skill_id in self.skills:
            return self.skills[skill_id].agents
        return []

    def format_delegation_response(
        self,
        original_request: str,
        current_skill: str,
        target_skill: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Format a delegation response."""
        return {
            "delegation": {
                "from_skill": current_skill,
                "to_skill": target_skill,
                "reason": reason,
                "original_request": original_request,
                "context": context or {},
            },
            "request": original_request,
            "interpretation": f"Delegating to {target_skill} because: {reason}",
            "action_taken": f"Delegated to {target_skill}",
            "verification": "Delegation recorded in audit trail",
        }
