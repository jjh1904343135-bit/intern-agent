from __future__ import annotations

from pathlib import Path

from evals.agent.run_agent_eval import (
    evaluate_agent_cases,
    render_agent_eval_report,
)


def test_agent_eval_report_aggregates_core_reliability_metrics() -> None:
    summary = evaluate_agent_cases()

    assert summary["case_count"] >= 5
    assert summary["metrics"]["intent_accuracy"] >= 0.8
    assert summary["metrics"]["tool_call_accuracy"] >= 0.8
    assert summary["metrics"]["argument_accuracy"] >= 0.8
    assert summary["metrics"]["rag_grounding_rate"] >= 0.8
    assert summary["metrics"]["resume_rubric_compliance"] >= 0.8
    assert summary["metrics"]["interview_followup_hit_rate"] >= 0.8
    assert "failed_cases" in summary


def test_agent_eval_report_renders_markdown_for_interview_review() -> None:
    summary = {
        "case_count": 6,
        "metrics": {
            "intent_accuracy": 1.0,
            "tool_call_accuracy": 1.0,
            "argument_accuracy": 0.83,
            "rag_grounding_rate": 1.0,
            "resume_rubric_compliance": 1.0,
            "interview_followup_hit_rate": 1.0,
        },
        "failed_cases": [],
    }

    report = render_agent_eval_report(summary, rag_report_path=Path("backend/evals/rag/rag_eval_report.md"))

    assert "# Agent / RAG Eval Report" in report
    assert "Intent Accuracy: 1.00" in report
    assert "Tool Call Accuracy: 1.00" in report
    assert "Argument Accuracy: 0.83" in report
    assert "Interview Follow-up Hit Rate: 1.00" in report
    assert "RAG report" in report
