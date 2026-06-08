# RAG Ablation Eval Report

Dataset: `rag_eval_cases.jsonl`
Cases: 8

Current retrieval path: query rewrite + multi-query + Qdrant dense retrieval + PostgreSQL BM25 lexical retrieval + lightweight rerank + context packing + retrieval sufficiency.

## Retrieval Ablation
| Mode | Recall@3 | Recall@5 | MRR | Failed Cases |
|---|---:|---:|---:|---:|
| dense_only | 0.75 | 0.75 | 0.56 | 2 |
| bm25_only | 0.38 | 0.38 | 0.38 | 5 |
| hybrid_rerank | 0.88 | 1.00 | 0.71 | 1 |

## Interpretation
- Hybrid rerank is stronger than dense-only and BM25-only on this 8-case golden set.
- BM25-only is intentionally weaker on semantic questions, but it contributes exact keyword evidence for hybrid rerank.
- The remaining hybrid issue is `rag-javaup-kafka-reliability-001`, where the correct chunk appears at rank 5 instead of top 3.

## Failed Cases
### dense_only
- rag-jvm-memory-001: correct chunk not found in top 5
- rag-thread-pool-001: correct chunk not found in top 5

### bm25_only
- rag-mysql-index-001: correct chunk not found in top 5
- rag-spring-transaction-001: correct chunk not found in top 5
- rag-javaup-spring-transaction-failure-001: correct chunk not found in top 5
- rag-javaup-kafka-reliability-001: correct chunk not found in top 5
- rag-javaup-netty-zero-copy-001: correct chunk not found in top 5

### hybrid_rerank
- rag-javaup-kafka-reliability-001: correct chunk ranked at 5

## Commands
```powershell
docker compose exec api python -m app.scripts.ingest_knowledge_doc --path /app/file/10万字总结.docx
docker compose exec api python -m app.scripts.ingest_javaup_knowledge
docker compose exec api python -m evals.rag.eval_knowledge_rag --ablation
```