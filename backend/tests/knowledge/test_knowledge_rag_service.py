from __future__ import annotations

from app.services.knowledge_rag_service import KnowledgeSearchHit, KnowledgeSearchResult, KnowledgeRagService


def test_knowledge_search_result_builds_prompt_context() -> None:
    result = KnowledgeSearchResult(
        available=True,
        query="JVM 内存模型",
        total=2,
        hits=[
            KnowledgeSearchHit(
                chunk_id="chunk-1",
                score=0.88,
                text="JVM 内存区域包含堆、虚拟机栈、本地方法栈、方法区和程序计数器。",
                question="1、 JVM 内存模型是什么",
                section_path=["基础篇", "JVM"],
                source_file="10万字总结.docx",
                metadata={"chunk_index": 0},
            ),
            KnowledgeSearchHit(
                chunk_id="chunk-2",
                score=0.81,
                text="堆主要存放对象实例，栈保存局部变量表、操作数栈和方法出口。",
                question="2、 堆和栈有什么区别",
                section_path=["基础篇", "JVM"],
                source_file="10万字总结.docx",
                metadata={"chunk_index": 1},
            ),
        ],
        source="knowledge_rag",
        fallback_notice=None,
    )

    context = KnowledgeRagService.format_prompt_context(result)

    assert "八股知识库参考" in context
    assert "1、 JVM 内存模型是什么" in context
    assert "堆主要存放对象实例" in context
    assert "只基于这些片段回答" in context


def test_knowledge_search_result_marks_empty_retrieval() -> None:
    result = KnowledgeSearchResult(
        available=True,
        query="不存在的问题",
        total=0,
        hits=[],
        source="knowledge_rag",
        fallback_notice="知识库未检索到直接片段",
    )

    assert KnowledgeRagService.format_prompt_context(result) == "知识库未检索到直接片段。"
