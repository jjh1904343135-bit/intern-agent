from __future__ import annotations

from typing import Any

from app.agents.interview.evaluator import (
    adjust_difficulty,
    analyze_answer,
    build_followup_prompt,
    select_followup_strategy,
    update_evaluation_state,
)
from app.agents.interview.models import EvaluationState, InterviewAgentState
from app.agents.interview.planner import build_question_plan
from app.agents.interview.tools import extract_candidate_profile, extract_job_profile, get_job_detail


def initialize_interview_agent_state(*, session_id: str, job, resume, round_type: str = "mixed") -> dict[str, Any]:
    # 面试 Agent 的初始状态来自岗位画像和候选人画像，不读取 AI 助手长期记忆。
    raw_job = get_job_detail(job=job)
    job_profile = extract_job_profile(raw_job)
    candidate_profile = extract_candidate_profile(
        resume_id=str(resume.id),
        file_name=resume.file_name,
        parsed_resume=resume.parsed_content or {},
        job_profile=job_profile,
    )
    difficulty = _initial_difficulty(job_profile.level)
    plan = build_question_plan(
        job_profile=job_profile,
        candidate_profile=candidate_profile,
        round_type=round_type,
        difficulty=difficulty,
    )
    state = InterviewAgentState(
        session_id=session_id,
        job_profile=job_profile.to_dict(),
        candidate_profile=candidate_profile.to_dict(),
        round_type=round_type if round_type in {"screening", "technical", "hm", "behavioral", "mixed"} else "mixed",
        question_plan=[item.to_dict() for item in plan],
        evaluation_state=EvaluationState().to_dict(),
        difficulty=difficulty,
        remaining_focus=list(job_profile.interview_focus),
    )
    return state.to_dict()


def first_question(agent_state: dict[str, Any]) -> dict[str, Any]:
    plan = list(agent_state.get("question_plan") or [])
    if plan:
        return plan[0]
    return {
        "id": "q-1",
        "category": "experience",
        "skill_tag": "岗位能力",
        "prompt": "请结合你的简历，说明你最匹配这个岗位的一段经历。",
        "ideal_signals": ["项目背景", "本人动作", "结果"],
        "followup_axes": ["clarify"],
        "difficulty": 2,
    }


def next_planned_question(agent_state: dict[str, Any], *, round_index: int) -> dict[str, Any]:
    plan = list(agent_state.get("question_plan") or [])
    if 0 <= round_index - 1 < len(plan):
        return plan[round_index - 1]
    return first_question(agent_state)


def process_answer(
    *,
    agent_state: dict[str, Any] | None,
    round_index: int,
    question_id: str,
    answer: str,
) -> dict[str, Any]:
    state = dict(agent_state or {})
    planned_question = next_planned_question(state, round_index=round_index)
    # 每轮回答都会转成可评分信号，再决定难度和追问策略。
    signals = analyze_answer(
        answer=answer,
        planned_question=planned_question,
        job_profile=state.get("job_profile") or {},
    )
    evaluation = update_evaluation_state(
        current=state.get("evaluation_state"),
        answer_signals=signals,
        planned_question=planned_question,
    )
    difficulty = adjust_difficulty(current_difficulty=int(state.get("difficulty") or 2), answer_signals=signals)
    strategy = select_followup_strategy(answer_signals=signals, difficulty=difficulty)
    next_prompt = build_followup_prompt(
        strategy=strategy,
        planned_question=planned_question,
        answer_signals=signals,
        difficulty=difficulty,
    )
    asked = list(state.get("asked_questions") or [])
    asked.append(
        {
            "question_id": question_id,
            "round_index": round_index,
            "planned_question": planned_question,
            "answer": answer,
            "answer_signals": signals.to_dict(),
            "followup_strategy": strategy,
        }
    )
    state["asked_questions"] = asked
    state["evaluation_state"] = evaluation.to_dict()
    state["difficulty"] = difficulty
    state["last_followup_strategy"] = strategy
    state["remaining_focus"] = _remaining_focus(state)
    return {
        "agent_state": state,
        "answer_signals": signals.to_dict(),
        "evaluation_state": evaluation.to_dict(),
        "difficulty": difficulty,
        "followup_strategy": strategy,
        "next_prompt": next_prompt,
    }


def build_summary(agent_state: dict[str, Any] | None) -> dict[str, Any]:
    state = agent_state or {}
    evaluation = state.get("evaluation_state") or EvaluationState().to_dict()
    average = round(
        sum(int(evaluation.get(key) or 1) for key in ["technical_depth", "practical_experience", "communication", "problem_solving", "ownership", "role_fit"]) / 6,
        2,
    )
    probability = "70%-85%" if average >= 4 else "50%-70%" if average >= 3 else "30%-50%"
    strongest = max(
        ["technical_depth", "practical_experience", "communication", "problem_solving", "ownership", "role_fit"],
        key=lambda key: int(evaluation.get(key) or 1),
    )
    weakest = min(
        ["technical_depth", "practical_experience", "communication", "problem_solving", "ownership", "role_fit"],
        key=lambda key: int(evaluation.get(key) or 1),
    )
    return {
        "fit_level": average,
        "pass_probability": probability,
        "strongest_dimension": strongest,
        "weakest_dimension": weakest,
        "risk_points": _risk_points(state),
        "improvement_suggestions": _improvements(state, weakest),
        "score_dimensions": _summary_score_dimensions(evaluation),
        "evidence_chain": _evidence_chain(state),
    }


def _summary_score_dimensions(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "technical_depth": ("技术深度", 0.22),
        "practical_experience": ("项目实践", 0.20),
        "communication": ("表达沟通", 0.15),
        "problem_solving": ("问题解决", 0.16),
        "ownership": ("责任边界", 0.14),
        "role_fit": ("岗位匹配", 0.13),
    }
    evidence = list(evaluation.get("evidence") or [])
    dimensions: list[dict[str, Any]] = []
    for key, (label, weight) in labels.items():
        score = int(evaluation.get(key) or 1)
        dimensions.append(
            {
                "dimension": label,
                "score": score,
                "weight": weight,
                "evidence": evidence[-3:] or ["来自本轮回答信号的规则评分"],
                "problems": [] if score >= 4 else [f"{label} 证据还不够充分"],
                "suggestions": [_dimension_suggestion(key)],
                "confidence": 0.78 if evidence else 0.62,
            }
        )
    return dimensions


def _evidence_chain(state: dict[str, Any]) -> list[dict[str, Any]]:
    job_profile = state.get("job_profile") or {}
    candidate_profile = state.get("candidate_profile") or {}
    project_names = [
        str(item.get("name") or "")
        for item in candidate_profile.get("projects") or []
        if isinstance(item, dict) and item.get("name")
    ]
    chain: list[dict[str, Any]] = []
    for item in state.get("asked_questions") or []:
        planned = item.get("planned_question") or {}
        signals = item.get("answer_signals") or {}
        strategy = item.get("followup_strategy")
        chain.append(
            {
                "question_id": item.get("question_id"),
                "round_index": item.get("round_index"),
                "question_focus": planned.get("skill_tag"),
                "job_requirement": planned.get("prompt") or "岗位要求未记录",
                "resume_evidence": "、".join(project_names[:3]) or candidate_profile.get("summary") or "简历证据不足",
                "answer_signal_summary": {
                    "completeness": signals.get("completeness"),
                    "depth": signals.get("depth"),
                    "specificity": signals.get("specificity"),
                    "ownership": signals.get("ownership"),
                    "red_flags": signals.get("red_flags") or [],
                    "missing_expected_points": signals.get("missing_expected_points") or [],
                },
                "followup_reason": _followup_reason(strategy=strategy, signals=signals),
            }
        )
    return chain


def _dimension_suggestion(key: str) -> str:
    suggestions = {
        "technical_depth": "补充架构、指标、失败场景和技术取舍。",
        "practical_experience": "用真实项目说明个人动作和交付结果。",
        "communication": "用更短结构表达背景、动作、结果和复盘。",
        "problem_solving": "说明排查路径、验证方法和回归测试。",
        "ownership": "明确本人负责的模块和决策边界。",
        "role_fit": "把回答和 JD 关键职责一一对应。",
    }
    return suggestions.get(key, "继续补充可验证证据。")


def _followup_reason(*, strategy: str | None, signals: dict[str, Any]) -> str:
    if strategy == "clarify":
        return "回答过短或个人贡献不清晰，先要求补具体场景。"
    if strategy == "drill_down":
        return "回答有基本内容但深度不足，继续追问设计原因和失败场景。"
    if strategy == "transfer":
        return "回答较完整，提升难度并考察迁移能力。"
    if strategy == "challenge":
        return "回答有一定证据，挑战关键假设和风险处理。"
    red_flags = signals.get("red_flags") or []
    return f"根据回答信号继续追问：{'、'.join(red_flags) or '暂无明显风险'}。"


def _initial_difficulty(level: str) -> int:
    return {"intern": 2, "junior": 2, "mid": 3, "senior": 4, "staff": 5, "manager": 4}.get(level, 2)


def _remaining_focus(state: dict[str, Any]) -> list[str]:
    focus = list(state.get("remaining_focus") or [])
    asked_skills = {str(item.get("planned_question", {}).get("skill_tag") or "") for item in state.get("asked_questions") or []}
    return [item for item in focus if item not in asked_skills]


def _risk_points(state: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for item in state.get("asked_questions") or []:
        signals = item.get("answer_signals") or {}
        risks.extend(signals.get("red_flags") or [])
        risks.extend(f"缺少 {point}" for point in (signals.get("missing_expected_points") or [])[:2])
    return list(dict.fromkeys(risks))[:5] or ["暂无明显高频风险点，但仍建议准备更量化的项目证据。"]


def _improvements(state: dict[str, Any], weakest: str) -> list[str]:
    suggestions = {
        "technical_depth": "为核心项目准备架构图、失败场景、指标和取舍。",
        "practical_experience": "用 STAR 结构补充具体动作、结果和复盘。",
        "communication": "练习用更短句说明目标、协作对象和对齐方式。",
        "problem_solving": "准备问题定位路径：现象、假设、验证、修复、回归。",
        "ownership": "明确你本人负责的模块、决策和影响。",
        "role_fit": "把简历项目改写成和目标岗位 JD 一一对应的证据链。",
    }
    missing = state.get("candidate_profile", {}).get("missing_skills") or []
    result = [suggestions.get(weakest, suggestions["role_fit"])]
    if missing:
        result.append(f"补一条能证明 {'、'.join(missing[:3])} 的项目或学习验证记录。")
    result.append("每个项目准备 1 分钟版和 3 分钟版，避免回答过散。")
    return result[:4]
