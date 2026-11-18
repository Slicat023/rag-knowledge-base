"""File ingestion lifecycle: parse -> split -> embed -> Chroma."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.config import settings
from app.services.parser import build_nodes, parse_file
from app.services.registry import DocumentRecord, DocumentRegistry
from app.services.vector_store import VectorStoreService
from app.utils import now_iso

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, registry: DocumentRegistry, vectors: VectorStoreService) -> None:
        self.registry = registry
        self.vectors = vectors
        self._ingest_lock = threading.Lock()
        self._deleted_lock = threading.Lock()
        self._deleted: set[str] = set()

    # ---------------------------------------------------------------- helpers
    def path_for(self, record: DocumentRecord) -> Path:
        return settings.documents_dir / record.stored_name

    def _is_deleted(self, doc_id: str) -> bool:
        with self._deleted_lock:
            return doc_id in self._deleted

    def _mark_deleted(self, doc_id: str) -> None:
        with self._deleted_lock:
            self._deleted.add(doc_id)

    def _clear_deleted(self, doc_id: str) -> None:
        with self._deleted_lock:
            self._deleted.discard(doc_id)

    def new_record(
        self,
        doc_id: str,
        name: str,
        stored_name: str,
        extension: str,
        size: int,
    ) -> DocumentRecord:
        record = DocumentRecord(
            id=doc_id,
            name=name,
            stored_name=stored_name,
            extension=extension,
            size=size,
            status="processing",
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        return self.registry.add(record)

    # ---------------------------------------------------------------- ingest
    def ingest(self, doc_id: str) -> None:
        """Synchronous ingestion, intended to run in a background task."""
        record = self.registry.get(doc_id)
        if record is None or self._is_deleted(doc_id):
            return

        with self._ingest_lock:
            record = self.registry.get(doc_id)
            if record is None or self._is_deleted(doc_id):
                return

            self.registry.update(doc_id, status="processing", error=None, chunks=0)
            path = self.path_for(record)
            try:
                if not path.exists():
                    raise FileNotFoundError(f"文件不存在：{record.name}")
                logger.info("Parsing %s (%s)", record.name, record.id)
                documents = parse_file(path, doc_id, record.name)
                nodes = build_nodes(documents, doc_id)
                if not nodes:
                    raise RuntimeError("文档切分后没有生成任何文本块。")
                if self._is_deleted(doc_id):
                    return

                # Re-indexing must not leave stale chunks behind.
                self.vectors.delete_document(doc_id)
                logger.info("Embedding %d chunks for %s", len(nodes), record.name)
                self.vectors.add_nodes(nodes)

                if self._is_deleted(doc_id):
                    self.vectors.delete_document(doc_id)
                    return

                self.registry.update(
                    doc_id,
                    status="ready",
                    chunks=len(nodes),
                    error=None,
                )
                logger.info("Ingested %s: %d chunks", record.name, len(nodes))
            except Exception as exc:
                logger.exception("Ingestion failed for %s", record.name)
                self.registry.update(
                    doc_id,
                    status="failed",
                    chunks=0,
                    error=str(exc) or exc.__class__.__name__,
                )

    # ---------------------------------------------------------------- delete
    def delete(self, doc_id: str) -> bool:
        record = self.registry.get(doc_id)
        if record is None:
            return False

        self._mark_deleted(doc_id)
        with self._ingest_lock:
            # Do not report success while old chunks can still be retrieved.
            # If Chroma is unavailable, keep the record and let the user retry.
            try:
                self.vectors.delete_document(doc_id)
            except Exception as exc:
                logger.exception("Failed to delete vectors for %s", doc_id)
                raise RuntimeError("向量库删除失败，文件记录已保留，请稍后重试。") from exc

            path = self.path_for(record)
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                logger.exception("Failed to delete file %s", path)

            self.registry.remove(doc_id)
        return True

    # ---------------------------------------------------------------- retry
    def retry(self, doc_id: str) -> bool:
        record = self.registry.get(doc_id)
        if record is None:
            return False
        if not self.path_for(record).exists():
            self.registry.update(
                doc_id,
                status="failed",
                error="原始文件已丢失，请删除该记录后重新上传。",
            )
            return False
        self._clear_deleted(doc_id)
        self.registry.update(doc_id, status="processing", error=None, chunks=0)
        return True