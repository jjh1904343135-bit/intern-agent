"""Markdown cleaning and chunking for external interview-note corpora."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


TECH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Java": ("java", "jvm", "juc", "classloader", "类加载", "垃圾回收"),
    "JVM": ("jvm", "堆", "虚拟机栈", "方法区", "元空间", "gc", "jstat", "jmap"),
    "MySQL": ("mysql", "索引", "事务", "mvcc", "innodb", "sql", "死锁", "隔离级别", "执行计划"),
    "Redis": ("redis", "rdb", "aof", "缓存", "持久化", "跳表", "分布式锁", "redisson"),
    "Spring": ("spring", "bean", "ioc", "aop", "事务传播", "transactional", "循环依赖"),
    "SpringBoot": ("springboot", "自动配置", "starter", "启动流程", "条件装配"),
    "MyBatis": ("mybatis", "一级缓存", "二级缓存", "动态sql", "拦截器", "sql注入"),
    "Kafka": ("kafka", "partition", "offset", "rebalance", "消息可靠性"),
    "RocketMQ": ("rocketmq", "事务消息", "顺序消息", "消费重试"),
    "Netty": ("netty", "eventloop", "bytebuf", "零拷贝", "粘包", "拆包"),
    "Dubbo": ("dubbo", "rpc", "spi", "负载均衡", "服务治理"),
    "Elasticsearch": ("elasticsearch", "倒排索引", "深度分页", "分片"),
    "分布式": ("分布式", "一致性", "cap", "raft", "tcc", "seata", "分库分表"),
    "微服务": ("微服务", "注册中心", "网关", "熔断", "限流", "nacos", "springcloud"),
    "系统设计": ("高并发", "限流", "缓存", "布隆过滤器", "延迟队列", "ddd", "领域驱动"),
    "RAG": ("rag", "向量", "embedding", "检索增强", "rerank"),
    "Agent": ("agent", "工具调用", "mcp", "规划", "记忆"),
}


@dataclass(frozen=True)
class MarkdownKnowledgeChunk:
    text: str
    section_path: list[str]
    question: str | None
    chunk_index: int
    source_file: str
    repo_path: str
    source_url: str
    chunk_strategy: str = "markdown_heading"
    extra_metadata: dict = field(default_factory=dict)

    @property
    def token_count(self) -> int:
        return max(1, len(self.text) // 2)

    @property
    def keywords(self) -> list[str]:
        return extract_markdown_keywords(" ".join([*(self.section_path or []), self.question or "", self.text]))

    @property
    def topic(self) -> str:
        return infer_markdown_topic(section_path=self.section_path, question=self.question, text=self.text)

    @property
    def quality_score(self) -> float:
        score = 0.35
        if 160 <= len(self.text) <= 1400:
            score += 0.25
        elif len(self.text) > 80:
            score += 0.12
        if self.section_path:
            score += 0.16
        if self.question:
            score += 0.12
        if self.keywords:
            score += min(0.17, len(self.keywords) * 0.035)
        return round(max(0.05, min(score, 1.0)), 2)

    @property
    def metadata(self) -> dict:
        return {
            "source_repo": "shining-stars-l/javaup",
            "source_url": self.source_url,
            "repo_path": self.repo_path,
            "source_file": self.source_file,
            "section_path": self.section_path,
            "question": self.question,
            "chunk_index": self.chunk_index,
            "content_type": "javaup_markdown",
            "chunk_strategy": self.chunk_strategy,
            "topic": self.topic,
            "keywords": self.keywords,
            "chunk_quality_score": self.quality_score,
            **self.extra_metadata,
        }


def chunk_markdown_document(
    markdown: str,
    *,
    source_file: str,
    repo_path: str,
    source_url: str,
    target_chars: int = 900,
    overlap_chars: int = 120,
) -> list[MarkdownKnowledgeChunk]:
    """Chunk a Markdown article by heading and question-like anchors."""

    chunks: list[MarkdownKnowledgeChunk] = []
    section_stack: list[tuple[int, str]] = []
    current_question: str | None = None
    buffer: list[str] = []
    in_code_fence = False

    def section_path() -> list[str]:
        return [title for _, title in section_stack if title]

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(item for item in buffer if item).strip()
        if text:
            chunks.extend(
                _split_text_to_chunks(
                    text=text,
                    source_file=source_file,
                    repo_path=repo_path,
                    source_url=source_url,
                    section_path=section_path(),
                    question=current_question,
                    start_index=len(chunks),
                    target_chars=target_chars,
                    overlap_chars=overlap_chars,
                )
            )
        buffer = []

    for raw_line in _strip_front_matter(markdown).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue

        if not in_code_fence:
            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading:
                flush()
                level = len(heading.group(1))
                title = clean_markdown_line(heading.group(2))
                section_stack = [(old_level, old_title) for old_level, old_title in section_stack if old_level < level]
                section_stack.append((level, title))
                current_question = title if _looks_like_question(title) else None
                continue

        cleaned = clean_markdown_line(stripped)
        if not cleaned or _is_noise_markdown_line(cleaned):
            continue
        if _looks_like_question(cleaned):
            flush()
            current_question = cleaned
            buffer = [cleaned]
            continue
        buffer.append(cleaned)
        if sum(len(item) for item in buffer) >= target_chars:
            flush()
            if current_question:
                buffer = [current_question]

    flush()
    return [MarkdownKnowledgeChunk(**{**chunk.__dict__, "chunk_index": index}) for index, chunk in enumerate(chunks)]


def clean_markdown_line(line: str) -> str:
    line = re.sub(r"<!--.*?-->", "", line)
    line = re.sub(r"!\[[^\]]*]\([^)]+\)", "", line)
    line = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", line)
    line = line.replace("`", "")
    line = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", line)
    if "|" in line:
        line = " ".join(part.strip() for part in line.strip("|").split("|") if part.strip())
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def extract_markdown_keywords(text: str) -> list[str]:
    normalized = text.lower()
    keywords: list[str] = []
    for canonical, aliases in TECH_KEYWORDS.items():
        if canonical.lower() in normalized or any(alias.lower() in normalized for alias in aliases):
            keywords.append(canonical)

    phrase_rules = [
        ("索引失效", ("索引失效", "索引用不上", "最左前缀", "隐式类型转换", "前置通配符")),
        ("事务隔离", ("事务隔离", "读已提交", "可重复读", "幻读", "mvcc")),
        ("分布式锁", ("分布式锁", "redlock", "watchdog", "自动续期")),
        ("缓存一致性", ("缓存一致性", "双写", "延迟双删", "缓存穿透", "缓存雪崩")),
        ("零拷贝", ("零拷贝", "sendfile", "mmap", "direct buffer")),
        ("限流熔断", ("限流", "熔断", "令牌桶", "漏桶", "降级")),
    ]
    for canonical, aliases in phrase_rules:
        if any(alias.lower() in normalized for alias in aliases):
            keywords.append(canonical)
    return list(dict.fromkeys(keywords))[:14]


def infer_markdown_topic(*, section_path: list[str], question: str | None, text: str) -> str:
    joined = " ".join([*section_path, question or "", text])
    keywords = extract_markdown_keywords(joined)
    preferred_order = [
        "MySQL",
        "Redis",
        "Spring",
        "SpringBoot",
        "MyBatis",
        "JVM",
        "Kafka",
        "RocketMQ",
        "Netty",
        "Dubbo",
        "Elasticsearch",
        "分布式",
        "微服务",
        "系统设计",
        "Java",
        "RAG",
        "Agent",
    ]
    for topic in preferred_order:
        if topic in keywords:
            return topic
    return section_path[0] if section_path else "Java八股"


def _split_text_to_chunks(
    *,
    text: str,
    source_file: str,
    repo_path: str,
    source_url: str,
    section_path: list[str],
    question: str | None,
    start_index: int,
    target_chars: int,
    overlap_chars: int,
) -> list[MarkdownKnowledgeChunk]:
    if len(text) <= target_chars:
        return [
            MarkdownKnowledgeChunk(
                text=text,
                section_path=section_path,
                question=question,
                chunk_index=start_index,
                source_file=source_file,
                repo_path=repo_path,
                source_url=source_url,
            )
        ]

    result: list[MarkdownKnowledgeChunk] = []
    cursor = 0
    while cursor < len(text):
        end = _semantic_boundary(text, start=cursor, preferred_end=min(len(text), cursor + target_chars))
        slice_text = text[cursor:end].strip()
        if slice_text:
            result.append(
                MarkdownKnowledgeChunk(
                    text=slice_text,
                    section_path=section_path,
                    question=question,
                    chunk_index=start_index + len(result),
                    source_file=source_file,
                    repo_path=repo_path,
                    source_url=source_url,
                )
            )
        if end >= len(text):
            break
        cursor = max(0, end - overlap_chars)
    return result


def _semantic_boundary(text: str, *, start: int, preferred_end: int) -> int:
    if preferred_end >= len(text):
        return len(text)
    window = text[start:preferred_end]
    candidates = [window.rfind(mark) for mark in ["\n", "。", "；", ";", "."]]
    best = max(candidates)
    if best >= int(len(window) * 0.55):
        return start + best + 1
    return preferred_end


def _strip_front_matter(markdown: str) -> str:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("---\n"):
        end = normalized.find("\n---\n", 4)
        if end != -1:
            return normalized[end + 5 :]
    return normalized


def _looks_like_question(text: str) -> bool:
    if text.endswith(("?", "？")):
        return True
    if len(text) > 120:
        return False
    lowered = text.lower()
    markers = ("是什么", "为什么", "怎么", "如何", "哪些", "区别", "原理", "流程", "机制", "场景", "失效", "详解")
    technical = ("java", "jvm", "mysql", "redis", "spring", "kafka", "rocketmq", "netty", "dubbo")
    return any(marker in text for marker in markers) and (
        any(item in lowered for item in technical)
        or any(item in text for item in ("索引", "事务", "锁", "缓存", "分布式", "微服务", "线程", "内存"))
    )


def _is_noise_markdown_line(text: str) -> bool:
    if not text:
        return True
    if re.fullmatch(r"[-=]{3,}", text):
        return True
    if re.fullmatch(r":?-{2,}:?\s*", text):
        return True
    if text in {"目录", "返回目录", "Table of Contents"}:
        return True
    return False
