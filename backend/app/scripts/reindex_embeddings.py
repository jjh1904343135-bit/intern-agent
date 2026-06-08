from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import session_local
from app.core.settings import settings
from app.repositories.job_repository import JobRepository
from app.tools.embeddings.fastembed_adapter import embed_text
from app.tools.retrievers.qdrant_retriever import ensure_collection, recreate_collection, upsert_point


def _vector_size() -> int:
    return len(embed_text("python sql fastapi"))


def rebuild_job_embeddings(db: Session) -> int:
    job_repository = JobRepository(db)
    jobs = job_repository.list_active_jobs()

    ensure_collection(settings.qdrant_jobs_collection, _vector_size())

    indexed_jobs = 0
    for job in jobs:
        job_text = " ".join(filter(None, [job.title, job.company, job.city, job.jd_text or ""]))
        point_id = job.embedding_id or str(job.id)
        upsert_point(
            collection_name=settings.qdrant_jobs_collection,
            point_id=point_id,
            vector=embed_text(job_text),
            payload={
                "job_id": str(job.id),
                "title": job.title,
                "company": job.company,
                "city": job.city,
                "jd_text": job.jd_text,
            },
        )
        job_repository.upsert_embedding_id(job=job, embedding_id=point_id)
        indexed_jobs += 1

    return indexed_jobs


def rebuild_resume_embeddings(db: Session) -> int:
    ensure_collection(settings.qdrant_resumes_collection, _vector_size())

    indexed_resumes = 0
    resumes = db.execute(
        text(
            """
            SELECT id, user_id, parsed_content, embedding_id
            FROM resumes
            WHERE parse_status = 'done' AND parsed_content IS NOT NULL
            """
        )
    ).mappings()
    for resume in resumes:
        parsed_content = resume["parsed_content"]
        resume_text = " ".join(
            filter(
                None,
                [
                    parsed_content.get("summary", ""),
                    " ".join(parsed_content.get("skills", [])),
                    " ".join(item.get("name", "") for item in parsed_content.get("projects", []) if isinstance(item, dict)),
                ],
            )
        )
        point_id = resume["embedding_id"] or str(resume["id"])
        upsert_point(
            collection_name=settings.qdrant_resumes_collection,
            point_id=point_id,
            vector=embed_text(resume_text),
            payload={"resume_id": str(resume["id"]), "user_id": str(resume["user_id"])},
        )
        db.execute(
            text("UPDATE resumes SET embedding_id = :embedding_id WHERE id = :resume_id"),
            {"embedding_id": point_id, "resume_id": str(resume["id"])},
        )
        indexed_resumes += 1

    db.commit()
    return indexed_resumes


def rebuild_search_indexes() -> dict[str, int]:
    vector_size = _vector_size()
    recreate_collection(settings.qdrant_jobs_collection, vector_size)
    recreate_collection(settings.qdrant_resumes_collection, vector_size)

    with session_local() as db:
        indexed_jobs = rebuild_job_embeddings(db)
        indexed_resumes = rebuild_resume_embeddings(db)

    return {"jobs": indexed_jobs, "resumes": indexed_resumes}


if __name__ == "__main__":
    result = rebuild_search_indexes()
    print(f"indexed_jobs={result['jobs']}")
    print(f"indexed_resumes={result['resumes']}")
