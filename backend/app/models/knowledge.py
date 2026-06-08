"""Knowledge-base tables for AI assistant RAG."""

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeDocument(Base):
    """Store one ingested source document and its embedding configuration."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    source_file: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="processing")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    embedding_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    document_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())


class KnowledgeChunk(Base):
    """Store retrievable chunks while Qdrant stores the dense vector."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_documents.id"), nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    section_path: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qdrant_point_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    chunk_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
