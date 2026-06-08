from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.interview.evaluator import analyze_answer, select_followup_strategy
from app.agents.interview.models import CandidateProfile, JobProfile
from app.agents.interview.planner import build_question_plan
from app.agents.supervisor import SupervisorAgent
from app.services.chat_service import ChatService
from app.services.resume_service import ResumeService
from app.tools.job_discovery import recommend_jobs


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "tests" / "agent_eval" / "golden_cases"
DEFAULT_REPORT_PATH = ROOT.parent / "docs" / "evaluation" / "agent-rag-eval-report.md"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_agent_cases() -> dict[str, Any]:
    failed: list[str] = []
    chat_cases = load_jsonl(GOLDEN_DIR / "chat_cases.jsonl")
    rag_cases = load_jsonl(GOLDEN_DIR / "rag_cases.jsonl")
    job_cases = load_jsonl(GOLDEN_DIR / "job_match_cases.jsonl")
    interview_cases = load_jsonl(GOLDEN_DIR / "interview_cases.jsonl")
    resume_cases = load_jsonl(GOLDEN_DIR / "resume_score_cases.jsonl")

    intent_hits = 0
    tool_hits = 0
    arg_hits = 0
    arg_total = 0
    supervisor = SupervisorAgent()
    for case in chat_cases:
        turn = supervisor.plan_turn(message=case["input"], history=[], tool_context={})
        if turn.intent == case["expected_intent"]:
            intent_hits += 1
        else:
            failed.append(f"{case['id']}: intent {turn.intent} != {case['expected_intent']}")
        expected_tools = set(case.get("expected_tools") or [])
        if expected_tools.issubset(set(turn.tools)):
            tool_hits += 1
        else:
            failed.append(f"{case['id']}: missing tools {sorted(expected_tools - set(turn.tools))}")
        if expected := (case.get("expected_tool_args") or {}).get("job_search"):
            arg_total += 1
            keyword = ChatService._keyword_from_message(case["input"]) or ""
            city = ChatService._city_from_message(case["input"])
            if all(term.lower() in keyword.lower() for term in expected.get("keyword_contains") or []) and city == expected.get("city"):
                arg_hits += 1
            else:
                failed.append(f"{case['id']}: job_search args keyword={keyword!r} city={city!r}")

    rag_hits = 0
    for case in rag_cases:
        tool_context = {
            "knowledge_search": {
                "available": True,
                "query": case["input"],
                "total": len(case.get("mock_hits") or []),
                "source": "knowledge_rag",
                "hits": case.get("mock_hits") or [],
            }
        }
        turn = supervisor.plan_turn(message=case["input"], history=[], tool_context=tool_context)
        prompt = turn.prompt
        if set(case.get("expected_tools") or []).issubset(set(turn.tools)) and all(term in prompt for term in case.get("must_use_references") or []):
            rag_hits += 1
        else:
            failed.append(f"{case['id']}: RAG tool or references missing")

    job_hits = 0
    for case in job_cases:
        top = recommend_jobs(
            case["jobs"],
            resume_profile=case["resume_profile"],
            city=case["input"].get("city"),
            experience=case["input"].get("experience"),
            skills=tuple(case["input"].get("skills") or ()),
        )[0]
        if top.get("canonical_title") == case["expected_top_title"] and top.get("score_dimensions") and top.get("evidence_summary"):
            job_hits += 1
        else:
            failed.append(f"{case['id']}: job recommendation evidence missing")

    interview_hits = 0
    for case in interview_cases:
        plan = build_question_plan(
            job_profile=JobProfile(**case["job_profile"]),
            candidate_profile=CandidateProfile(**case["candidate_profile"]),
            round_type="mixed",
            difficulty=2,
        )
        planned = plan[0].to_dict()
        case_hits = 0
        for followup_case in case.get("followup_cases") or []:
            signals = analyze_answer(answer=followup_case["answer"], planned_question=planned, job_profile=case["job_profile"])
            strategy = select_followup_strategy(answer_signals=signals, difficulty=4)
            if "expected_strategy" in followup_case:
                case_hits += int(strategy == followup_case["expected_strategy"])
            else:
                case_hits += int(strategy in set(followup_case.get("expected_strategy_in") or []))
        if case_hits == len(case.get("followup_cases") or []):
            interview_hits += 1
        else:
            failed.append(f"{case['id']}: followup policy mismatch")

    resume_hits = 0
    for case in resume_cases:
        report = ResumeService._build_rule_score(case["parsed_content"])
        required_dimensions = set(case.get("required_dimensions") or [])
        actual_dimensions = {item.get("dimension") for item in report.get("dimensions") or []}
        if required_dimensions.issubset(actual_dimensions) and report.get("rubric_version") == ResumeService.RUBRIC_VERSION:
            resume_hits += 1
        else:
            failed.append(f"{case['id']}: resume rubric contract mismatch")

    case_count = len(chat_cases) + len(rag_cases) + len(job_cases) + len(interview_cases) + len(resume_cases)
    return {
        "case_count": case_count,
        "metrics": {
            "intent_accuracy": _ratio(intent_hits, len(chat_cases)),
            "tool_call_accuracy": _ratio(tool_hits, len(chat_cases)),
            "argument_accuracy": _ratio(arg_hits, arg_total),
            "rag_grounding_rate": _ratio(rag_hits, len(rag_cases)),
            "job_match_explanation_rate": _ratio(job_hits, len(job_cases)),
            "resume_rubric_compliance": _ratio(resume_hits, len(resume_cases)),
            "interview_followup_hit_rate": _ratio(interview_hits, len(interview_cases)),
        },
        "failed_cases": failed,
    }


def render_agent_eval_report(summary: dict[str, Any], *, rag_report_path: Path) -> str:
    metrics = summary["metrics"]
    lines = [
        "# Agent / RAG Eval Report",
        "",
        f"Cases: {summary['case_count']}",
        "",
        "## Agent Reliability",
        f"- Intent Accuracy: {metrics['intent_accuracy']:.2f}",
        f"- Tool Call Accuracy: {metrics['tool_call_accuracy']:.2f}",
        f"- Argument Accuracy: {metrics['argument_accuracy']:.2f}",
        f"- Job Match Explanation Rate: {metrics.get('job_match_explanation_rate', 0):.2f}",
        f"- Resume Rubric Compliance: {metrics['resume_rubric_compliance']:.2f}",
        f"- Interview Follow-up Hit Rate: {metrics['interview_followup_hit_rate']:.2f}",
        f"- RAG Grounding Rate: {metrics['rag_grounding_rate']:.2f}",
        "",
        "## RAG report",
        f"- Source: `{rag_report_path.as_posix()}`",
        "",
        "## Failed Cases",
    ]
    if summary.get("failed_cases"):
        lines.extend(f"- {item}" for item in summary["failed_cases"])
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def write_agent_eval_report(*, report_path: Path = DEFAULT_REPORT_PATH) -> dict[str, Any]:
    summary = evaluate_agent_cases()
    report = render_agent_eval_report(summary, rag_report_path=ROOT / "evals" / "rag" / "rag_eval_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return summary


def _ratio(hit: int, total: int) -> float:
    return round(hit / max(total, 1), 2)


def main() -> int:
    summary = write_agent_eval_report()
    print(render_agent_eval_report(summary, rag_report_path=ROOT / "evals" / "rag" / "rag_eval_report.md"))
    return 0 if not summary["failed_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
