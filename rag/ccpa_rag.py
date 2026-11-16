"""CCPA knowledge base with Retrieval-Augmented Generation (RAG).

RAG in one sentence: before the LLM writes anything about the law, we *retrieve* the most relevant
passages of the guidelines and give them to it, so its answer is grounded in real text instead of
its memory (fewer hallucinations, and we can cite the pattern number).

Pipeline
1. Load knowledge: rag/data/ccpa_patterns.json (our structured summary) and, if present, the
   official guidelines PDF(s) in rag/data/*.pdf.
2. Chunk: one chunk per pattern section (definition / examples / prohibited); PDFs are split into
   ~800-character overlapping chunks and tagged with the pattern they mention.
3. Embed each chunk with sentence-transformers (all-MiniLM-L6-v2).
4. Store in ChromaDB (a local vector database, folder rag/chroma/, git-ignored).
5. ``ccpa_lookup(query)`` embeds the query and returns the closest chunks.

    python -m rag.ccpa_rag --rebuild
    python -m rag.ccpa_rag "fees shown only at checkout"
"""

from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parent
DATA_DIR = RAG_DIR / "data"
CHROMA_DIR = RAG_DIR / "chroma"
COLLECTION = "ccpa_dark_patterns"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_CHARS, CHUNK_OVERLAP = 800, 150


def _knowledge() -> dict:
    return json.loads((DATA_DIR / "ccpa_patterns.json").read_text(encoding="utf-8"))


def build_chunks() -> list[dict]:
    """Return chunks: {id, text, pattern (0 = general), name, source}."""
    kb = _knowledge()
    chunks: list[dict] = []
    for i, g in enumerate(kb["general"]):
        chunks.append({"id": f"general-{i}", "text": f"{g['title']}: {g['text']}", "pattern": 0,
                       "name": g["title"], "source": "summary"})
    for p in kb["patterns"]:
        head = f"CCPA dark pattern {p['number']}: {p['name']}."
        chunks.append({"id": f"p{p['number']}-def", "text": f"{head} Definition: {p['definition']}",
                       "pattern": p["number"], "name": p["name"], "source": "summary"})
        chunks.append({"id": f"p{p['number']}-ex", "text": f"{head} Examples: " + "; ".join(p["examples"]),
                       "pattern": p["number"], "name": p["name"], "source": "summary"})
        chunks.append({"id": f"p{p['number']}-rule", "text": f"{head} What is not allowed: {p['prohibited']}",
                       "pattern": p["number"], "name": p["name"], "source": "summary"})
    chunks.extend(_pdf_chunks({p["name"].lower(): p["number"] for p in kb["patterns"]}))
    return chunks


def _pdf_chunks(name_to_number: dict[str, int]) -> list[dict]:
    """Chunk any guideline PDFs the user placed in rag/data/ (optional, needs pypdf)."""
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        return []
    try:
        from pypdf import PdfReader
    except ImportError:
        print("[rag] pypdf not installed; skipping PDFs (pip install pypdf)")
        return []
    out: list[dict] = []
    for pdf in pdfs:
        text = re.sub(r"\s+", " ", " ".join(page.extract_text() or "" for page in PdfReader(pdf).pages))
        start, n = 0, 0
        while start < len(text):
            piece = text[start:start + CHUNK_CHARS]
            mentioned = [num for name, num in name_to_number.items() if name in piece.lower()]
            out.append({"id": f"{pdf.stem}-{n}", "text": piece, "pattern": mentioned[0] if mentioned else 0,
                        "name": pdf.stem, "source": pdf.name})
            start += CHUNK_CHARS - CHUNK_OVERLAP
            n += 1
    print(f"[rag] ingested {len(out)} chunks from {len(pdfs)} PDF(s)")
    return out


@lru_cache(maxsize=1)
def _encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


def _embed(texts: list[str]) -> list[list[float]]:
    return _encoder().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


@lru_cache(maxsize=1)
def _collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def build_index(rebuild: bool = False) -> int:
    """(Re)build the ChromaDB collection. Returns the number of chunks stored."""
    col = _collection()
    if col.count() and not rebuild:
        return col.count()
    if col.count():
        col.delete(ids=col.get()["ids"])
    chunks = build_chunks()
    col.add(ids=[c["id"] for c in chunks], documents=[c["text"] for c in chunks],
            embeddings=_embed([c["text"] for c in chunks]),
            metadatas=[{"pattern": c["pattern"], "name": c["name"], "source": c["source"]} for c in chunks])
    return col.count()


def ccpa_lookup(query: str, k: int = 3) -> list[dict]:
    """Top-k CCPA passages for a query: [{pattern, name, text, score}] (score = cosine similarity)."""
    build_index()
    q = _embed([query])[0]
    res = _collection().query(query_embeddings=[q], n_results=k,
                              include=["documents", "metadatas", "embeddings"])
    # Vectors are normalised, so the dot product is the cosine similarity (1 = same meaning).
    return [
        {"pattern": meta["pattern"], "name": meta["name"], "text": doc,
         "score": round(float(sum(a * b for a, b in zip(q, emb))), 3)}
        for doc, meta, emb in zip(res["documents"][0], res["metadatas"][0], res["embeddings"][0])
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="fees revealed only at checkout")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    print(f"Index has {build_index(rebuild=a.rebuild)} chunks.")
    for hit in ccpa_lookup(a.query):
        print(f"[{hit['score']:.2f}] pattern {hit['pattern']} ({hit['name']}): {hit['text'][:160]}")


if __name__ == "__main__":
    main()
