from __future__ import annotations

from app.agents.chat.complexity import ChatComplexityClassifier


def test_chat_complexity_classifier_routes_small_talk_and_basic_explanations_to_simple_answer() -> None:
    classifier = ChatComplexityClassifier()

    assert classifier.classify("你好") == "simple_answer"
    assert classifier.classify("你是谁") == "simple_answer"
    assert classifier.classify("你能做什么") == "simple_answer"
    assert classifier.classify("帮我解释一下 RAG") == "simple_answer"


def test_chat_complexity_classifier_routes_tool_and_rag_work_to_agentic_task() -> None:
    classifier = ChatComplexityClassifier()

    assert classifier.classify("帮我找北京 Java 后端实习并结合简历分析") == "agentic_task"
    assert classifier.classify("帮我搜一下美团开发岗") == "agentic_task"
    assert classifier.classify("讲一下 Java JVM 内存模型") == "agentic_task"
    assert classifier.classify("根据我的默认简历保存几个腾讯岗位到投递清单") == "agentic_task"
