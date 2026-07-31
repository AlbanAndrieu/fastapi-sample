"""Unit tests for RAG embedding normalization and scoring."""

from types import SimpleNamespace

import pytest

from nabla.rag import ingest


def test_extract_embeddings_accepts_openai_compatible_objects() -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[1, 2.5]), SimpleNamespace(embedding=[3.0, 4])],
    )

    assert ingest._extract_embeddings(response, expected_count=2) == [[1.0, 2.5], [3.0, 4.0]]


def test_extract_embeddings_rejects_wrong_cardinality() -> None:
    with pytest.raises(ValueError, match="count mismatch"):
        ingest._extract_embeddings({"data": [{"embedding": [1.0]}]}, expected_count=2)


def test_extract_embeddings_rejects_inconsistent_dimensions() -> None:
    response = {"data": [{"embedding": [1.0]}, {"embedding": [1.0, 2.0]}]}

    with pytest.raises(ValueError, match="inconsistent vector dimensions"):
        ingest._extract_embeddings(response, expected_count=2)


def test_semantic_search_returns_scores_without_mutating_store(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"filepath": "x.md", "chunk_id": 0, "text": "near", "embedding": [1.0, 0.0]},
        {"filepath": "x.md", "chunk_id": 1, "text": "far", "embedding": [0.0, 1.0]},
    ]
    monkeypatch.setattr(ingest, "VECTOR_DB", rows)
    monkeypatch.setattr(ingest, "embed_chunks", lambda chunks: [[1.0, 0.0]])

    results = ingest.semantic_search("query", topk=1)

    assert results[0]["text"] == "near"
    assert results[0]["score"] == pytest.approx(1.0)
    assert "score" not in rows[0]
