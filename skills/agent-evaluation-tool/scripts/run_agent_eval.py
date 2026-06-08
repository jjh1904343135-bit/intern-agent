from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok

TOOL = "agent-evaluation-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or inspect Agent golden-case evaluation.")
    parser.add_argument("--write-report", action="store_true", help="Write docs/evaluation/agent-rag-eval-report.md.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without loading eval cases.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"case_count": 1, "metrics": {"intent_accuracy": 1.0}, "mode": "self-test"}))
        return 0
    input_payload = {"write_report": args.write_report}
    try:
        bootstrap_project_paths()
        from evals.agent.run_agent_eval import DEFAULT_REPORT_PATH, evaluate_agent_cases, write_agent_eval_report

        summary = write_agent_eval_report() if args.write_report else evaluate_agent_cases()
        emit(ok(TOOL, {"summary": summary, "report_path": str(DEFAULT_REPORT_PATH) if args.write_report else None}, input_payload=input_payload))
        return 0 if not summary.get("failed_cases") else 2
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
