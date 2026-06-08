"""Download curated JavaUp Markdown docs and ingest them into the AI assistant RAG index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.javaup_knowledge_source import (
    collect_local_javaup_markdowns,
    download_selected_javaup_markdowns,
    fetch_javaup_tree_paths,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest curated javaup Markdown docs into knowledge_chunks.")
    parser.add_argument(
        "--dest",
        default="file/knowledge_sources/javaup",
        help="Local destination for downloaded Markdown files. Defaults to file/knowledge_sources/javaup.",
    )
    parser.add_argument("--max-files", type=int, default=None, help="Optional cap for quick smoke runs.")
    parser.add_argument("--download-only", action="store_true", help="Only download Markdown files and write manifest.json.")
    parser.add_argument("--refresh-download", action="store_true", help="Force GitHub refresh instead of using local Markdown first.")
    args = parser.parse_args()

    dest_dir = Path(args.dest)
    downloaded = [] if args.refresh_download else collect_local_javaup_markdowns(dest_dir=dest_dir, max_files=args.max_files)
    if not downloaded:
        try:
            tree_paths = fetch_javaup_tree_paths()
            downloaded = download_selected_javaup_markdowns(dest_dir=dest_dir, paths=tree_paths, max_files=args.max_files)
        except Exception as exc:
            raise SystemExit(f"javaup source unavailable and no local Markdown files found: {exc}") from exc

    if args.download_only:
        print(json.dumps({"downloaded": len(downloaded), "files": downloaded}, ensure_ascii=False))
        return

    from app.core.database import session_local
    from app.services.knowledge_ingestion import ingest_markdown_knowledge_doc
    from app.tools.embeddings.dashscope_adapter import EmbeddingProviderError, EmbeddingProviderNotConfigured

    total_chunks = 0
    ingested: list[dict] = []
    try:
        with session_local() as db:
            for item in downloaded:
                result = ingest_markdown_knowledge_doc(
                    db=db,
                    path=Path(str(item["local_path"])),
                    source_url=str(item["source_url"]),
                    repo_path=str(item["repo_path"]),
                )
                total_chunks += int(result["chunks"])
                ingested.append({**item, **result})
    except EmbeddingProviderNotConfigured as exc:
        raise SystemExit(f"embedding provider not configured: {exc}") from exc
    except EmbeddingProviderError as exc:
        raise SystemExit(f"embedding provider error: {exc}") from exc

    print(
        json.dumps(
            {
                "downloaded": len(downloaded),
                "documents": len(ingested),
                "chunks": total_chunks,
                "files": ingested,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
