from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok

TOOL = "chat-routing-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect SupervisorAgent intent and tool routing.")
    parser.add_argument("--message", help="User message to route.")
    parser.add_argument("--history-json", default="[]", help="JSON list of recent chat messages.")
    parser.add_argument("--tool-context-json", default="{}", help="JSON object with existing tool context.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without app imports.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(
            ok(
                TOOL,
                {
                    "complexity": "agentic_task",
                    "intent": "job_search",
                    "tools": ["resume_profile", "job_search"],
                    "prompt_template_id": "chat/supervisor",
                    "mode": "self-test",
                },
            )
        )
        return 0
    input_payload = {"message": args.message, "has_history": bool(args.history_json), "has_tool_context": bool(args.tool_context_json)}
    try:
        if not args.message:
            raise ValueError("--message is required")
        bootstrap_project_paths()
        from app.agents.chat.complexity import ChatComplexityClassifier
        from app.agents.supervisor import SupervisorAgent

        history = json.loads(args.history_json)
        tool_context = json.loads(args.tool_context_json)
        complexity = ChatComplexityClassifier().classify(args.message)
        if complexity == "simple_answer":
            emit(
                ok(
                    TOOL,
                    {
                        "complexity": complexity,
                        "agent_name": "chat_assistant",
                        "intent": "general_chat",
                        "steps": ["direct_answer"],
                        "tools": [],
                        "prompt_template_id": "chat/simple_answer",
                        "prompt_template_version": "v1",
                        "prompt_chars": 0,
                        "system_prompt_chars": 0,
                    },
                    input_payload=input_payload,
                )
            )
            return 0
        turn = SupervisorAgent().plan_turn(message=args.message, history=history, tool_context=tool_context)
        emit(
            ok(
                TOOL,
                {
                    "complexity": complexity,
                    "agent_name": turn.agent_name,
                    "intent": turn.intent,
                    "steps": turn.steps,
                    "tools": turn.tools,
                    "prompt_template_id": turn.prompt_template_id,
                    "prompt_template_version": turn.prompt_template_version,
                    "prompt_chars": len(turn.prompt),
                    "system_prompt_chars": len(turn.system_prompt),
                },
                input_payload=input_payload,
            )
        )
        return 0
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
