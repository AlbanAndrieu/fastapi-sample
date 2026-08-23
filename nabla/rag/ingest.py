import os
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import numpy as np
import pdfplumber
import docx
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

import logging

logger = logging.getLogger("rag.ingest")

DATA_DIR = Path("data/")
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

VECTOR_DB: list[dict[str, Any]] = []


def extract_text_from_pdf(filepath: Path) -> str:
    try:
        # Try PyMuPDF first (fast for most PDFs)
        with fitz.open(filepath) as doc:
            return "\n".join(str(page.get_text("text")) for page in doc)
    except Exception:
        # Fallback: pdfplumber
        with pdfplumber.open(str(filepath)) as pdf:
            return "\n".join([page.extract_text() or "" for page in pdf.pages])


def extract_text_from_docx(filepath: Path) -> str:
    doc = docx.Document(str(filepath))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext in {".docx", ".doc"}:
        return extract_text_from_docx(filepath)
    elif ext in {".md", ".txt"}:
        return filepath.read_text(encoding="utf-8", errors="ignore")
    else:
        logger.warning(f"Unknown extension {ext}, treating as text: {filepath}")
        return filepath.read_text(encoding="utf-8", errors="ignore")


def text_to_markdown(text: str, ext: str) -> str:
    # For now, just wrap pre/code block for .txt, do nothing for .md
    if ext == ".md":
        return text
    elif ext == ".txt":
        return f"```\n{text}\n```"
    else:
        return text


def chunk_text(text: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> list[str]:
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i : i + chunk_size]
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def _extract_embeddings(response: Any, *, expected_count: int) -> list[list[float]]:
    """Validate and normalize LiteLLM's OpenAI-compatible embedding response."""
    data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)
    if not isinstance(data, list):
        raise ValueError("Embedding response has no 'data' list")

    embeddings: list[list[float]] = []
    for index, item in enumerate(data):
        raw = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
        if not isinstance(raw, list) or not raw or not all(isinstance(value, (int, float)) for value in raw):
            raise ValueError(f"Embedding response item {index} has an invalid vector")
        embeddings.append([float(value) for value in raw])

    if len(embeddings) != expected_count:
        raise ValueError(f"Embedding response count mismatch: expected {expected_count}, got {len(embeddings)}")
    dimensions = {len(vector) for vector in embeddings}
    if len(dimensions) > 1:
        raise ValueError("Embedding response contains inconsistent vector dimensions")
    return embeddings


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    # Use LiteLLM to embed all chunks.
    if not chunks:
        return []
    import litellm  # noqa: PLC0415 - expensive optional integration, loaded only when RAG is used

    model = os.environ.get("RAG_EMBEDDING_MODEL", "text-embedding-ada-002")
    response = litellm.embedding(
        model=model,
        input=chunks,
    )
    return _extract_embeddings(response, expected_count=len(chunks))


def add_file_to_vector_db(filepath: Path):
    ext = filepath.suffix.lower()
    text = extract_text(filepath)
    md = text_to_markdown(text, ext)
    chunks = chunk_text(md)
    embeddings = embed_chunks(chunks)
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=True)):
        VECTOR_DB.append(
            {
                "filepath": str(filepath),
                "chunk_id": i,
                "text": chunk,
                "embedding": emb,
            },
        )
    logger.info(f"Ingested {filepath}: {len(chunks)} chunks")


def find_files(data_dir: Path) -> list[Path]:
    all_files = []
    for root, _, files in os.walk(data_dir):
        for fname in files:
            p = Path(root) / fname
            if p.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}:
                all_files.append(p)
    return all_files


def initial_ingest():
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = find_files(DATA_DIR)
    for f in files:
        add_file_to_vector_db(f)


class RAGFileEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            path = Path(os.fsdecode(event.src_path))
            if path.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}:
                add_file_to_vector_db(path)


def start_watching() -> BaseObserver:
    event_handler = RAGFileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, str(DATA_DIR), recursive=True)
    observer.daemon = True
    observer.start()
    return observer


def cosine_similarity(a: list[float], b: list[float]) -> float:
    vector_a = np.array(a)
    vector_b = np.array(b)
    return float(np.dot(vector_a, vector_b) / (np.linalg.norm(vector_a) * np.linalg.norm(vector_b) + 1e-10))


def semantic_search(query: str, topk: int = 5) -> list[dict[str, Any]]:
    if not VECTOR_DB:
        return []
    emb = embed_chunks([query])[0]
    scored = [(cosine_similarity(emb, row["embedding"]), row) for row in VECTOR_DB]
    scored.sort(reverse=True, key=lambda x: x[0])
    return [{**row, "score": score} for score, row in scored[:topk]]


def setup_rag() -> BaseObserver:
    initial_ingest()
    observer = start_watching()
    logger.info(f"RAG directory watcher active on: {DATA_DIR}")
    return observer
