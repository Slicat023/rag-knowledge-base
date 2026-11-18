"""Health and capability endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.deps import registry
from app.services.embeddings import embedding_service
from app.services.llm import llm_factory
from app.services.parser import SUPPORTED_EXTENSIONS
from app.services.reranker import reranker
from app.services.vector_store import vector_store

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "default_llm": settings.default_llm,
        "llm": llm_factory.info(),
        "embedding": embedding_service.info(),
        "reranker": reranker.info(),
        "documents": registry.counts(),
        "vector_store": vector_store.info(),
        "limits": {"max_upload_mb": settings.max_upload_mb},
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
    }