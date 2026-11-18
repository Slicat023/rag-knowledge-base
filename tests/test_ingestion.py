from __future__ import annotations

import pytest

from app.services.ingestion import IngestionService
from app.services.registry import DocumentRecord, DocumentRegistry


class FakeVectors:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[str] = []

    def delete_document(self, doc_id: str) -> None:
        if self.fail:
            raise RuntimeError("chroma down")
        self.deleted.append(doc_id)


def make_record(tmp_path, doc_id="doc-1"):
    registry = DocumentRegistry(tmp_path / "registry.json")
    stored = f"{doc_id}.txt"
    (tmp_path / stored).write_text("内容", encoding="utf-8")
    record = DocumentRecord(
        id=doc_id,
        name="制度.txt",
        stored_name=stored,
        extension=".txt",
        size=6,
        status="ready",
        chunks=1,
    )
    registry.add(record)
    return registry, record


def test_delete_removes_record_file_and_vectors(tmp_path):
    registry, record = make_record(tmp_path)
    vectors = FakeVectors()
    service = IngestionService(registry, vectors)  # type: ignore[arg-type]
    service.path_for = lambda item: tmp_path / item.stored_name  # type: ignore[method-assign]

    assert service.delete(record.id) is True
    assert registry.get(record.id) is None
    assert not (tmp_path / record.stored_name).exists()
    assert vectors.deleted == [record.id]


def test_delete_keeps_record_when_vector_delete_fails(tmp_path):
    registry, record = make_record(tmp_path)
    vectors = FakeVectors(fail=True)
    service = IngestionService(registry, vectors)  # type: ignore[arg-type]
    service.path_for = lambda item: tmp_path / item.stored_name  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        service.delete(record.id)
    assert registry.get(record.id) is not None
    assert (tmp_path / record.stored_name).exists()