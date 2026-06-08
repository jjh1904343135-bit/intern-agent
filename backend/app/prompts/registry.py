from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined


class PromptRenderError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    id: str
    version: str
    system: str
    user: str
    variables: list[str]
    output_contract: str
    safety_notes: str
    source_path: Path


@dataclass(frozen=True)
class RenderedPrompt:
    template_id: str
    version: str
    system: str
    user: str
    output_contract: str
    safety_notes: str


class PromptRegistry:
    """集中加载和渲染 Agent Prompt，避免 Prompt 散落在业务 service 中。"""

    def __init__(self, template_root: Path | None = None) -> None:
        self.template_root = template_root or Path(__file__).resolve().parent / "templates"
        # StrictUndefined 让缺失变量直接报错，避免 Prompt 悄悄带着空上下文运行。
        self._env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)

    @lru_cache(maxsize=128)
    def load(self, template_id: str) -> PromptTemplate:
        normalized = template_id.strip().replace("\\", "/").removesuffix(".yaml")
        path = (self.template_root / f"{normalized}.yaml").resolve()
        # 模板 id 只能解析到 templates 目录内，防止通过路径穿越读取任意文件。
        if not str(path).startswith(str(self.template_root.resolve())):
            raise PromptRenderError(f"invalid prompt template id: {template_id}")
        if not path.exists():
            raise PromptRenderError(f"prompt template not found: {template_id}")

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        variables = [str(item) for item in list(payload.get("variables") or [])]
        return PromptTemplate(
            id=str(payload.get("id") or normalized),
            version=str(payload.get("version") or "v1"),
            system=str(payload.get("system") or ""),
            user=str(payload.get("user") or ""),
            variables=variables,
            output_contract=str(payload.get("output_contract") or ""),
            safety_notes=str(payload.get("safety_notes") or ""),
            source_path=path,
        )

    def render(self, template_id: str, variables: dict[str, Any]) -> RenderedPrompt:
        template = self.load(template_id)
        missing = [name for name in template.variables if name not in variables]
        if missing:
            raise PromptRenderError(f"prompt {template_id} missing variables: {', '.join(missing)}")

        try:
            system = self._env.from_string(template.system).render(**variables)
            user = self._env.from_string(template.user).render(**variables)
        except Exception as exc:  # pragma: no cover - Jinja gives detailed subclasses.
            raise PromptRenderError(f"failed to render prompt {template_id}: {exc}") from exc

        return RenderedPrompt(
            template_id=template.id,
            version=template.version,
            system=system.strip(),
            user=user.strip(),
            output_contract=template.output_contract.strip(),
            safety_notes=template.safety_notes.strip(),
        )
