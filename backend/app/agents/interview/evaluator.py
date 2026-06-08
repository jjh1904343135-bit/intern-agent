from __future__ import annotations

from app.agents.interview.models import AnswerSignals, EvaluationState
from app.agents.interview.tools import _extract_all_skills


def analyze_answer(*, answer: str, planned_question: dict, job_profile: dict) -> AnswerSignals:
    text = answer.strip()
    mentioned_skills = _extract_all_skills(text)
    expected = [str(item) for item in planned_question.get("ideal_signals") or []]
    missing = [item for item in expected if item.lower() not in text.lower()]
    red_flags: list[str] = []
    if len(text) < 30:
        red_flags.append("回答过短")
    if not any(token in text for token in ["我", "负责", "主导", "实现", "设计"]):
        red_flags.append("个人贡献不清晰")

    return AnswerSignals(
        completeness=_score_by_length(text),
        correctness=_score_expected_hits(text=text, expected=expected),
        depth=_score_depth(text),
        specificity=_score_specificity(text),
        ownership=_score_ownership(text),
        red_flags=red_flags,
        mentioned_skills=mentioned_skills,
        missing_expected_points=missing[:5],
    )


def update_evaluation_state(*, current: dict | None, answer_signals: AnswerSignals, planned_question: dict) -> EvaluationState:
    previous = EvaluationState(**{**EvaluationState().to_dict(), **(current or {})})
    evidence = list(previous.evidence or [])
    skill_tag = str(planned_question.get("skill_tag") or "岗位能力")
    if answer_signals.mentioned_skills:
        evidence.append(f"回答中提到 {skill_tag} 相关技能：{'、'.join(answer_signals.mentioned_skills[:4])}")
    if answer_signals.red_flags:
        evidence.append(f"风险：{'、'.join(answer_signals.red_flags)}")

    return EvaluationState(
        technical_depth=max(previous.technical_depth, answer_signals.depth),
        practical_experience=max(previous.practical_experience, answer_signals.specificity),
        communication=max(previous.communication, answer_signals.completeness),
        problem_solving=max(previous.problem_solving, answer_signals.correctness),
        ownership=max(previous.ownership, answer_signals.ownership),
        role_fit=max(previous.role_fit, min(5, len(answer_signals.mentioned_skills) + 1)),
        confidence=max(previous.confidence, round((answer_signals.completeness + answer_signals.specificity) / 2)),
        evidence=evidence[-8:],
    )


def select_followup_strategy(*, answer_signals: AnswerSignals, difficulty: int) -> str:
    if answer_signals.completeness <= 2 or "回答过短" in answer_signals.red_flags:
        return "clarify"
    if difficulty >= 4 and answer_signals.correctness >= 4:
        return "transfer"
    if answer_signals.depth <= 2 and answer_signals.specificity < 4:
        return "drill_down"
    return "challenge"


def adjust_difficulty(*, current_difficulty: int, answer_signals: AnswerSignals) -> int:
    average = (answer_signals.completeness + answer_signals.correctness + answer_signals.depth + answer_signals.specificity + answer_signals.ownership) / 5
    if answer_signals.specificity >= 4 or answer_signals.depth >= 4:
        return min(5, current_difficulty + 1)
    if average >= 4:
        return min(5, current_difficulty + 1)
    if average <= 2 and (answer_signals.completeness <= 2 or "回答过短" in answer_signals.red_flags):
        return max(1, current_difficulty - 1)
    return current_difficulty


def build_followup_prompt(*, strategy: str, planned_question: dict, answer_signals: AnswerSignals, difficulty: int) -> str:
    skill = str(planned_question.get("skill_tag") or "这个点")
    if strategy == "clarify":
        return f"你刚才提到的 {skill} 还比较概括。请补一个具体场景：目标是什么、你做了什么、结果如何？"
    if strategy == "drill_down":
        return f"继续下钻 {skill}：为什么这样设计？如果延迟、成本或准确率出现问题，你会优先改哪里？"
    if strategy == "transfer":
        return f"把你刚才的方法迁移到一个更复杂的新业务里还成立吗？请说明需要调整的边界和 guardrails。"
    return f"我挑战一下你的方案：如果 {skill} 的关键假设不成立，你会如何发现并修正？"


def _score_by_length(text: str) -> int:
    if len(text) >= 180:
        return 5
    if len(text) >= 100:
        return 4
    if len(text) >= 50:
        return 3
    return 2 if text else 1


def _score_expected_hits(*, text: str, expected: list[str]) -> int:
    if not expected:
        return 3
    hits = sum(1 for item in expected if item.lower() in text.lower())
    return min(5, max(1, hits + 1))


def _score_depth(text: str) -> int:
    keywords = ["为什么", "取舍", "延迟", "指标", "评测", "失败", "缓存", "索引", "guardrail", "监控"]
    hits = sum(1 for item in keywords if item.lower() in text.lower())
    return min(5, max(1, hits + 2))


def _score_specificity(text: str) -> int:
    keywords = ["fastapi", "qdrant", "rag", "pytest", "docker", "redis", "sql", "sse", "指标", "测试"]
    hits = sum(1 for item in keywords if item in text.lower())
    return min(5, max(1, hits + 1))


def _score_ownership(text: str) -> int:
    keywords = ["我负责", "我主导", "我实现", "我设计", "我会", "我在"]
    hits = sum(1 for item in keywords if item in text)
    return min(5, max(1, hits + 1))
