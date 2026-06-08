from __future__ import annotations

from evals.rag.eval_knowledge_rag import (
    evaluate_answer,
    evaluate_case,
    evaluate_cases,
    render_ablation_markdown_report,
    render_markdown_report,
)


def test_rag_eval_computes_recall_mrr_and_context_precision() -> None:
    case = {
        "id": "rag-mysql-index-001",
        "question": "MySQL 索引失效有哪些常见情况？",
        "expected_chunk_keywords": ["最左前缀", "函数", "隐式类型转换", "like", "范围查询"],
        "expected_answer_points": ["联合索引需要满足最左前缀"],
    }
    hits = [
        {"text": "MySQL explain 可以查看执行计划。", "score": 0.92, "question": "执行计划"},
        {"text": "索引失效常见原因：不满足最左前缀、对索引列使用函数、隐式类型转换、like 前置通配符、范围查询后续列可能无法使用索引。", "score": 0.88, "question": "索引失效"},
        {"text": "Redis 持久化包含 RDB 和 AOF。", "score": 0.7, "question": "Redis"},
    ]

    result = evaluate_case(case, hits=hits, answer="联合索引需要满足最左前缀。", top_k_values=(3, 5))

    assert result["correct_rank"] == 2
    assert result["recall_at_3"] is True
    assert result["recall_at_5"] is True
    assert result["mrr"] == 0.5
    assert result["context_precision_at_3"] == 0.33


def test_rag_eval_scores_answer_point_coverage_grounding_and_hallucinations() -> None:
    case = {
        "id": "rag-mysql-index-001",
        "expected_answer_points": [
            "联合索引需要满足最左前缀",
            "对索引列使用函数可能导致索引失效",
            "隐式类型转换可能导致索引失效",
            "like 前置通配符可能导致索引失效",
        ],
        "forbidden_answer_points": ["保证所有范围查询都会失效"],
    }
    contexts = [
        "联合索引需要满足最左前缀。对索引列使用函数可能导致索引失效。隐式类型转换可能导致索引失效。like 前置通配符可能导致索引失效。",
    ]
    answer = "联合索引需要满足最左前缀；对索引列使用函数可能导致索引失效；隐式类型转换可能导致索引失效。另外保证所有范围查询都会失效。"

    result = evaluate_answer(case, answer=answer, contexts=contexts)

    assert result["answer_point_coverage"] == 0.75
    assert result["grounded"] is True
    assert result["hallucination_count"] == 1


def test_rag_eval_aggregates_cases_and_renders_markdown_report() -> None:
    cases = [
        {
            "id": "rag-1",
            "question": "JVM 内存区域有哪些？",
            "expected_chunk_keywords": ["堆", "虚拟机栈", "程序计数器"],
            "expected_answer_points": ["JVM 运行时数据区包含堆", "程序计数器是线程私有"],
        },
        {
            "id": "rag-2",
            "question": "Redis 持久化方式？",
            "expected_chunk_keywords": ["RDB", "AOF"],
            "expected_answer_points": ["Redis 持久化包含 RDB", "AOF 记录写命令"],
        },
    ]

    def fake_search(case: dict, limit: int) -> list[dict]:
        if case["id"] == "rag-1":
            return [{"text": "JVM 运行时数据区包含堆、虚拟机栈、程序计数器。程序计数器是线程私有。", "score": 0.9}]
        return [{"text": "Redis 持久化包含 RDB 和 AOF。AOF 记录写命令。", "score": 0.88}]

    def fake_generate(case: dict, hits: list[dict]) -> str:
        return hits[0]["text"]

    summary = evaluate_cases(cases, search_fn=fake_search, answer_fn=fake_generate, top_k=5)
    report = render_markdown_report(summary, dataset_name="rag_eval_cases.jsonl")

    assert summary["case_count"] == 2
    assert summary["retrieval"]["recall_at_3"] == 1.0
    assert summary["retrieval"]["recall_at_5"] == 1.0
    assert summary["retrieval"]["mrr"] == 1.0
    assert summary["generation"]["grounded_answer_rate"] == 1.0
    assert "RAG Eval Report" in report
    assert "Recall@3: 1.00" in report


def test_rag_eval_renders_ablation_report() -> None:
    ablation = {
        "case_count": 2,
        "modes": {
            "dense_only": {"retrieval": {"recall_at_3": 0.5, "recall_at_5": 0.5, "mrr": 0.25}, "failed_cases": ["rag-2"]},
            "bm25_only": {"retrieval": {"recall_at_3": 1.0, "recall_at_5": 1.0, "mrr": 1.0}, "failed_cases": []},
            "hybrid_rerank": {"retrieval": {"recall_at_3": 1.0, "recall_at_5": 1.0, "mrr": 1.0}, "failed_cases": []},
        },
    }

    report = render_ablation_markdown_report(ablation, dataset_name="rag_eval_cases.jsonl")

    assert "RAG Ablation Eval Report" in report
    assert "| dense_only | 0.50 | 0.50 | 0.25 | 1 |" in report
    assert "| bm25_only | 1.00 | 1.00 | 1.00 | 0 |" in report
