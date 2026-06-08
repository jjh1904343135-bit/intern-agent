from __future__ import annotations

from app.services.knowledge_ingestion import clean_knowledge_paragraphs, chunk_interview_notes
from app.repositories.knowledge_repository import bm25_scores
from app.services.knowledge_rag_service import (
    KnowledgeSearchHit,
    assess_context_sufficiency,
    merge_and_rerank_hits,
    pack_knowledge_context,
    rewrite_technical_queries,
)


def test_cleaning_and_qa_chunking_adds_quality_metadata() -> None:
    paragraphs = clean_knowledge_paragraphs(
        [
            "  Java 基础篇  ",
            "第 1 页",
            "1、 MySQL 索引失效有哪些情况？",
            "对索引列使用函数、隐式类型转换、like 前置通配符都可能导致索引失效。",
            "对索引列使用函数、隐式类型转换、like 前置通配符都可能导致索引失效。",
            "2、 JVM 运行时内存区域怎么讲？",
            "包含堆、虚拟机栈、本地方法栈、方法区和程序计数器。",
        ]
    )

    chunks = chunk_interview_notes(paragraphs, source_file="10万字总结.docx", target_chars=500)

    assert "第 1 页" not in paragraphs
    assert paragraphs.count("对索引列使用函数、隐式类型转换、like 前置通配符都可能导致索引失效。") == 1
    assert chunks[0].question == "1、 MySQL 索引失效有哪些情况？"
    assert chunks[0].metadata["chunk_strategy"] == "qa"
    assert chunks[0].metadata["topic"] == "MySQL"
    assert {"MySQL", "索引失效", "like"}.issubset(set(chunks[0].metadata["keywords"]))
    assert chunks[0].metadata["chunk_quality_score"] >= 0.7


def test_query_rewrite_expands_oral_technical_question() -> None:
    plan = rewrite_technical_queries("mysql 为什么有时候索引用不上")

    assert plan["original_query"] == "mysql 为什么有时候索引用不上"
    assert "MySQL 索引失效 常见原因" in plan["queries"]
    assert {"MySQL", "索引失效", "最左前缀", "隐式类型转换"}.issubset(set(plan["keywords"]))
    assert len(plan["queries"]) >= 3


def test_hybrid_rerank_prefers_keyword_complete_chunk_over_dense_only() -> None:
    dense_hits = [
        KnowledgeSearchHit(
            chunk_id="dense-weak",
            score=0.91,
            text="MySQL 查询优化需要关注执行计划和慢 SQL。",
            question="MySQL 查询优化",
            section_path=["数据库"],
            source_file="10万字总结.docx",
            metadata={"chunk_index": 1, "chunk_quality_score": 0.7, "retrieval_channel": "dense"},
        )
    ]
    lexical_hits = [
        KnowledgeSearchHit(
            chunk_id="lexical-strong",
            score=0.62,
            text="MySQL 索引失效包括最左前缀不满足、对索引列使用函数、隐式类型转换、like 前置通配符和范围查询后的列无法继续充分使用索引。",
            question="MySQL 索引失效有哪些情况？",
            section_path=["数据库", "MySQL"],
            source_file="10万字总结.docx",
            metadata={"chunk_index": 2, "chunk_quality_score": 0.92, "retrieval_channel": "lexical"},
        )
    ]

    reranked = merge_and_rerank_hits(
        query="mysql 为什么索引用不上",
        query_keywords=["MySQL", "索引失效", "最左前缀", "函数", "隐式类型转换", "like"],
        dense_hits=dense_hits,
        lexical_hits=lexical_hits,
        limit=2,
    )

    assert reranked[0].chunk_id == "lexical-strong"
    assert reranked[0].metadata["retrieval_channel"] == "hybrid"
    assert reranked[0].metadata["keyword_coverage"] >= 0.8
    assert reranked[0].metadata["rerank_score"] > reranked[1].metadata["rerank_score"]


def test_bm25_scores_rank_keyword_complete_chunk_above_generic_chunk() -> None:
    tokens = ["Kafka", "acks", "副本", "ISR", "重试"]
    documents = [
        "Kafka 是常见消息队列，适合削峰填谷和异步解耦。",
        "Kafka 可靠性需要生产端 acks 和重试，Broker 侧依赖副本与 ISR，消费端需要正确提交 offset。",
    ]

    scores = bm25_scores(query_tokens=tokens, documents=documents)

    assert scores[1] > scores[0]
    assert scores[1] > 0


def test_context_packing_keeps_citations_and_marks_insufficient_context() -> None:
    weak_hit = KnowledgeSearchHit(
        chunk_id="weak",
        score=0.2,
        text="这段只说数据库优化，没有说 Redis 持久化。",
        question="数据库优化",
        section_path=["数据库"],
        source_file="10万字总结.docx",
        metadata={"chunk_index": 8, "rerank_score": 0.18, "keyword_coverage": 0.1},
    )

    packed = pack_knowledge_context([weak_hit], max_chars=300)
    sufficiency = assess_context_sufficiency(
        query="Redis RDB AOF 持久化区别",
        query_keywords=["Redis", "RDB", "AOF", "持久化"],
        hits=[weak_hit],
    )

    assert "参考知识 [1]" in packed["context"]
    assert packed["citations"][0]["chunk_index"] == 8
    assert sufficiency["sufficient"] is False
    assert sufficiency["reason"] in {"low_keyword_coverage", "low_top_score", "empty_context"}
