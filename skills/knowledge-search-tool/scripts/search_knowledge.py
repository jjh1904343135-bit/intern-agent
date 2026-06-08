from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok

TOOL = "knowledge-search-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search the AI assistant knowledge RAG tool.")
    parser.add_argument("--query", help="Technical or interview-note question.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum chunks.")
    parser.add_argument("--min-score", type=float, default=0.2, help="Minimum rerank score.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without RAG access.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"total": 1, "retrieval_strategy": "hybrid_dense_lexical_rerank", "mode": "self-test"}))
        return 0
    input_payload = {"query": args.query, "limit": args.limit, "min_score": args.min_score}
    try:
        if not args.query:
            raise ValueError("--query is required")
        bootstrap_project_paths()
        from app.core.database import session_local
        from app.services.knowledge_rag_service import KnowledgeRagService

        db = session_local()
        try:
            payload = KnowledgeRagService(db).search(args.query, limit=args.limit, min_score=args.min_score)
            hits = []
            for hit in list(payload.get("hits") or [])[: args.limit]:
                metadata = hit.get("metadata") or {}
                hits.append(
                    {
                        "question": hit.get("question"),
                        "section_path": hit.get("section_path") or [],
                        "source_file": hit.get("source_file"),
                        "source_url": metadata.get("source_url"),
                        "repo_path": metadata.get("repo_path"),
                        "chunk_index": metadata.get("chunk_index"),
                        "score": metadata.get("rerank_score", hit.get("score")),
                    }
                )
            emit(
                ok(
                    TOOL,
                    {
                        "available": payload.get("available"),
                        "total": payload.get("total"),
                        "source": payload.get("source"),
                        "fallback_notice": payload.get("fallback_notice"),
                        "retrieval_strategy": payload.get("retrieval_strategy"),
                        "retrieval_sufficient": payload.get("retrieval_sufficient"),
                        "sufficiency": payload.get("sufficiency") or {},
                        "hits": hits,
                    },
                    input_payload=input_payload,
                )
            )
            return 0
        finally:
            db.close()
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
