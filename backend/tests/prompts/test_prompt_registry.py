from __future__ import annotations

from pathlib import Path

import pytest

from app.prompts.registry import PromptRegistry, PromptRenderError


def test_prompt_registry_renders_yaml_template_with_jinja_variables() -> None:
    rendered = PromptRegistry().render(
        "chat/supervisor",
        {
            "knowledge_context": "",
            "message": "帮我找北京 Java 后端实习",
            "intent": "job_search",
            "steps": ["理解目标岗位", "读取默认简历", "检索岗位"],
            "history_text": "user: 我想做后端",
            "context_text": "resume score=82",
            "response_contract": "必须包含匹配原因和投递建议",
        },
    )

    assert rendered.template_id == "chat/supervisor"
    assert rendered.version
    assert "User question: 帮我找北京 Java 后端实习" in rendered.user
    assert "Plan: 理解目标岗位 -> 读取默认简历 -> 检索岗位" in rendered.user
    assert "Never invent job postings" in rendered.system
    assert "{{" not in rendered.user


def test_prompt_registry_reports_missing_variables() -> None:
    registry = PromptRegistry()

    with pytest.raises(PromptRenderError) as exc_info:
        registry.render("chat/supervisor", {"message": "你好"})

    assert "missing variables" in str(exc_info.value)
    assert "intent" in str(exc_info.value)


def test_all_prompt_templates_load_with_required_metadata() -> None:
    registry = PromptRegistry()
    template_root = Path(__file__).parents[2] / "app" / "prompts" / "templates"

    template_ids = [path.relative_to(template_root).with_suffix("").as_posix() for path in template_root.rglob("*.yaml")]
    assert {"chat/supervisor", "chat/simple_answer", "interview/feedback", "notification/proactive_decision"}.issubset(
        set(template_ids)
    )

    for template_id in template_ids:
        template = registry.load(template_id)
        assert template.id == template_id
        assert template.version
        assert isinstance(template.variables, list)
        assert template.system.strip()
        assert template.user.strip()
