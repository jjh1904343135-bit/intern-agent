from __future__ import annotations

from pathlib import Path

import pytest

from app.scripts import ingest_knowledge_doc
from app.tools.embeddings.dashscope_adapter import EmbeddingProviderError, EmbeddingProviderNotConfigured


def test_ingest_cli_reports_missing_embedding_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    docx_path = tmp_path / "notes.docx"
    docx_path.write_bytes(b"placeholder")

    def raise_missing_key(*, db, path):
        raise EmbeddingProviderNotConfigured("DASHSCOPE_API_KEY is required")

    monkeypatch.setattr(ingest_knowledge_doc, "ingest_knowledge_doc", raise_missing_key)
    monkeypatch.setattr("sys.argv", ["ingest_knowledge_doc", "--path", str(docx_path)])

    with pytest.raises(SystemExit, match="embedding provider not configured"):
        ingest_knowledge_doc.main()


def test_ingest_cli_reports_embedding_provider_business_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    docx_path = tmp_path / "notes.docx"
    docx_path.write_bytes(b"placeholder")

    def raise_provider_error(*, db, path):
        raise EmbeddingProviderError('DashScope embedding request failed: {"code":"AccessDenied.Unpurchased"}')

    monkeypatch.setattr(ingest_knowledge_doc, "ingest_knowledge_doc", raise_provider_error)
    monkeypatch.setattr("sys.argv", ["ingest_knowledge_doc", "--path", str(docx_path)])

    with pytest.raises(SystemExit, match="embedding provider error: .*AccessDenied.Unpurchased"):
        ingest_knowledge_doc.main()
