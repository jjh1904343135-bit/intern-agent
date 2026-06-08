from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.agents.resume import ResumeParserAgent, ResumeScoringAgent
from app.agents.runtime import AgentContext, AgentRunner
from app.core.providers.claude_provider import ClaudeProviderError
from app.core.providers.factory import get_provider
from app.core.settings import settings
from app.prompts import PromptRegistry
from app.repositories.resume_repository import ResumeRepository
from app.tools.parsers.pdf_parser import extract_resume_text, parse_resume_text
from app.utils.llm_json import LLMJsonError, extract_json_object


@dataclass
class ResumeServiceError(Exception):
    status_code: int
    code: int
    message: str


class ResumeService:
    ALLOWED_EXTENSIONS = {".pdf", ".docx"}
    MAX_FILE_SIZE = 10 * 1024 * 1024
    RUBRIC_VERSION = "resume_score_v1"
    RULE_SCORE_VERSION = "resume_rule_v1"
    RUBRIC = [
        ("教育背景", 0.10),
        ("技能匹配", 0.20),
        ("项目经历", 0.25),
        ("实习/实践", 0.15),
        ("表达质量", 0.15),
        ("量化结果", 0.10),
        ("风险项", 0.05),
    ]

    def __init__(self, resume_repository: ResumeRepository):
        self.resume_repository = resume_repository

    def upload_resume(self, *, user_id: str, file_name: str, file_bytes: bytes) -> dict:
        suffix = Path(file_name).suffix.lower()
        if suffix not in self.ALLOWED_EXTENSIONS:
            raise ResumeServiceError(status_code=400, code=2001, message="Unsupported resume file type")

        if len(file_bytes) > self.MAX_FILE_SIZE:
            raise ResumeServiceError(status_code=400, code=2002, message="Resume file is too large")

        storage_dir = Path(settings.resume_storage_dir)
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f"{uuid4()}{suffix}"
        storage_path.write_bytes(file_bytes)

        resume = self.resume_repository.create(
            user_id=user_id,
            file_url=str(storage_path),
            file_name=file_name,
            parse_status="processing",
        )
        return {
            "resume_id": str(resume.id),
            "parse_status": resume.parse_status,
            "estimated_seconds": 8,
            "progress": self._build_progress(
                parse_status="processing",
                parsed_content=None,
                score_report=None,
                parse_error=None,
                upload_just_finished=True,
            ),
        }

    async def get_status(self, *, user_id: str, resume_id: str) -> dict:
        resume = self.resume_repository.get_by_id(resume_id=resume_id, user_id=user_id)
        if resume is None:
            raise ResumeServiceError(status_code=404, code=2003, message="Resume not found")

        score = resume.score_report
        if resume.parse_status == "done" and resume.parsed_content is not None:
            if score is None:
                # Backfill old records; new records are scored by the worker.
                score = await self.build_score_report(file_name=resume.file_name, parsed_content=resume.parsed_content)
                self.resume_repository.save_score_report(resume=resume, score_report=score)
            else:
                score = self._normalize_existing_report(score=score, parsed_content=resume.parsed_content)

        return {
            "resume_id": str(resume.id),
            "parse_status": resume.parse_status,
            "file_name": resume.file_name,
            "parsed_content": resume.parsed_content,
            "parse_error": resume.parse_error,
            "score": score,
            "progress": self._build_progress(
                parse_status=resume.parse_status,
                parsed_content=resume.parsed_content,
                score_report=score,
                parse_error=resume.parse_error,
            ),
        }

    async def parse_resume_content(self, *, file_name: str, file_bytes: bytes) -> dict:
        raw_text = extract_resume_text(file_name, file_bytes)
        fallback = parse_resume_text(raw_text, file_name=file_name)
        provider = get_provider()
        context = AgentContext(provider=provider, request_id=f"resume-parse:{file_name}", assistant_type=ResumeParserAgent.assistant_type)
        try:
            result = await AgentRunner().run(
                ResumeParserAgent(),
                prompt=self._build_parse_prompt(file_name=file_name, raw_text=raw_text),
                context=context,
            )
            payload = extract_json_object(result.content)
            normalized = self._normalize_parsed_content(payload=payload, fallback=fallback, raw_text=raw_text, file_name=file_name)
            return normalized
        except (ClaudeProviderError, LLMJsonError, ValueError, TypeError):
            return fallback

    async def build_score_report(self, *, file_name: str, parsed_content: dict) -> dict:
        fallback = self._build_rule_score(parsed_content)
        provider = get_provider()
        readable_resume = self._to_readable_resume(file_name=file_name, parsed_content=parsed_content)
        score_prompt = PromptRegistry().render("resume/score", {"readable_resume": readable_resume}).user
        context = AgentContext(provider=provider, request_id=f"resume-score:{file_name}", assistant_type=ResumeScoringAgent.assistant_type)

        try:
            result = await AgentRunner().run(ResumeScoringAgent(), prompt=score_prompt, context=context)
            payload = extract_json_object(result.content)
            normalized = self._normalize_llm_report(payload=payload, fallback=fallback, model_name=provider.model or "gemma4:26b")
            if self._looks_invalid_review(report=normalized, parsed_content=parsed_content):
                return fallback
            return normalized
        except (ClaudeProviderError, LLMJsonError, ValueError, TypeError):
            return fallback

    @classmethod
    def _build_progress(
        cls,
        *,
        parse_status: str,
        parsed_content: dict | None,
        score_report: dict | None,
        parse_error: str | None,
        upload_just_finished: bool = False,
    ) -> dict:
        """Build a user-facing progress model without adding another database table."""
        if parse_status == "failed":
            reason = cls._failure_reason(parse_error)
            failed_stage = "extracting_text" if reason["code"] in {"text_too_short", "unsupported_file"} else "structuring"
            return cls._progress_payload(current_stage="failed", percent=55, failure_reason=reason, failed_stage=failed_stage)

        if parse_status == "done":
            return cls._progress_payload(current_stage="completed", percent=100)

        if upload_just_finished:
            return cls._progress_payload(current_stage="uploaded", percent=10)

        if parsed_content is not None and score_report is None:
            return cls._progress_payload(current_stage="scoring", percent=80)

        return cls._progress_payload(current_stage="extracting_text", percent=30)

    @staticmethod
    def _progress_payload(
        *,
        current_stage: str,
        percent: int,
        failure_reason: dict | None = None,
        failed_stage: str | None = None,
    ) -> dict:
        labels = {
            "uploaded": "上传成功",
            "extracting_text": "正在提取文本",
            "structuring": "正在结构化解析",
            "scoring": "正在评分",
            "completed": "完成",
            "failed": "解析失败",
        }
        order = ["uploaded", "extracting_text", "structuring", "scoring", "completed"]
        if current_stage == "failed":
            current_index = order.index(failed_stage or "structuring")
        else:
            current_index = order.index(current_stage)

        stages = []
        for index, key in enumerate(order):
            if current_stage == "failed" and key == (failed_stage or "structuring"):
                status = "failed"
            elif current_stage == "failed":
                status = "done" if index < current_index else "pending"
            elif index < current_index:
                status = "done"
            elif index == current_index:
                status = "done" if current_stage == "completed" else "current"
            else:
                status = "pending"
            stages.append({"key": key, "label": labels[key], "status": status})

        return {
            "current_stage": current_stage,
            "percent": percent,
            "label": labels[current_stage],
            "stages": stages,
            "failure_reason": failure_reason,
        }

    @staticmethod
    def _failure_reason(parse_error: str | None) -> dict:
        raw = str(parse_error or "").strip()
        lowered = raw.lower()
        if "unsupported" in lowered or "file type" in lowered or "格式" in raw:
            return {"code": "unsupported_file", "message": "文件格式不支持，请上传 PDF 或 DOCX。", "detail": raw}
        if "too short" in lowered or "text too" in lowered or "文本太少" in raw or "empty" in lowered:
            return {"code": "text_too_short", "message": "简历可提取文本太少，请换一份文本版 PDF/DOCX。", "detail": raw}
        if any(term in lowered for term in ["model", "timeout", "connection", "provider", "unavailable"]):
            return {"code": "model_unavailable", "message": "模型暂不可用，系统会保留文件，请稍后重试解析。", "detail": raw}
        return {"code": "parse_error", "message": "简历解析失败，请检查文件内容后重试。", "detail": raw}

    @staticmethod
    def _build_parse_prompt(*, file_name: str, raw_text: str) -> str:
        return PromptRegistry().render(
            "resume/parse",
            {"file_name": file_name, "raw_text": raw_text[:6000]},
        ).user

    @staticmethod
    def _normalize_parsed_content(*, payload: dict, fallback: dict, raw_text: str, file_name: str) -> dict:
        skills = [str(item).strip() for item in list(payload.get("skills") or fallback.get("skills") or []) if str(item).strip()]
        return {
            "summary": str(payload.get("summary") or fallback.get("summary") or ""),
            "education": [item for item in list(payload.get("education") or fallback.get("education") or []) if isinstance(item, dict)][:5],
            "experience": [item for item in list(payload.get("experience") or fallback.get("experience") or []) if isinstance(item, dict)][:6],
            "projects": [item for item in list(payload.get("projects") or fallback.get("projects") or []) if isinstance(item, dict)][:6],
            "skills": list(dict.fromkeys(skills))[:20],
            "raw_text": raw_text[:6000],
            "file_name": file_name,
            "text_length": len(raw_text),
        }

    @staticmethod
    def _to_readable_resume(*, file_name: str, parsed_content: dict) -> str:
        summary = parsed_content.get("summary") or "None"
        skills = ", ".join(parsed_content.get("skills", []) or []) or "None"
        projects = "; ".join(item.get("name", "") for item in parsed_content.get("projects", []) if isinstance(item, dict)) or "None"
        experience = "; ".join(item.get("company", "") for item in parsed_content.get("experience", []) if isinstance(item, dict)) or "None"
        education = "; ".join(item.get("school", "") for item in parsed_content.get("education", []) if isinstance(item, dict)) or "None"
        raw_json = json.dumps(parsed_content, ensure_ascii=False)
        return (
            f"简历文件名：{file_name}\n"
            f"个人摘要：{summary}\n"
            f"技能：{skills}\n"
            f"项目：{projects}\n"
            f"经历：{experience}\n"
            f"教育：{education}\n"
            f"结构化 JSON：{raw_json}\n\n"
            "请输出 JSON，键必须为：overall_score,label,summary,dimensions,highlights,risks,next_actions。\n"
            "dimensions 必须是数组，固定 7 个维度：教育背景(0.10)、技能匹配(0.20)、项目经历(0.25)、实习/实践(0.15)、表达质量(0.15)、量化结果(0.10)、风险项(0.05)。\n"
            "每个维度对象必须包含：dimension, score, weight, evidence, problems, suggestions, confidence。\n"
            "evidence 只能引用简历中能看到的事实；problems 写扣分原因；suggestions 写可执行修改建议。"
        )

    @staticmethod
    def _looks_invalid_review(*, report: dict, parsed_content: dict) -> bool:
        text_blob = " ".join(
            [
                str(report.get("summary", "")),
                *[str(item) for item in report.get("risks", [])],
                *[str(item) for item in report.get("highlights", [])],
            ]
        )
        signal_count = sum(1 for key in ("summary", "skills", "projects", "experience", "education") if parsed_content.get(key))
        parse_failure_terms = ["乱码", "编码", "解析失败", "不可读", "corrupt", "encoding", "parse failure"]
        if signal_count >= 3 and any(term in text_blob.lower() for term in [item.lower() for item in parse_failure_terms]):
            return True
        if signal_count >= 4 and int(report.get("overall_score", 0)) <= 10:
            return True
        return False

    @staticmethod
    def _normalize_existing_report(*, score: dict, parsed_content: dict) -> dict:
        fallback = ResumeService._build_rule_score(parsed_content)
        if score.get("rubric_version") == ResumeService.RUBRIC_VERSION and isinstance(score.get("dimensions"), list):
            dimensions = ResumeService._normalize_rubric_dimensions(score.get("dimensions"), fallback=fallback)
        else:
            dimensions = ResumeService._normalize_rubric_dimensions(score.get("dimensions"), fallback=fallback)
        merged = {**fallback, **score}
        merged["dimensions"] = dimensions
        merged["dimension_scores"] = {item["dimension"]: item["score"] for item in dimensions}
        merged["rubric_version"] = ResumeService.RUBRIC_VERSION
        merged["rule_score"] = score.get("rule_score") or fallback["rule_score"]
        merged["llm_review"] = score.get("llm_review") or fallback["llm_review"]
        merged["highlights"] = [str(item) for item in list(score.get("highlights") or fallback["highlights"])[:3]]
        merged["risks"] = [str(item) for item in list(score.get("risks") or fallback["risks"])[:4]]
        merged["next_actions"] = [str(item) for item in list(score.get("next_actions") or fallback["next_actions"])[:3]]
        merged["summary"] = str(score.get("summary") or fallback["summary"])
        merged["source"] = str(score.get("source") or fallback["source"])
        merged["model"] = str(score.get("model") or fallback["model"])
        merged["status"] = str(score.get("status") or ("fallback" if merged["source"] == "fallback_rule" else "ready"))
        merged["overall_score"] = max(0, min(100, int(score.get("overall_score") or fallback["overall_score"])))
        merged["label"] = str(score.get("label") or fallback["label"])
        return merged

    @staticmethod
    def _normalize_llm_report(*, payload: dict, fallback: dict, model_name: str) -> dict:
        dimensions = ResumeService._normalize_rubric_dimensions(payload.get("dimensions"), fallback=fallback)
        overall_score = max(0, min(100, int(payload.get("overall_score", fallback["overall_score"]))))
        llm_review = {
            "status": "ready",
            "model": model_name,
            "project_expression_quality": str((payload.get("llm_review") or {}).get("project_expression_quality") or "由 Gemma4 根据项目描述质量、贡献边界和结果表达综合判断"),
            "role_relevance": str((payload.get("llm_review") or {}).get("role_relevance") or "由 Gemma4 根据技能、项目和实践经历与目标岗位通用要求综合判断"),
            "risk_judgement": str((payload.get("llm_review") or {}).get("risk_judgement") or "风险项来自简历事实不足、量化缺失或表述不够可验证的地方"),
            "evidence_count": sum(len(item["evidence"]) for item in dimensions),
            "problem_count": sum(len(item["problems"]) for item in dimensions),
            "suggestion_count": sum(len(item["suggestions"]) for item in dimensions),
        }
        return {
            "overall_score": overall_score,
            "label": str(payload.get("label") or fallback["label"]),
            "summary": str(payload.get("summary") or fallback["summary"]),
            "dimensions": dimensions,
            "dimension_scores": {item["dimension"]: item["score"] for item in dimensions},
            "highlights": [str(item) for item in list(payload.get("highlights") or fallback["highlights"])[:3]],
            "risks": [str(item) for item in list(payload.get("risks") or fallback["risks"])[:4]],
            "next_actions": [str(item) for item in list(payload.get("next_actions") or fallback["next_actions"])[:3]],
            "source": "gemma4",
            "model": model_name,
            "status": "ready",
            "rubric_version": ResumeService.RUBRIC_VERSION,
            "rule_score": fallback["rule_score"],
            "llm_review": llm_review,
        }

    @staticmethod
    def _normalize_rubric_dimensions(dimensions_payload, *, fallback: dict) -> list[dict]:
        """Normalize model or legacy dimension payloads into the public rubric schema."""
        fallback_by_name = {item["dimension"]: item for item in fallback["dimensions"]}
        payload_by_name: dict[str, dict] = {}
        if isinstance(dimensions_payload, list):
            for item in dimensions_payload:
                if isinstance(item, dict):
                    name = str(item.get("dimension") or "").strip()
                    if name:
                        payload_by_name[name] = item
        elif isinstance(dimensions_payload, dict):
            legacy_map = {
                "completeness": "表达质量",
                "skills_depth": "技能匹配",
                "project_quality": "项目经历",
                "ats_readiness": "风险项",
            }
            for key, value in dimensions_payload.items():
                name = legacy_map.get(str(key), str(key))
                payload_by_name[name] = {"dimension": name, "score": value}

        normalized: list[dict] = []
        for name, weight in ResumeService.RUBRIC:
            base = fallback_by_name[name]
            incoming = payload_by_name.get(name, {})
            evidence = ResumeService._list_of_strings(incoming.get("evidence") or base["evidence"], limit=4)
            problems = ResumeService._list_of_strings(incoming.get("problems") or base["problems"], limit=4)
            suggestions = ResumeService._list_of_strings(incoming.get("suggestions") or base["suggestions"], limit=4)
            normalized.append(
                {
                    "dimension": name,
                    "score": ResumeService._clamp_int(incoming.get("score", base["score"])),
                    "weight": weight,
                    "evidence": evidence,
                    "problems": problems,
                    "suggestions": suggestions,
                    "confidence": ResumeService._clamp_float(incoming.get("confidence", base["confidence"])),
                }
            )
        return normalized

    @staticmethod
    def _dimension(*, name: str, score: int, weight: float, evidence: list[str], problems: list[str], suggestions: list[str], confidence: float) -> dict:
        return {
            "dimension": name,
            "score": ResumeService._clamp_int(score),
            "weight": weight,
            "evidence": ResumeService._list_of_strings(evidence, limit=4),
            "problems": ResumeService._list_of_strings(problems, limit=4),
            "suggestions": ResumeService._list_of_strings(suggestions, limit=4),
            "confidence": ResumeService._clamp_float(confidence),
        }

    @staticmethod
    def _list_of_strings(items, *, limit: int) -> list[str]:
        return [str(item).strip() for item in list(items or []) if str(item).strip()][:limit]

    @staticmethod
    def _clamp_int(value, *, default: int = 0) -> int:
        try:
            return max(0, min(100, int(round(float(value)))))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clamp_float(value, *, default: float = 0.75) -> float:
        try:
            return round(max(0.0, min(1.0, float(value))), 2)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _weighted_score(dimensions: list[dict]) -> int:
        total = sum(float(item["score"]) * float(item["weight"]) for item in dimensions)
        return ResumeService._clamp_int(total)

    @staticmethod
    def _build_rule_score(parsed_content: dict) -> dict:
        """Build deterministic rubric scoring used as fallback and evidence baseline."""
        skills = [str(item).strip() for item in parsed_content.get("skills", []) or [] if str(item).strip()]
        projects = [item for item in parsed_content.get("projects", []) or [] if isinstance(item, dict)]
        experience = [item for item in parsed_content.get("experience", []) or [] if isinstance(item, dict)]
        education = [item for item in parsed_content.get("education", []) or [] if isinstance(item, dict)]
        summary = str(parsed_content.get("summary", "") or "").strip()
        raw_text = " ".join(
            [
                summary,
                str(parsed_content.get("raw_text") or ""),
                " ".join(skills),
                json.dumps(projects, ensure_ascii=False),
                json.dumps(experience, ensure_ascii=False),
                json.dumps(education, ensure_ascii=False),
            ]
        )

        checks = {
            "has_contact_email": bool(re.search(r"[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}", raw_text)),
            "has_contact_phone": bool(re.search(r"(?<!\d)(?:1[3-9]\d{9}|\d{3,4}[- ]?\d{7,8})(?!\d)", raw_text)),
            "has_project_name": bool(projects and any(str(item.get("name") or "").strip() for item in projects)),
            "has_quantified_metrics": bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|ms|s|秒|分钟|人|万|千|次|条|QPS|TPS|coverage|hit rate|latency|users|requests|覆盖率|命中率)", raw_text, re.IGNORECASE)),
            "has_skill_keywords": len(skills) >= 2,
            "has_education": bool(education),
            "has_experience": bool(experience),
            "has_summary": bool(summary),
        }
        vague_terms = ["负责相关工作", "参与相关", "熟悉各种", "良好沟通", "吃苦耐劳", "认真负责", "responsible for related work", "participated in related work", "familiar with many", "good communication", "hard-working"]
        vague_hits = [term for term in vague_terms if term.lower() in raw_text.lower()]

        project_names = [str(item.get("name") or "").strip() for item in projects if str(item.get("name") or "").strip()]
        project_stack = [skill for skill in skills if skill.lower() in raw_text.lower()]
        rubric_names = [name for name, _weight in ResumeService.RUBRIC]

        education_score = 85 if checks["has_education"] else 45
        if education and any(item.get("major") or item.get("degree") for item in education):
            education_score += 8
        if education and any(item.get("gpa") or item.get("courses") for item in education):
            education_score += 7

        skill_score = min(100, 42 + len(skills) * 8 + (10 if len(project_stack) >= 3 else 0))
        project_score = min(100, 48 + len(projects) * 16 + (10 if checks["has_project_name"] else 0) + (12 if checks["has_quantified_metrics"] else 0))
        practice_score = min(100, 42 + len(experience) * 22 + (10 if checks["has_contact_email"] or checks["has_contact_phone"] else 0))
        expression_score = min(100, 50 + (15 if summary else 0) + (12 if projects else 0) + (8 if not vague_hits else -8))
        metric_score = 82 if checks["has_quantified_metrics"] else 45
        risk_score = 88 - min(30, len(vague_hits) * 10) - (8 if not checks["has_contact_email"] and not checks["has_contact_phone"] else 0)

        dimensions = [
            ResumeService._dimension(
                name=rubric_names[0],
                score=education_score,
                weight=0.10,
                evidence=["已提取教育经历" if education else "简历中未提取到教育经历"],
                problems=[] if education else ["学校、专业、学历或时间范围不完整"],
                suggestions=["补充学校、专业、学历、时间；如成绩有优势可补 GPA 或相关课程"],
                confidence=0.82 if education else 0.68,
            ),
            ResumeService._dimension(
                name=rubric_names[1],
                score=skill_score,
                weight=0.20,
                evidence=[f"识别到 {len(skills)} 项技能关键词：{', '.join(skills[:6])}" if skills else "未识别到稳定技能关键词"],
                problems=[] if len(skills) >= 5 else ["技能关键词偏少，可能影响 ATS 和岗位匹配"],
                suggestions=["围绕目标岗位补充语言、框架、数据库、工程工具和业务关键词"],
                confidence=0.86 if skills else 0.62,
            ),
            ResumeService._dimension(
                name=rubric_names[2],
                score=project_score,
                weight=0.25,
                evidence=[f"简历中包含项目：{', '.join(project_names[:3])}" if project_names else "未提取到明确项目名称"],
                problems=[] if checks["has_project_name"] and checks["has_quantified_metrics"] else ["缺少量化结果" if not checks["has_quantified_metrics"] else "项目边界不够明确"],
                suggestions=["用 STAR 法描述背景、本人动作、技术难点和结果；补充耗时、命中率、覆盖率或吞吐量等指标"],
                confidence=0.88 if projects else 0.65,
            ),
            ResumeService._dimension(
                name=rubric_names[3],
                score=practice_score,
                weight=0.15,
                evidence=[f"包含 {len(experience)} 段实践或工作经历" if experience else "未提取到实习或实践经历"],
                problems=[] if experience else ["真实工作流、协作对象和交付结果不足"],
                suggestions=["补充实习、课程项目、开源或团队协作经历，并说明交付物"],
                confidence=0.82 if experience else 0.66,
            ),
            ResumeService._dimension(
                name=rubric_names[4],
                score=expression_score,
                weight=0.15,
                evidence=["包含个人摘要" if summary else "缺少个人摘要", "项目/经历条目可被结构化解析" if projects or experience else "结构化条目较少"],
                problems=[f"存在空泛表达：{', '.join(vague_hits[:3])}"] if vague_hits else ([] if summary else ["开头定位不够聚焦，HR 快速浏览时信息不足"]),
                suggestions=["每段经历写清场景、职责边界、技术选择和可验证结果"],
                confidence=0.8,
            ),
            ResumeService._dimension(
                name=rubric_names[5],
                score=metric_score,
                weight=0.10,
                evidence=["已识别到量化指标或数字结果" if checks["has_quantified_metrics"] else "当前未识别到量化结果"],
                problems=[] if checks["has_quantified_metrics"] else ["缺少指标、数据或前后对比，项目价值不够可验证"],
                suggestions=["补充性能、规模、效率、覆盖率、命中率、用户量或业务转化等数字"],
                confidence=0.84,
            ),
            ResumeService._dimension(
                name=rubric_names[6],
                score=risk_score,
                weight=0.05,
                evidence=["未发现明显夸大或矛盾表达" if not vague_hits else f"发现 {len(vague_hits)} 个低证据表达"],
                problems=["缺少邮箱或手机号，真实投递场景可能影响联系"] if not checks["has_contact_email"] and not checks["has_contact_phone"] else [],
                suggestions=["删除不可验证的夸张描述，保留能被项目、经历或数据支撑的表达"],
                confidence=0.78,
            ),
        ]
        overall_score = ResumeService._weighted_score(dimensions)
        label = "优秀" if overall_score >= 85 else "良好" if overall_score >= 70 else "待加强"

        highlights: list[str] = []
        risks: list[str] = []
        next_actions: list[str] = []

        if skills:
            highlights.append(f"已识别 {len(skills)} 项核心技能")
        if projects:
            highlights.append(f"包含 {len(projects)} 段项目经历")
        if summary:
            highlights.append("具备简历摘要，有助于快速建立岗位匹配印象")

        for item in dimensions:
            risks.extend(item["problems"])
            next_actions.extend(item["suggestions"])

        return {
            "overall_score": overall_score,
            "label": label,
            "summary": "规则引擎生成的兜底评估：按教育、技能、项目、实践、表达、量化结果和风险项给出可解释评分。",
            "dimensions": dimensions,
            "dimension_scores": {item["dimension"]: item["score"] for item in dimensions},
            "highlights": highlights[:3] or ["已完成基础简历解析"],
            "risks": list(dict.fromkeys(risks))[:4] or ["建议继续补充与目标岗位相关的经历细节"],
            "next_actions": list(dict.fromkeys(next_actions))[:3] or ["补齐简历关键字段后重新评估"],
            "source": "fallback_rule",
            "model": "rule-engine",
            "status": "fallback",
            "rubric_version": ResumeService.RUBRIC_VERSION,
            "rule_score": {
                "version": ResumeService.RULE_SCORE_VERSION,
                "checks": checks,
                "vague_terms": vague_hits,
                "weighted_score": overall_score,
            },
            "llm_review": {
                "status": "fallback",
                "reason": "Gemma4 未返回稳定可解析的结构化评分，已使用规则评分兜底。",
                "project_expression_quality": "规则层只能判断项目是否存在、是否量化，不能完全替代模型判断表达深度。",
                "role_relevance": "规则层根据技能和项目关键词粗略判断岗位相关性。",
                "risk_judgement": "规则层检查联系方式、量化结果和空泛表达。",
            },
        }
