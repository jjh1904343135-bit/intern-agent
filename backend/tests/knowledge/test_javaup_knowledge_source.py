from __future__ import annotations

from app.services.javaup_knowledge_source import collect_local_javaup_markdowns, select_javaup_markdown_paths
from app.services.knowledge_markdown import chunk_markdown_document


def test_select_javaup_markdown_paths_keeps_curated_interview_docs() -> None:
    tree_paths = [
        "README.md",
        "docs/06-基础内功/01-操作系统/01.进程线程与协程.md",
        "docs/11-数据库/01-MySQL/12-MySQL索引/21.MySQL索引失效问题排查.md",
        "docs/11-数据库/03-Oracle/01.Oracle索引技术全面解析.md",
        "docs/16-框架中间件/23-Kafka/02.Kafka消息可靠性保障机制.md",
        "docs/21-进阶设计与性能优化/04-限流与熔断/01.限流算法原理与实现.md",
    ]

    selected = select_javaup_markdown_paths(tree_paths)

    assert "docs/06-基础内功/01-操作系统/01.进程线程与协程.md" in selected
    assert "docs/11-数据库/01-MySQL/12-MySQL索引/21.MySQL索引失效问题排查.md" in selected
    assert "docs/16-框架中间件/23-Kafka/02.Kafka消息可靠性保障机制.md" in selected
    assert "docs/21-进阶设计与性能优化/04-限流与熔断/01.限流算法原理与实现.md" in selected
    assert "docs/11-数据库/03-Oracle/01.Oracle索引技术全面解析.md" not in selected
    assert selected == sorted(selected, key=selected.index)


def test_collect_local_javaup_markdowns_uses_downloaded_files_without_network(tmp_path) -> None:
    repo_path = "docs/16-框架中间件/23-Kafka/02.Kafka消息可靠性保障机制.md"
    local_path = tmp_path / "16-框架中间件" / "23-Kafka" / "02.Kafka消息可靠性保障机制.md"
    local_path.parent.mkdir(parents=True)
    local_path.write_text("# Kafka 消息可靠性\n\nacks、副本、ISR 和重试。", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        """
{
  "source": "shining-stars-l/javaup",
  "files": [
    {
      "repo_path": "docs/16-框架中间件/23-Kafka/02.Kafka消息可靠性保障机制.md",
      "source_url": "https://github.com/shining-stars-l/javaup/blob/master/docs/16-%E6%A1%86%E6%9E%B6%E4%B8%AD%E9%97%B4%E4%BB%B6/23-Kafka/02.Kafka%E6%B6%88%E6%81%AF%E5%8F%AF%E9%9D%A0%E6%80%A7%E4%BF%9D%E9%9A%9C%E6%9C%BA%E5%88%B6.md",
      "raw_url": "https://raw.githubusercontent.com/shining-stars-l/javaup/master/docs/16-%E6%A1%86%E6%9E%B6%E4%B8%AD%E9%97%B4%E4%BB%B6/23-Kafka/02.Kafka%E6%B6%88%E6%81%AF%E5%8F%AF%E9%9D%A0%E6%80%A7%E4%BF%9D%E9%9A%9C%E6%9C%BA%E5%88%B6.md",
      "local_path": "D:/stale/host/path/02.Kafka消息可靠性保障机制.md",
      "bytes": 20
    }
  ]
}
""",
        encoding="utf-8",
    )

    local_files = collect_local_javaup_markdowns(dest_dir=tmp_path)

    assert len(local_files) == 1
    assert local_files[0]["repo_path"] == repo_path
    assert local_files[0]["local_path"] == str(local_path)
    assert local_files[0]["bytes"] == local_path.stat().st_size


def test_chunk_markdown_document_preserves_source_metadata_and_headings() -> None:
    markdown = """
# MySQL 索引失效问题排查

## 最左前缀原则

联合索引需要按照最左前缀匹配。如果跳过第一列，后续列通常无法充分使用索引。

## 函数与隐式转换

对索引列使用函数、发生隐式类型转换、like 前置通配符，都可能导致索引失效。
"""

    chunks = chunk_markdown_document(
        markdown,
        source_file="21.MySQL索引失效问题排查.md",
        repo_path="docs/11-数据库/01-MySQL/12-MySQL索引/21.MySQL索引失效问题排查.md",
        source_url="https://github.com/shining-stars-l/javaup/blob/master/docs/example.md",
        target_chars=120,
        overlap_chars=20,
    )

    assert len(chunks) >= 2
    assert chunks[0].section_path == ["MySQL 索引失效问题排查", "最左前缀原则"]
    assert chunks[0].metadata["source_repo"] == "shining-stars-l/javaup"
    assert chunks[0].metadata["source_url"].startswith("https://github.com/shining-stars-l/javaup")
    assert chunks[0].metadata["repo_path"].endswith("21.MySQL索引失效问题排查.md")
    assert chunks[0].metadata["content_type"] == "javaup_markdown"
    assert chunks[0].metadata["chunk_strategy"] == "markdown_heading"
    assert "MySQL" in chunks[0].metadata["keywords"]
    assert chunks[0].metadata["topic"] == "MySQL"
