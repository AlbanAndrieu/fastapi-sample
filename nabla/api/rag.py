from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Dict

from nabla.rag import ingest

router = APIRouter()


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    topk: int = Field(5, ge=1, le=50)


class SearchResult(BaseModel):
    filepath: str
    chunk_id: int
    text: str
    score: float


@router.post("/rag/search", response_model=List[SearchResult])
def rag_search(req: QueryRequest):
    results = ingest.semantic_search(req.query, req.topk)
    # Rerun scoring for .score output (cosine similarity)
    import numpy as np

    query_emb = results and ingest.embed_chunks([req.query])[0] or []
    out = []
    for row in results:
        emb = row["embedding"]
        sim = float(np.dot(query_emb, emb) / (np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-10))
        out.append(
            SearchResult(
                filepath=row["filepath"],
                chunk_id=row["chunk_id"],
                text=row["text"],
                score=sim,
            ),
        )
    return out
