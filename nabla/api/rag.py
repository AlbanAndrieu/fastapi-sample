from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List

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
    return [
        SearchResult(
            filepath=row["filepath"],
            chunk_id=row["chunk_id"],
            text=row["text"],
            score=row["score"],
        )
        for row in results
    ]
