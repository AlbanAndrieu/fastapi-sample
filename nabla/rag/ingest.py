import os
import time
import mimetypes
from pathlib import Path
from typing import List, Dict, Tuple
import threading

import fitz  # PyMuPDF
import pdfplumber
import docx
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import logging

logger = logging.getLogger("rag.ingest")

DATA_DIR = Path("data/")
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

VECTOR_DB: List[Dict] = []  # [{"filepath": path, "chunk_id": i, "text": str, "embedding": [...]}, ...]


def extract_text_from_pdf(filepath: Path) -> str:
    try:
        # Try PyMuPDF first (fast for most PDFs)
        with fitz.open(filepath) as doc:
            return "\n".join([page.get_text("text") for page in doc])
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


def chunk_text(text: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> List[str]:
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i : i + chunk_size]
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def embed_chunks(chunks: List[str]) -> List[List[float]]:
    # Use LiteLLM to embed all chunks. Import at runtime to avoid import errors in old setups.
    import litellm
    import os

    model = os.environ.get("RAG_EMBEDDING_MODEL", "text-embedding-ada-002")
    return litellm.embedding(
        model=model,
        input=chunks,
    )


def add_file_to_vector_db(filepath: Path):
    ext = filepath.suffix.lower()
    text = extract_text(filepath)
    md = text_to_markdown(text, ext)
    chunks = chunk_text(md)
    embeddings = embed_chunks(chunks)
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        VECTOR_DB.append(
            {
                "filepath": str(filepath),
                "chunk_id": i,
                "text": chunk,
                "embedding": emb,
            },
        )
    logger.info(f"Ingested {filepath}: {len(chunks)} chunks")


def find_files(data_dir: Path) -> List[Path]:
    all_files = []
    for root, dirs, files in os.walk(data_dir):
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
            path = Path(event.src_path)
            if path.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}:
                add_file_to_vector_db(path)


def start_watching():
    event_handler = RAGFileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, str(DATA_DIR), recursive=True)
    observer.daemon = True
    observer.start()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    import numpy as np

    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def semantic_search(query: str, topk=5) -> List[Dict]:
    if not VECTOR_DB:
        return []
    import litellm

    emb = litellm.embedding(
        model=os.environ.get("RAG_EMBEDDING_MODEL", "text-embedding-ada-002"),
        input=[query],
    )[0]
    scored = [(cosine_similarity(emb, row["embedding"]), row) for row in VECTOR_DB]
    scored.sort(reverse=True, key=lambda x: x[0])
    return [row for _, row in scored[:topk]]


def setup_rag():
    initial_ingest()
    start_watching()
    logger.info(f"RAG directory watcher active on: {DATA_DIR}")
