"""Chroma-backed vector store and LlamaIndex index."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class VectorStoreService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client = None
        self._collection = None
        self._vector_store = None
        self._index = None

    # ------------------------------------------------------------- lifecycle
    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection
        with self._lock:
            if self._collection is not None:
                return self._collection

            import chromadb
            from chromadb.config import Settings as ChromaSettings

            settings.ensure_directories()
            self._client = chromadb.PersistentClient(
                path=str(settings.chroma_dir),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
            logger.info(
                "Chroma collection '%s' ready (%d items)",
                settings.chroma_collection,
                self._collection.count(),
            )
            return self._collection

    @property
    def collection(self):
        return self._ensure_collection()

    def _ensure_index(self):
        if self._index is not None:
            return self._index
        with self._lock:
            if self._index is not None:
                return self._index

            from llama_index.core import VectorStoreIndex
            from llama_index.vector_stores.chroma import ChromaVectorStore

            from app.services.embeddings import embedding_service

            collection = self._ensure_collection()
            self._vector_store = ChromaVectorStore(chroma_collection=collection)
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=self._vector_store,
                embed_model=embedding_service.get(),
            )
            return self._index

    # ------------------------------------------------------------- mutation
    def add_nodes(self, nodes: list) -> int:
        if not nodes:
            return 0
        index = self._ensure_index()
        with self._lock:
            index.insert_nodes(nodes)
        return len(nodes)

    def delete_document(self, doc_id: str) -> None:
        """Delete every chunk belonging to a knowledge-base document.

        LlamaIndex's Chroma adapter reserves the top-level ``doc_id`` metadata
        key for its own ref-doc id, so we use our own ``kb_id`` key and delete
        by explicit ids (more reliable than a filtered delete across versions).
        """
        collection = self._ensure_collection()
        with self._lock:
            try:
                data = collection.get(where={"kb_id": doc_id}, include=[])
            except Exception:
                data = collection.get(where={"kb_id": doc_id})
            ids = list(data.get("ids") or [])
            if ids:
                collection.delete(ids=ids)
                logger.info("Deleted %d vectors for document %s", len(ids), doc_id)
            else:
                logger.warning("No vectors found for document %s (kb_id filter)", doc_id)

    def clear(self) -> None:
        collection = self._ensure_collection()
        with self._lock:
            data = collection.get(include=[])
            ids = list(data.get("ids") or [])
            if ids:
                collection.delete(ids=ids)
                logger.info("Cleared %d vectors", len(ids))

    # ------------------------------------------------------------- querying
    def retrieve(self, query: str, top_k: int) -> list:
        index = self._ensure_index()
        retriever = index.as_retriever(similarity_top_k=max(1, int(top_k)))
        return retriever.retrieve(query)

    def count(self) -> int:
        try:
            return int(self.collection.count())
        except Exception:
            logger.exception("Could not count Chroma collection")
            return 0

    def info(self) -> dict[str, Any]:
        return {
            "collection": settings.chroma_collection,
            "path": str(settings.chroma_dir),
            "vectors": self.count(),
        }


vector_store = VectorStoreService()