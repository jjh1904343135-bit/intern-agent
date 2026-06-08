"""Curated JavaUp Markdown source selection and download helpers."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import quote
from urllib.request import Request, urlopen


JAVAUP_REPO = "shining-stars-l/javaup"
JAVAUP_BRANCH = "master"
JAVAUP_TREE_API = f"https://api.github.com/repos/{JAVAUP_REPO}/git/trees/{JAVAUP_BRANCH}?recursive=1"
JAVAUP_BLOB_BASE = f"https://github.com/{JAVAUP_REPO}/blob/{JAVAUP_BRANCH}"
JAVAUP_RAW_BASE = f"https://raw.githubusercontent.com/{JAVAUP_REPO}/{JAVAUP_BRANCH}"


CURATED_JAVAUP_PATHS: tuple[str, ...] = (
    # 基础内功：操作系统 / 网络 / 数据结构，只保留后端面试高频主题。
    "docs/06-基础内功/01-操作系统/01.进程线程与协程.md",
    "docs/06-基础内功/01-操作系统/02.进程通信与调度.md",
    "docs/06-基础内功/01-操作系统/03.内存管理与虚拟地址.md",
    "docs/06-基础内功/01-操作系统/06.IO优化与零拷贝.md",
    "docs/06-基础内功/02-网络/02.TCP协议深入解析.md",
    "docs/06-基础内功/02-网络/03.HTTP协议演进与特性.md",
    "docs/06-基础内功/03-数据结构/01.线性数据结构.md",
    "docs/06-基础内功/03-数据结构/02.树形结构基础.md",
    # 数据库：MySQL / Redis 面试核心，不纳入 Oracle 等非当前主线内容。
    "docs/11-数据库/01-MySQL/10-MySQL锁/08.MySQL行级锁详解.md",
    "docs/11-数据库/01-MySQL/10-MySQL锁/10.MySQL死锁问题分析与解决.md",
    "docs/11-数据库/01-MySQL/11-MySQL事务/11.MySQL事务机制与ACID特性.md",
    "docs/11-数据库/01-MySQL/11-MySQL事务/13.MySQL事务隔离级别详解.md",
    "docs/11-数据库/01-MySQL/11-MySQL事务/14.MySQL隔离级别实现原理.md",
    "docs/11-数据库/01-MySQL/12-MySQL索引/18.MySQL索引基础与底层原理.md",
    "docs/11-数据库/01-MySQL/12-MySQL索引/20.MySQL联合索引与查询优化.md",
    "docs/11-数据库/01-MySQL/12-MySQL索引/21.MySQL索引失效问题排查.md",
    "docs/11-数据库/01-MySQL/13-MySQL慢SQL调优/23.执行计划深度解析与实战.md",
    "docs/11-数据库/01-MySQL/13-MySQL慢SQL调优/26.SQL性能调优全面指南.md",
    "docs/11-数据库/01-MySQL/14-MySQL特征/01.MySQL架构与执行流程.md",
    "docs/11-数据库/01-MySQL/14-MySQL特征/05.MySQL存储引擎与高级特性.md",
    "docs/11-数据库/02-Redis/01-Redis基础与数据类型/01.Redis数据类型详解与应用场景.md",
    "docs/11-数据库/02-Redis/01-Redis基础与数据类型/03.Redis线程模型与性能优化.md",
    "docs/11-数据库/02-Redis/02-Redis持久化与内存/01.Redis持久化与数据安全.md",
    "docs/11-数据库/02-Redis/03-Redis集群与高可用/02.Redis集群架构与高可用方案.md",
    "docs/11-数据库/02-Redis/06-Redis分布式锁/01.Redis分布式锁实战指南.md",
    "docs/11-数据库/02-Redis/06-Redis分布式锁/03.Redisson分布式锁核心实现原理.md",
    "docs/11-数据库/02-Redis/07-Redis缓存一致性/01.Redis与数据库一致性保障方案.md",
    # 框架中间件：Spring / MyBatis / MQ / RPC / Netty / ES 高频八股。
    "docs/16-框架中间件/08-Spring/01.Spring核心概念详解.md",
    "docs/16-框架中间件/08-Spring/02.Bean生命周期与依赖注入.md",
    "docs/16-框架中间件/08-Spring/05.Spring循环依赖解决方案详解.md",
    "docs/16-框架中间件/08-Spring/10-Spring事务/06.Spring事务管理核心详解.md",
    "docs/16-框架中间件/08-Spring/10-Spring事务/09.Spring事务失效场景与解决方案.md",
    "docs/16-框架中间件/08-Spring/16-SpringBoot/12.SpringBoot自动配置原理深度剖析.md",
    "docs/16-框架中间件/08-Spring/16-SpringBoot/22.SpringBoot启动原理.md",
    "docs/16-框架中间件/09-Mybatis/02.MyBatis工作原理与核心组件.md",
    "docs/16-框架中间件/09-Mybatis/07.MyBatis缓存机制详解.md",
    "docs/16-框架中间件/21-SpringCloud/01.SpringCloud核心概念与架构.md",
    "docs/16-框架中间件/21-SpringCloud/05.Nacos架构与核心功能详解.md",
    "docs/16-框架中间件/23-Kafka/01.Kafka基础架构与核心概念.md",
    "docs/16-框架中间件/23-Kafka/02.Kafka消息可靠性保障机制.md",
    "docs/16-框架中间件/24-RocketMQ/02.RocketMQ消息可靠性保障机制.md",
    "docs/16-框架中间件/26-Elasticsearch/02.倒排索引原理与性能优势.md",
    "docs/16-框架中间件/27-Dubbo/02.Dubbo核心架构与调用流程.md",
    "docs/16-框架中间件/28-Netty/01.Netty核心架构与线程模型.md",
    "docs/16-框架中间件/28-Netty/03.Netty零拷贝技术详解.md",
    # 进阶设计：系统设计、分布式、缓存、事务和当前项目相关 RAG/Agent。
    "docs/21-进阶设计与性能优化/01-微服务相关/04.微服务治理与稳定性保障.md",
    "docs/21-进阶设计与性能优化/02-分布式相关理论/01.分布式系统一致性理论详解.md",
    "docs/21-进阶设计与性能优化/03-分布式id/01.分布式ID生成方案详解.md",
    "docs/21-进阶设计与性能优化/04-限流与熔断/01.限流算法原理与实现.md",
    "docs/21-进阶设计与性能优化/04-限流与熔断/04.高并发系统设计实践.md",
    "docs/21-进阶设计与性能优化/05-缓存的设计/04.多级缓存架构设计与实践.md",
    "docs/21-进阶设计与性能优化/06-布隆过滤器/01.布隆过滤器原理与实战应用.md",
    "docs/21-进阶设计与性能优化/10-问题故障解决/01.JVM诊断工具命令详解.md",
    "docs/21-进阶设计与性能优化/17-分库分表/01.分库分表核心概念与应用场景.md",
    "docs/21-进阶设计与性能优化/18-分布式事务/01.分布式事务基础概念与解决方案.md",
    "docs/21-进阶设计与性能优化/19-Seata/01.Seata分布式事务框架核心原理.md",
    "docs/21-进阶设计与性能优化/20-DDD/01.领域驱动设计核心思想与价值.md",
    "docs/21-进阶设计与性能优化/25-AI/03.RAG检索增强生成技术.md",
    "docs/21-进阶设计与性能优化/25-AI/04.AIAgent与工具调用协议.md",
)


def select_javaup_markdown_paths(tree_paths: Iterable[str], *, max_files: int | None = None) -> list[str]:
    """Return curated Java interview Markdown paths in stable priority order."""

    available = {path for path in tree_paths if path.endswith(".md")}
    selected = [path for path in CURATED_JAVAUP_PATHS if path in available]
    return selected[:max_files] if max_files else selected


def fetch_javaup_tree_paths() -> list[str]:
    request = Request(JAVAUP_TREE_API, headers={"User-Agent": "qingcheng-ai-rag"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed public GitHub API URL.
        payload = json.loads(response.read().decode("utf-8"))
    return [item["path"] for item in payload.get("tree", []) if item.get("type") == "blob"]


def collect_local_javaup_markdowns(*, dest_dir: Path, max_files: int | None = None) -> list[dict[str, str | int]]:
    """Return already downloaded curated JavaUp Markdown files.

    The container may not be able to reach GitHub, while the project already has a local
    `file/knowledge_sources/javaup` snapshot. Prefer that snapshot so ingestion remains
    reproducible and does not depend on network availability.
    """

    dest_root = dest_dir.resolve()
    manifest_entries = _read_local_manifest_entries(dest_root)
    repo_paths = [str(item.get("repo_path") or "") for item in manifest_entries if item.get("repo_path")]
    if not repo_paths:
        repo_paths = list(CURATED_JAVAUP_PATHS)

    selected = select_javaup_markdown_paths(repo_paths, max_files=max_files)
    entry_by_path = {str(item.get("repo_path")): item for item in manifest_entries if item.get("repo_path")}
    results: list[dict[str, str | int]] = []
    for repo_path in selected:
        manifest_entry = entry_by_path.get(repo_path) or {}
        local_path = _resolve_existing_local_path(dest_root=dest_root, repo_path=repo_path, manifest_entry=manifest_entry)
        if local_path is None:
            continue
        results.append(
            {
                "repo_path": repo_path,
                "source_url": str(manifest_entry.get("source_url") or source_url_for_path(repo_path)),
                "raw_url": str(manifest_entry.get("raw_url") or raw_url_for_path(repo_path)),
                "local_path": str(local_path),
                "bytes": local_path.stat().st_size,
            }
        )
    return results[:max_files] if max_files else results


def download_selected_javaup_markdowns(
    *,
    dest_dir: Path,
    paths: Iterable[str] | None = None,
    max_files: int | None = None,
) -> list[dict[str, str | int]]:
    tree_paths = list(paths) if paths is not None else fetch_javaup_tree_paths()
    selected = select_javaup_markdown_paths(tree_paths, max_files=max_files)
    dest_root = dest_dir.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, str | int]] = []
    for repo_path in selected:
        raw_url = raw_url_for_path(repo_path)
        local_path = local_path_for_repo_path(dest_root, repo_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        request = Request(raw_url, headers={"User-Agent": "qingcheng-ai-rag"})
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed public GitHub raw URL.
            content = response.read()
        local_path.write_bytes(content)
        results.append(
            {
                "repo_path": repo_path,
                "source_url": source_url_for_path(repo_path),
                "raw_url": raw_url,
                "local_path": str(local_path),
                "bytes": len(content),
            }
        )

    manifest_path = dest_root / "manifest.json"
    manifest_path.write_text(json.dumps({"source": JAVAUP_REPO, "files": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def source_url_for_path(repo_path: str) -> str:
    return f"{JAVAUP_BLOB_BASE}/{quote(repo_path, safe='/')}"


def raw_url_for_path(repo_path: str) -> str:
    return f"{JAVAUP_RAW_BASE}/{quote(repo_path, safe='/')}"


def local_path_for_repo_path(dest_root: Path, repo_path: str) -> Path:
    relative = PurePosixPath(repo_path)
    parts = relative.parts[1:] if relative.parts and relative.parts[0] == "docs" else relative.parts
    local_path = (dest_root / Path(*parts)).resolve()
    if not str(local_path).startswith(str(dest_root.resolve())):
        raise ValueError(f"unsafe javaup repo path: {repo_path}")
    return local_path


def _read_local_manifest_entries(dest_root: Path) -> list[dict]:
    manifest_path = dest_root / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    files = payload.get("files")
    return [item for item in files if isinstance(item, dict)] if isinstance(files, list) else []


def _resolve_existing_local_path(*, dest_root: Path, repo_path: str, manifest_entry: dict) -> Path | None:
    candidates: list[Path] = []
    manifest_path = str(manifest_entry.get("local_path") or "").strip()
    if manifest_path:
        raw_path = Path(manifest_path)
        candidates.append(raw_path if raw_path.is_absolute() else (dest_root / raw_path))
    candidates.append(local_path_for_repo_path(dest_root, repo_path))

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists() and resolved.is_file():
            return resolved
    return None
