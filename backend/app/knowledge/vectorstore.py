"""ChromaDB vector store for semantic search over schemes and documents.

Uses ChromaDB's default embedding function (onnxruntime-based, lightweight).
Automatically seeds from the curated scholarship dataset on first use.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger("lifepilot.knowledge")

_collection = None
_client = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "scholarships.json"


def get_vectorstore():
    """Get or create the ChromaDB collection (singleton)."""
    global _collection, _client
    if _collection is not None:
        return _collection

    try:
        import chromadb
        persist_dir = settings.chroma_persist_dir
        _client = chromadb.PersistentClient(path=persist_dir)
        _collection = _client.get_or_create_collection(
            name="schemes",
            metadata={"hnsw:space": "cosine"},
        )

        # Seed if empty
        if _collection.count() == 0:
            _seed_from_curated()

        logger.info(f"ChromaDB ready: {_collection.count()} documents in 'schemes'")
        return _collection
    except Exception as e:
        logger.warning(f"ChromaDB unavailable: {e}. Vector search disabled.")
        return _FallbackCollection()


def _seed_from_curated():
    """Seed ChromaDB with the curated scholarship dataset."""
    global _collection
    if _collection is None:
        return

    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            schemes = json.load(f)
    except Exception:
        return

    ids = []
    documents = []
    metadatas = []

    for scheme in schemes:
        sid = scheme.get("id", "")
        # Build a rich text representation for embedding
        text_parts = [
            scheme.get("title", ""),
            scheme.get("description", ""),
            f"Provider: {scheme.get('provider', '')}",
            f"Amount: {scheme.get('amount', '')}",
            f"Category: {scheme.get('category', '')}",
        ]
        criteria = scheme.get("criteria", {})
        if criteria.get("category"):
            text_parts.append(f"For: {', '.join(criteria['category'])}")
        if criteria.get("state"):
            text_parts.append(f"State: {', '.join(criteria['state'])}")
        if criteria.get("education_level"):
            text_parts.append(f"Education: {', '.join(criteria['education_level'])}")

        doc_text = " | ".join(t for t in text_parts if t)

        ids.append(sid)
        documents.append(doc_text)
        metadatas.append({
            "id": sid,
            "title": scheme.get("title", ""),
            "category": scheme.get("category", ""),
            "full_json": json.dumps(scheme),
        })

    if ids:
        _collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(f"Seeded ChromaDB with {len(ids)} schemes")


def add_schemes(schemes: list[dict]) -> int:
    """Add new schemes to the vector store (from scraping, etc.)."""
    coll = get_vectorstore()
    if isinstance(coll, _FallbackCollection):
        return 0

    added = 0
    for scheme in schemes:
        sid = scheme.get("id", "")
        if not sid:
            continue
        existing = coll.get(ids=[sid])
        if existing and existing.get("ids"):
            continue

        text = f"{scheme.get('title', '')} | {scheme.get('description', '')} | {scheme.get('provider', '')}"
        coll.add(
            ids=[sid],
            documents=[text],
            metadatas=[{
                "id": sid,
                "title": scheme.get("title", ""),
                "full_json": json.dumps(scheme),
            }],
        )
        added += 1

    return added


def search(query: str, n_results: int = 10) -> list[dict]:
    """Semantic search for schemes matching a natural language query."""
    coll = get_vectorstore()
    try:
        results = coll.query(query_texts=[query], n_results=n_results)
        schemes = []
        if results and results.get("metadatas"):
            for meta in results["metadatas"][0]:
                full = meta.get("full_json")
                if full:
                    try:
                        schemes.append(json.loads(full))
                    except json.JSONDecodeError:
                        schemes.append({"id": meta.get("id"), "title": meta.get("title", "")})
        return schemes
    except Exception as e:
        logger.warning(f"Vector search failed: {e}")
        return []


class _FallbackCollection:
    """No-op fallback when ChromaDB is unavailable."""
    def count(self):
        return 0
    def query(self, **kwargs):
        return {"documents": [[]], "metadatas": [[]]}
    def add(self, **kwargs):
        pass
    def get(self, **kwargs):
        return {"ids": []}
