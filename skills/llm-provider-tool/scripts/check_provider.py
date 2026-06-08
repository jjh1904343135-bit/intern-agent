from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok

TOOL = "llm-provider-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect configured LLM provider and optional health details.")
    parser.add_argument("--diagnose", action="store_true", help="Run provider.diagnose(); may touch the model endpoint.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without provider imports.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"provider": "claude", "model": "gemma4:26b", "mode": "self-test"}))
        return 0
    input_payload = {"diagnose": args.diagnose}
    try:
        bootstrap_project_paths()
        from app.core.providers.factory import get_provider

        provider = get_provider()
        result = {"provider": provider.name, "model": provider.model}
        if args.diagnose:
            result["diagnostics"] = asyncio.run(provider.diagnose())
        emit(ok(TOOL, result, input_payload=input_payload))
        return 0
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
