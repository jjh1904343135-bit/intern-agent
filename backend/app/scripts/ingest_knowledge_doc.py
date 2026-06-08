"""CLI for ingesting DOCX interview notes into the AI assistant RAG index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.database import session_local
from app.services.knowledge_ingestion import ingest_knowledge_doc
from app.tools.embeddings.dashscope_adapter import EmbeddingProviderError, EmbeddingProviderNotConfigured


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a DOCX file into Qdrant knowledge_chunks.")
    parser.add_argument("--path", required=True, help="Path to the DOCX file, for example /app/file/10万字总结.docx")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"knowledge document not found: {path}")

    try:
        with session_local() as db:
            result = ingest_knowledge_doc(db=db, path=path)
    except EmbeddingProviderNotConfigured as exc:
        raise SystemExit(f"embedding provider not configured: {exc}") from exc
    except EmbeddingProviderError as exc:
        raise SystemExit(f"embedding provider error: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
