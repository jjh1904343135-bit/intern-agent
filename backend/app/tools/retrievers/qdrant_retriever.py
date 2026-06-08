from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.settings import settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=(settings.qdrant_api_key or None),
        check_compatibility=False,
    )


def ensure_collection(collection_name: str, vector_size: int) -> None:
    client = get_qdrant_client()
    collections = {item.name for item in client.get_collections().collections}
    if collection_name in collections:
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def recreate_collection(collection_name: str, vector_size: int) -> None:
    client = get_qdrant_client()
    collections = {item.name for item in client.get_collections().collections}
    if collection_name in collections:
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def upsert_point(
    *,
    collection_name: str,
    point_id: str,
    vector: list[float],
    payload: dict,
) -> None:
    client = get_qdrant_client()
    client.upsert(
        collection_name=collection_name,
        points=[
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        ],
    )


def delete_points_by_document_id(*, collection_name: str, document_id: str) -> None:
    client = get_qdrant_client()
    collections = {item.name for item in client.get_collections().collections}
    if collection_name not in collections:
        return

    client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            )
        ),
        wait=True,
    )


def search_similar_jobs(*, vector: list[float], limit: int = 10) -> list[models.ScoredPoint]:
    client = get_qdrant_client()
    return client.search(
        collection_name=settings.qdrant_jobs_collection,
        query_vector=vector,
        limit=limit,
        with_payload=True,
    )


def search_similar_points(*, collection_name: str, vector: list[float], limit: int = 10) -> list[models.ScoredPoint]:
    client = get_qdrant_client()
    return client.search(
        collection_name=collection_name,
        query_vector=vector,
        limit=limit,
        with_payload=True,
    )
