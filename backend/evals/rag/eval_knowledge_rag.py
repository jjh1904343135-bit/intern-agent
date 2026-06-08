from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

DEFAULT_CASES_PATH = Path(__file__).with_name("rag_eval_cases.jsonl")
DEFAULT_REPORT_PATH = Path(__file__).with_name("rag_eval_report.md")


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            cases.append(json.loads(stripped))
    return cases


def evaluate_case(
    case: dict[str, Any],
    *,
    hits: list[dict[str, Any]],
    answer: str = "",
    top_k_values: tuple[int, ...] = (3, 5),
) -> dict[str, Any]:
    expected_keywords = [str(item) for item in case.get("expected_chunk_keywords") or []]
    correct_rank = _first_correct_rank(hits, expected_keywords)
    result: dict[str, Any] = {
        "id": case.get("id"),
        "question": case.get("question"),
        "correct_rank": correct_rank,
        "mrr": round(1 / correct_rank, 4) if correct_rank else 0.0,
        "hit_count": len(hits),
    }
    for k in top_k_values:
        result[f"recall_at_{k}"] = bool(correct_rank and correct_rank <= k)
        result[f"context_precision_at_{k}"] = _context_precision_at_k(hits, expected_keywords, k)
    result.update(evaluate_answer(case, answer=answer, contexts=[str(hit.get("text") or "") for hit in hits]))
    return result


def evaluate_answer(case: dict[str, Any], *, answer: str, contexts: Iterable[str]) -> dict[str, Any]:
    expected_points = [str(item) for item in case.get("expected_answer_points") or []]
    context_text = "\n".join(contexts)
    covered = [point for point in expected_points if _phrase_matches(answer, point)]
    supported_covered = [point for point in covered if _phrase_matches(context_text, point)]
    unsupported_covered = [point for point in covered if point not in supported_covered]
    forbidden_hits = [str(item) for item in case.get("forbidden_answer_points") or [] if _phrase_matches(answer, str(item))]
    coverage = round(len(covered) / max(len(expected_points), 1), 2) if expected_points else 0.0
    return {
        "answer_point_coverage": coverage,
        "grounded": bool(covered) and not unsupported_covered,
        "hallucination_count": len(unsupported_covered) + len(forbidden_hits),
        "covered_points": covered,
        "unsupported_points": unsupported_covered,
        "forbidden_hits": forbidden_hits,
    }


def evaluate_cases(
    cases: list[dict[str, Any]],
    *,
    search_fn: Callable[[dict[str, Any], int], list[dict[str, Any]]],
    answer_fn: Callable[[dict[str, Any], list[dict[str, Any]]], str] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        hits = search_fn(case, top_k)
        answer = answer_fn(case, hits) if answer_fn else str(case.get("answer") or "")
        rows.append(evaluate_case(case, hits=hits, answer=answer, top_k_values=(3, top_k)))

    failed_cases = [_failure_summary(row) for row in rows if _failure_summary(row)]
    return {
        "case_count": len(rows),
        "cases": rows,
        "retrieval": {
            "recall_at_3": _mean(row["recall_at_3"] for row in rows),
            f"recall_at_{top_k}": _mean(row[f"recall_at_{top_k}"] for row in rows),
            "mrr": _mean(row["mrr"] for row in rows),
            "context_precision_at_3": _mean(row["context_precision_at_3"] for row in rows),
            f"context_precision_at_{top_k}": _mean(row[f"context_precision_at_{top_k}"] for row in rows),
        },
        "generation": {
            "grounded_answer_rate": _mean(row["grounded"] for row in rows),
            "answer_point_coverage": _mean(row["answer_point_coverage"] for row in rows),
            "hallucination_case_count": sum(1 for row in rows if row["hallucination_count"] > 0),
        },
        "failed_cases": failed_cases,
    }


def render_markdown_report(summary: dict[str, Any], *, dataset_name: str) -> str:
    retrieval = summary["retrieval"]
    generation = summary["generation"]
    lines = [
        "# RAG Eval Report",
        "",
        f"Dataset: `{dataset_name}`",
        f"Cases: {summary['case_count']}",
        "",
        "## Retrieval",
        f"- Recall@3: {retrieval['recall_at_3']:.2f}",
        f"- Recall@5: {retrieval.get('recall_at_5', 0):.2f}",
        f"- MRR: {retrieval['mrr']:.2f}",
        f"- Context Precision@3: {retrieval['context_precision_at_3']:.2f}",
        f"- Context Precision@5: {retrieval.get('context_precision_at_5', 0):.2f}",
        f"- Hybrid / Rerank Enabled: {summary.get('hybrid_enabled', True)}",
        "",
        "## Generation",
        f"- Grounded Answer Rate: {generation['grounded_answer_rate']:.2f}",
        f"- Answer Point Coverage: {generation['answer_point_coverage']:.2f}",
        f"- Hallucination Case Count: {generation['hallucination_case_count']}",
        "",
        "## Failed Cases",
    ]
    if not summary["failed_cases"]:
        lines.append("- None")
    else:
        for item in summary["failed_cases"]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_ablation_markdown_report(ablation: dict[str, Any], *, dataset_name: str) -> str:
    lines = [
        "# RAG Ablation Eval Report",
        "",
        f"Dataset: `{dataset_name}`",
        f"Cases: {ablation['case_count']}",
        "",
        "## Retrieval Ablation",
        "| Mode | Recall@3 | Recall@5 | MRR | Failed Cases |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode_name, summary in ablation["modes"].items():
        retrieval = summary["retrieval"]
        lines.append(
            f"| {mode_name} | {retrieval['recall_at_3']:.2f} | "
            f"{retrieval.get('recall_at_5', 0):.2f} | {retrieval['mrr']:.2f} | "
            f"{len(summary['failed_cases'])} |"
        )
    lines.extend(["", "## Failed Cases"])
    for mode_name, summary in ablation["modes"].items():
        lines.append(f"### {mode_name}")
        if not summary["failed_cases"]:
            lines.append("- None")
        else:
            for item in summary["failed_cases"]:
                lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def rewrite_query(question: str, *, expected_keywords: list[str] | None = None) -> str:
    from app.services.knowledge_rag_service import rewrite_technical_queries

    plan = rewrite_technical_queries(question)
    extras = [item for item in (expected_keywords or []) if item not in " ".join(plan["queries"])]
    return " ".join([*plan["queries"], *extras[:4]]).strip()


def pack_contexts(hits: list[dict[str, Any]], *, max_chars: int = 3600) -> str:
    lines: list[str] = []
    total = 0
    for index, hit in enumerate(hits, 1):
        question = hit.get("question") or "未命名问题"
        chunk_index = (hit.get("metadata") or {}).get("chunk_index")
        header = f"[{index}] {question}" + (f" chunk {chunk_index}" if chunk_index is not None else "")
        text = str(hit.get("text") or "")
        block = f"{header}\n{text[:900]}"
        if total + len(block) > max_chars:
            break
        total += len(block)
        lines.append(block)
    return "\n\n".join(lines)


def dense_only_search(db: Any, case: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    from app.core.settings import settings
    from app.services.knowledge_rag_service import _hits_from_qdrant_points, rewrite_technical_queries
    from app.tools.embeddings.provider import embed_text
    from app.tools.retrievers.qdrant_retriever import search_similar_points

    del db
    query_plan = rewrite_technical_queries(str(case.get("question") or ""))
    merged: dict[str, dict[str, Any]] = {}
    for query in query_plan["queries"]:
        vector = embed_text(query)
        points = search_similar_points(collection_name=settings.qdrant_knowledge_collection, vector=vector, limit=max(limit * 4, 12))
        for hit in _hits_from_qdrant_points(points, retrieval_query=query):
            key = f"{hit.metadata.get('document_id')}:{hit.metadata.get('chunk_index')}" if hit.metadata.get("document_id") else hit.chunk_id
            current = merged.get(key)
            if current is None or float(hit.score) > float(current.get("score") or 0):
                merged[key] = hit.to_dict()
    return sorted(merged.values(), key=lambda item: float(item.get("score") or 0), reverse=True)[:limit]


def bm25_only_search(db: Any, case: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    from app.repositories.knowledge_repository import KnowledgeRepository
    from app.services.knowledge_rag_service import _hits_from_chunks, rewrite_technical_queries

    query_plan = rewrite_technical_queries(str(case.get("question") or ""))
    repository = KnowledgeRepository(db)
    merged: dict[str, dict[str, Any]] = {}
    for query in query_plan["queries"]:
        rows = repository.search_chunks_lexical(query=query, limit=max(limit * 4, 12))
        for hit in _hits_from_chunks(rows, retrieval_query=query):
            key = f"{hit.metadata.get('document_id')}:{hit.metadata.get('chunk_index')}"
            current = merged.get(key)
            if current is None or float(hit.metadata.get("bm25_score") or hit.score or 0) > float((current.get("metadata") or {}).get("bm25_score") or current.get("score") or 0):
                merged[key] = hit.to_dict()
    return sorted(
        merged.values(),
        key=lambda item: float((item.get("metadata") or {}).get("bm25_score") or item.get("score") or 0),
        reverse=True,
    )[:limit]


def hybrid_search(db: Any, case: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    from app.services.knowledge_rag_service import KnowledgeRagService

    service = KnowledgeRagService(db)
    result = service.search(str(case.get("question") or ""), limit=limit, min_score=0.0)
    return list(result.get("hits") or [])


def evaluate_retrieval_ablation(cases: list[dict[str, Any]], *, db: Any, top_k: int) -> dict[str, Any]:
    modes: dict[str, Callable[[Any, dict[str, Any], int], list[dict[str, Any]]]] = {
        "dense_only": dense_only_search,
        "bm25_only": bm25_only_search,
        "hybrid_rerank": hybrid_search,
    }
    return {
        "case_count": len(cases),
        "modes": {
            mode_name: _retrieval_only_summary(
                evaluate_cases(
                    cases,
                    search_fn=lambda case, limit, mode_fn=mode_fn: mode_fn(db, case, limit),
                    answer_fn=None,
                    top_k=top_k,
                ),
                top_k=top_k,
            )
            for mode_name, mode_fn in modes.items()
        },
    }


async def generate_answer_with_provider(case: dict[str, Any], hits: list[dict[str, Any]]) -> str:
    from app.agents.supervisor import SupervisorAgent
    from app.core.providers.factory import get_provider

    context = pack_contexts(hits)
    provider = get_provider()
    question = str(case.get("question") or "")
    prompt = (
        f"问题：{question}\n\n"
        f"知识库上下文：\n{context or '未检索到直接上下文'}\n\n"
        "请基于知识库上下文回答。若上下文不足，请明确说明，不要编造。"
    )
    return await provider.generate(
        prompt,
        system_prompt=SupervisorAgent().plan_turn(message=question, history=[], tool_context={}).system_prompt,
        temperature=0.1,
        max_tokens=700,
    )


def main() -> int:
    from app.core.database import session_local
    from app.services.knowledge_rag_service import KnowledgeRagService

    parser = argparse.ArgumentParser(description="Evaluate InternAgent knowledge RAG quality.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="Path to rag_eval_cases.jsonl")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Output markdown report path")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--generate-answers", action="store_true", help="Call the configured Gemma provider for answer evaluation")
    parser.add_argument("--ablation", action="store_true", help="Compare dense-only, BM25-only, and hybrid-rerank retrieval.")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    with session_local() as db:
        if args.ablation:
            ablation = evaluate_retrieval_ablation(cases, db=db, top_k=args.top_k)
            report = render_ablation_markdown_report(ablation, dataset_name=Path(args.cases).name)
            Path(args.report).write_text(report, encoding="utf-8")
            print(report)
            return 0

        service = KnowledgeRagService(db)

        def search_fn(case: dict[str, Any], limit: int) -> list[dict[str, Any]]:
            query = str(case.get("question") or "")
            result = service.search(query, limit=limit, min_score=0.0)
            return list(result.get("hits") or [])

        def answer_fn(case: dict[str, Any], hits: list[dict[str, Any]]) -> str:
            if args.generate_answers:
                return asyncio.run(generate_answer_with_provider(case, hits))
            return str(case.get("answer") or "")

        summary = evaluate_cases(cases, search_fn=search_fn, answer_fn=answer_fn, top_k=args.top_k)

    report = render_markdown_report(summary, dataset_name=Path(args.cases).name)
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    return 0


def _first_correct_rank(hits: list[dict[str, Any]], expected_keywords: list[str]) -> int | None:
    for index, hit in enumerate(hits, 1):
        if _hit_matches_expected_keywords(hit, expected_keywords):
            return index
    return None


def _hit_matches_expected_keywords(hit: dict[str, Any], expected_keywords: list[str]) -> bool:
    if not expected_keywords:
        return False
    text = " ".join(
        [
            str(hit.get("question") or ""),
            str(hit.get("text") or ""),
            " ".join(str(item) for item in hit.get("section_path") or []),
        ]
    )
    return _keyword_coverage(text, expected_keywords) >= 0.6


def _context_precision_at_k(hits: list[dict[str, Any]], expected_keywords: list[str], k: int) -> float:
    selected = hits[:k]
    if not selected:
        return 0.0
    matches = sum(1 for hit in selected if _hit_matches_expected_keywords(hit, expected_keywords))
    return round(matches / k, 2)


def _keyword_coverage(text: str, keywords: list[str]) -> float:
    normalized = _normalize(text)
    hits = sum(1 for keyword in keywords if _normalize(keyword) in normalized)
    return hits / max(len(keywords), 1)


def _phrase_matches(text: str, phrase: str) -> bool:
    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return False
    if normalized_phrase in normalized_text:
        return True
    terms = [term for term in re.split(r"[，,、\s；;。()（）]+", phrase) if len(term.strip()) >= 2]
    if not terms:
        return False
    return _keyword_coverage(text, terms) >= 0.65


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value).lower())


def _mean(values: Iterable[float | bool]) -> float:
    items = [float(value) for value in values]
    return round(sum(items) / max(len(items), 1), 2)


def _failure_summary(row: dict[str, Any]) -> str | None:
    reasons: list[str] = []
    if not row.get("recall_at_5"):
        reasons.append("correct chunk not found in top 5")
    elif row.get("correct_rank") and row["correct_rank"] > 3:
        reasons.append(f"correct chunk ranked at {row['correct_rank']}")
    if row.get("answer_point_coverage", 0) < 0.75:
        reasons.append(f"answer coverage {row.get('answer_point_coverage')}")
    if row.get("hallucination_count", 0) > 0:
        reasons.append(f"hallucination count {row['hallucination_count']}")
    if not reasons:
        return None
    return f"{row.get('id')}: {', '.join(reasons)}"


def _retrieval_only_summary(summary: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    summary = dict(summary)
    summary["failed_cases"] = [
        failure
        for row in summary.get("cases", [])
        if (failure := _retrieval_failure_summary(row, top_k=top_k))
    ]
    return summary


def _retrieval_failure_summary(row: dict[str, Any], *, top_k: int) -> str | None:
    recall_key = f"recall_at_{top_k}"
    if not row.get(recall_key):
        return f"{row.get('id')}: correct chunk not found in top {top_k}"
    if row.get("correct_rank") and row["correct_rank"] > 3:
        return f"{row.get('id')}: correct chunk ranked at {row['correct_rank']}"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
