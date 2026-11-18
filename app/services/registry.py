"""JSON-backed document registry.

Chroma stores the chunks; this registry stores the user-facing file list and
ingestion status. The file is intentionally small and human-readable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.utils import now_iso

logger = logging.getLogger(__name__)

DocumentStatus = Literal["processing", "ready", "failed"]


class DocumentRecord(BaseModel):
    id: str
    name: str
    stored_name: str
    extension: str
    size: int = 0
    status: DocumentStatus = "processing"
    chunks: int = 0
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    error: str | None = None


class DocumentRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._records: dict[str, DocumentRecord] = {}
        self._load()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw.get("items", raw) if isinstance(raw, dict) else raw
            for item in items:
                record = DocumentRecord.model_validate(item)
                self._records[record.id] = record
        except Exception:
            logger.exception("Failed to load registry %s; starting empty", self.path)
            self._records = {}

    def _save(self) -> None:
        payload = {
            "version": 1,
            "items": [r.model_dump() for r in self._records.values()],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
            return
        except OSError:
            logger.warning("Atomic registry replace failed; writing in place", exc_info=True)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        self.path.write_text(text, encoding="utf-8")

    # ------------------------------------------------------------------ api
    def list(self) -> list[DocumentRecord]:
        with self._lock:
            return sorted(
                self._records.values(),
                key=lambda r: r.created_at,
                reverse=True,
            )

    def get(self, doc_id: str) -> DocumentRecord | None:
        with self._lock:
            return self._records.get(doc_id)

    def add(self, record: DocumentRecord) -> DocumentRecord:
        with self._lock:
            self._records[record.id] = record
            self._save()
            return record

    def update(self, doc_id: str, **fields) -> DocumentRecord | None:
        with self._lock:
            record = self._records.get(doc_id)
            if record is None:
                return None
            if "error" in fields and fields["error"]:
                fields["error"] = str(fields["error"])[:1000]
            fields["updated_at"] = now_iso()
            updated = record.model_copy(update=fields)
            self._records[doc_id] = updated
            self._save()
            return updated

    def remove(self, doc_id: str) -> DocumentRecord | None:
        with self._lock:
            record = self._records.pop(doc_id, None)
            if record is not None:
                self._save()
            return record

    def counts(self) -> dict[str, int]:
        with self._lock:
            records = list(self._records.values())
        return {
            "total": len(records),
            "ready": sum(r.status == "ready" for r in records),
            "processing": sum(r.status == "processing" for r in records),
            "failed": sum(r.status == "failed" for r in records),
            "chunks": sum(r.chunks for r in records),
        }

    def recover_interrupted(self) -> int:
        """Mark jobs interrupted by a restart as failed so they can be retried."""
        changed = 0
        with self._lock:
            for doc_id, record in list(self._records.items()):
                if record.status == "processing":
                    self._records[doc_id] = record.model_copy(
                        update={
                            "status": "failed",
                            "error": "服务重启导致处理中断，请点击“重试”重新解析。",
                            "updated_at": now_iso(),
                        }
                    )
                    changed += 1
            if changed:
                self._save()
        return changed