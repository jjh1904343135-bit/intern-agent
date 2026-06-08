from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def _find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        skills_dir = parent / "skills"
        if skills_dir.is_dir() and any(skills_dir.glob("*/SKILL.md")) and ((parent / "docker-compose.yml").exists() or (parent / "app").is_dir()):
            return parent
    raise AssertionError("Could not find project root containing skills/")


PROJECT_ROOT = _find_project_root()
SKILLS_ROOT = PROJECT_ROOT / "skills"

EXPECTED_SKILLS = {
    "agent-evaluation-tool": ["run_agent_eval.py"],
    "application-list-tool": ["list_applications.py"],
    "assistant-memory-tool": ["inspect_memory.py", "export_memory_md.py"],
    "backend-service-tool": ["list_routes.py"],
    "chat-routing-tool": ["plan_turn.py"],
    "frontend-ui-tool": [],
    "interview-state-tool": ["inspect_interview_state.py"],
    "job-search-tool": ["discover_jobs.py"],
    "knowledge-search-tool": ["search_knowledge.py"],
    "llm-provider-tool": ["check_provider.py"],
    "resume-profile-tool": ["inspect_resume_profile.py"],
    "runtime-ops-tool": [],
    "scheduled-task-tool": [],
    "telegram-notification-tool": [],
}

REQUIRED_SECTIONS = [
    "## Tool Contract",
    "## Script Usage",
    "## Output Contract",
    "## Answer Synthesis",
    "## Validation",
]


def _skill_files() -> dict[str, Path]:
    return {
        path.parent.name: path
        for path in SKILLS_ROOT.glob("*/SKILL.md")
    }


def _frontmatter(markdown: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", markdown, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        values[key.strip()] = value.strip()
    return values


def _run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )


def test_replaces_domain_skills_with_tool_skills() -> None:
    assert set(_skill_files()) == set(EXPECTED_SKILLS)


def test_each_tool_skill_has_required_contract_sections() -> None:
    for skill_name, skill_file in _skill_files().items():
        markdown = skill_file.read_text(encoding="utf-8")
        metadata = _frontmatter(markdown)

        assert metadata["name"] == skill_name
        assert metadata["description"].startswith("Use when")
        assert re.fullmatch(r"[a-z0-9-]+", metadata["name"])
        for section in REQUIRED_SECTIONS:
            assert section in markdown, f"{skill_name} missing {section}"

        script_names = EXPECTED_SKILLS[skill_name]
        if not script_names:
            assert "This skill has no application-data Python script" in markdown
            continue

        for script_name in script_names:
            script_path = SKILLS_ROOT / skill_name / "scripts" / script_name
            assert script_path.exists(), f"{skill_name} missing {script_path}"
            assert f"scripts/{script_name}" in markdown
        assert "docker compose exec api python" in markdown


def test_tool_scripts_expose_help() -> None:
    for skill_name, script_names in EXPECTED_SKILLS.items():
        if not script_names:
            continue
        for script_name in script_names:
            script_path = SKILLS_ROOT / skill_name / "scripts" / script_name
            result = _run_script(script_path, "--help")
            assert result.returncode == 0, result.stderr
            assert "usage:" in result.stdout.lower()


def test_tool_scripts_emit_compact_json_for_self_test() -> None:
    for skill_name, script_names in EXPECTED_SKILLS.items():
        if not script_names:
            continue
        for script_name in script_names:
            script_path = SKILLS_ROOT / skill_name / "scripts" / script_name
            result = _run_script(script_path, "--self-test")
            assert result.returncode == 0, result.stderr
            payload = json.loads(result.stdout)
            assert payload["ok"] is True
            assert payload["tool"] == skill_name
            assert isinstance(payload["result"], dict)
