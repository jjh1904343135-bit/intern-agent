from __future__ import annotations

from dataclasses import dataclass


SIMPLE_ANSWER = "simple_answer"
AGENTIC_TASK = "agentic_task"


@dataclass(frozen=True)
class ChatComplexityClassifier:
    """Separate direct answers from tasks that need planning or tools."""

    def classify(self, message: str) -> str:
        text = (message or "").strip()
        lowered = text.lower()
        if not text:
            return SIMPLE_ANSWER

        # 命中这些词时，大概率需要读取项目事实或调用工具，不能只靠模型闲聊回答。
        agentic_tokens = [
            "岗位",
            "职位",
            "实习",
            "投递",
            "找工作",
            "招聘",
            "校招",
            "社招",
            "搜索",
            "搜一下",
            "查一下",
            "推荐",
            "开发岗",
            "工程师",
            "大厂",
            "保存",
            "简历",
            "评分",
            "面试",
            "结合",
            "根据我的",
            "北京",
            "上海",
            "腾讯",
            "阿里",
            "字节",
            "jvm",
            "mysql",
            "redis",
            "spring",
            "并发",
            "线程",
            "java",
            "后端",
        ]
        if any(token in lowered for token in agentic_tokens):
            return AGENTIC_TASK

        # 职业助手里的短问候、身份/功能说明、使用帮助类问题，直接走 simple_answer。
        simple_patterns = ["你好", "你是谁", "你能做什么", "怎么用", "如何使用", "使用说明", "帮我做什么", "介绍一下你自己", "有什么功能", "帮我解释一下"]
        if len(text) <= 40 and any(pattern in lowered for pattern in simple_patterns):
            return SIMPLE_ANSWER
        if len(text) <= 20:
            return SIMPLE_ANSWER
        return AGENTIC_TASK
