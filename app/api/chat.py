"""Streaming chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import settings
from app.deps import rag_service
from app.schemas import ChatRequest
from app.services.rag import event_stream

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    provider = (request.provider or settings.default_llm or "qwen").lower()
    stream = event_stream(
        rag_service,
        question=request.message,
        history=request.history,
        provider=provider,
        top_k=request.top_k,
        rerank_top_n=request.rerank_top_n,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )