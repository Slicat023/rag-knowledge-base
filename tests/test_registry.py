from __future__ import annotations

from app.services.registry import DocumentRecord, DocumentRegistry


def make_record(doc_id: str = "a" * 32) -> DocumentRecord:
    return DocumentRecord(
        id=doc_id,
        name="测试文档.pdf",
        stored_name=doc_id + ".pdf",
        extension=".pdf",
        size=1024,
        status="processing",
    )


def test_registry_crud(tmp_path):
    registry = DocumentRegistry(tmp_path / "registry.json")
    record = registry.add(make_record())
    assert registry.get(record.id).name == "测试文档.pdf"

    registry.update(record.id, status="ready", chunks=7)
    assert registry.get(record.id).chunks == 7
    assert registry.counts()["ready"] == 1

    removed = registry.remove(record.id)
    assert removed is not None
    assert registry.get(record.id) is None


def test_registry_persists(tmp_path):
    path = tmp_path / "registry.json"
    registry = DocumentRegistry(path)
    registry.add(make_record())
    again = DocumentRegistry(path)
    assert again.get("a" * 32) is not None


def test_recover_interrupted(tmp_path):
    registry = DocumentRegistry(tmp_path / "registry.json")
    registry.add(make_record())
    assert registry.recover_interrupted() == 1
    record = registry.get("a" * 32)
    assert record.status == "failed"
    assert "重启" in record.error