from __future__ import annotations

from collections.abc import Iterable

KEYWORDS = {
    "structure": {"先", "然后", "最后", "拆分", "步骤", "方案", "计划"},
    "communication": {"澄清", "沟通", "协作", "同步", "反馈", "对齐"},
    "domain": {"python", "sql", "fastapi", "redis", "接口", "数据库", "异步", "测试"},
}

MODE_QUESTIONS = {
    "standard": "请你做一个简短自我介绍，并说明你会如何推进这个岗位的后端任务。",
    "pressure": "如果线上接口延迟突然升高，你会如何在高压下定位问题并推进修复？",
    "case": "请设计一个支持简历解析和岗位匹配的最小后端闭环，并说明关键取舍。",
    "negotiation": "如果你拿到 offer，但职责与预期不一致，你会如何沟通争取？",
}


def opening_question(*, mode: str, job_title: str) -> str:
    base_question = MODE_QUESTIONS.get(mode, MODE_QUESTIONS["standard"])
    return f"你正在模拟面试岗位：{job_title}。{base_question}"


def evaluate_answer(answer: str, *, mode: str) -> dict:
    normalized = answer.lower()
    dimensions = {
        "structure": _score_dimension(normalized, KEYWORDS["structure"]),
        "communication": _score_dimension(normalized, KEYWORDS["communication"]),
        "domain": _score_dimension(normalized, KEYWORDS["domain"]),
    }
    overall = round(sum(dimensions.values()) / len(dimensions), 2)

    feedback_bits: list[str] = []
    if dimensions["structure"] < 3:
        feedback_bits.append("可以把回答拆成更清晰的步骤。")
    if dimensions["communication"] < 3:
        feedback_bits.append("可以补充你如何和面试官或团队对齐信息。")
    if dimensions["domain"] < 3:
        feedback_bits.append("可以再补一些技术细节，让方案更落地。")
    if not feedback_bits:
        feedback_bits.append("回答结构清晰，也兼顾了协作和技术落地。")

    follow_up = {
        "standard": "如果继续追问，你会如何验证这套方案的效果？",
        "pressure": "如果修复窗口只有 30 分钟，你的优先级会怎么排？",
        "case": "如果只能在两天内交付 MVP，你会删掉哪些部分？",
        "negotiation": "如果对方暂时不能满足你的诉求，你会如何继续沟通？",
    }.get(mode, "如果继续追问，你会如何验证这套方案的效果？")

    return {
        "overall_score": overall,
        "dimensions": dimensions,
        "feedback_text": " ".join(feedback_bits),
        "follow_up_question": follow_up,
    }


def build_report(messages: Iterable[dict], *, mode: str) -> dict:
    feedback_messages = [item for item in messages if item.get("role") == "assistant" and item.get("feedback_score") is not None]
    if not feedback_messages:
        raise ValueError("At least one answered round is required")

    latest = feedback_messages[-1]
    dimension_scores = latest.get("dimension_scores", {})
    overall = latest.get("feedback_score", 0)

    strengths: list[str] = []
    improvements: list[str] = []
    for key, score in dimension_scores.items():
        if score >= 4:
            strengths.append(_dimension_label(key))
        elif score <= 2:
            improvements.append(_dimension_label(key))

    return {
        "mode": mode,
        "overall_score": overall,
        "dimensions": dimension_scores,
        "strengths": strengths or ["表达完整"],
        "improvements": improvements or ["可以继续用更多真实案例支撑回答"],
        "summary": latest.get("content", ""),
    }


def _score_dimension(answer: str, keywords: set[str]) -> int:
    hits = sum(1 for keyword in keywords if keyword in answer)
    return min(5, max(1, hits + 1))


def _dimension_label(key: str) -> str:
    return {
        "structure": "结构化表达",
        "communication": "沟通协作",
        "domain": "技术深度",
    }.get(key, key)
