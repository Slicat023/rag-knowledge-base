"""Knowledge-base file management endpoints."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.deps import ingestion, registry
from app.schemas import DocumentItem, DocumentList, UploadError, UploadResult
from app.services.parser import SUPPORTED_EXTENSIONS
from app.utils import safe_filename

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _to_item(record) -> DocumentItem:
    return DocumentItem.model_validate(record.model_dump())


@router.get("", response_model=DocumentList)
def list_documents() -> DocumentList:
    items = [_to_item(record) for record in registry.list()]
    return DocumentList(items=items, total=len(items))


@router.post("", response_model=UploadResult, status_code=202)
async def upload_documents(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> UploadResult:
    items: list[DocumentItem] = []
    errors: list[UploadError] = []

    for upload in files:
        original = safe_filename(upload.filename or "document")
        extension = Path(original).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            errors.append(
                UploadError(
                    name=original,
                    message=f"不支持的文件类型 {extension or '(无扩展名)'}。"
                    f"支持：{', '.join(sorted(SUPPORTED_EXTENSIONS))}",
                )
            )
            await upload.close()
            continue

        doc_id = uuid4().hex
        stored_name = f"{doc_id}{extension}"
        destination = settings.documents_dir / stored_name
        size = 0
        try:
            with destination.open("wb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise ValueError(f"文件超过 {settings.max_upload_mb} MB 限制")
                    handle.write(chunk)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            errors.append(UploadError(name=original, message=str(exc)))
            continue
        finally:
            await upload.close()

        if size == 0:
            destination.unlink(missing_ok=True)
            errors.append(UploadError(name=original, message="文件为空"))
            continue

        record = ingestion.new_record(
            doc_id=doc_id,
            name=original,
            stored_name=stored_name,
            extension=extension,
            size=size,
        )
        background.add_task(ingestion.ingest, doc_id)
        items.append(_to_item(record))

    if not items and errors:
        raise HTTPException(status_code=400, detail="；".join(f"{e.name}: {e.message}" for e in errors))
    return UploadResult(items=items, errors=errors)


@router.delete("/{doc_id}")
def delete_document(doc_id: str) -> dict:
    try:
        deleted = ingestion.delete(doc_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="删除失败：向量库暂时不可用，文件记录已保留，请稍后重试。",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="文件不存在或已被删除")
    return {"ok": True, "id": doc_id}


@router.post("/{doc_id}/retry", response_model=DocumentItem, status_code=202)
def retry_document(doc_id: str, background: BackgroundTasks) -> DocumentItem:
    if not ingestion.retry(doc_id):
        record = registry.get(doc_id)
        if record is None:
            raise HTTPException(status_code=404, detail="文件不存在")
        raise HTTPException(status_code=400, detail=record.error or "无法重新处理该文件")
    background.add_task(ingestion.ingest, doc_id)
    return _to_item(registry.get(doc_id))


@router.get("/{doc_id}/download")
def download_document(doc_id: str):
    record = registry.get(doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = settings.documents_dir / record.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="原始文件已丢失")
    return FileResponse(path, filename=record.name)