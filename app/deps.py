"""Shared service singletons."""

from __future__ import annotations

from app.config import settings

settings.ensure_directories()

from app.services.ingestion import IngestionService  # noqa: E402
from app.services.rag import RagService  # noqa: E402
from app.services.registry import DocumentRegistry  # noqa: E402
from app.services.vector_store import vector_store  # noqa: E402

registry = DocumentRegistry(settings.registry_path)
ingestion = IngestionService(registry, vector_store)
rag_service = RagService(vector_store, registry)