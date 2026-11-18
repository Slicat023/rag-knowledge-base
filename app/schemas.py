"""Pydantic schemas shared by the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=20000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list)
    provider: Literal["qwen", "deepseek"] | None = None
    top_k: int | None = Field(default=None, ge=1, le=30)
    rerank_top_n: int | None = Field(default=None, ge=1, le=10)


class Source(BaseModel):
    index: int
    doc_id: str
    file_name: str
    page: int | None = None
    section_path: str = ""
    table_caption: str = ""
    score: float
    vector_score: float | None = None
    snippet: str
    text: str


class DocumentItem(BaseModel):
    id: str
    name: str
    extension: str
    size: int
    status: Literal["processing", "ready", "failed"]
    chunks: int
    created_at: str
    updated_at: str
    error: str | None = None


class DocumentList(BaseModel):
    items: list[DocumentItem]
    total: int


class UploadError(BaseModel):
    name: str
    message: str


class UploadResult(BaseModel):
    items: list[DocumentItem]
    errors: list[UploadError] = Field(default_factory=list)