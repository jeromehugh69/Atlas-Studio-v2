from pathlib import Path

from atlas_studio.skill_runtime import SkillRuntime


def test_skill_runtime_loads_only_assigned_bundled_skills(tmp_path: Path):
    skill = tmp_path / "safe-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: safe-skill\ndescription: Safe\n---\nUse evidence.", encoding="utf-8")
    runtime = SkillRuntime(tmp_path)

    rendered = runtime.render(["safe_skill", "../missing"])

    assert "ASSIGNED SKILL: safe-skill" in rendered
    assert "Use evidence." in rendered
    assert "missing" not in rendered


def test_skill_runtime_reports_available_skill_ids(tmp_path: Path):
    (tmp_path / "one").mkdir()
    (tmp_path / "one" / "SKILL.md").write_text("instructions", encoding="utf-8")
    assert SkillRuntime(tmp_path).available() == {"one"}
