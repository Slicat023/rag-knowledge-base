from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_pages_and_health():
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert "知识问答" in client.get("/").text
        assert client.get("/knowledge").status_code == 200
        assert "知识库文件" in client.get("/knowledge").text

        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert "embedding" in body
        assert "reranker" in body


def test_document_list_shape():
    with TestClient(app) as client:
        response = client.get("/api/documents")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert body["total"] == len(body["items"])


def test_unsupported_upload_is_rejected(tmp_path):
    with TestClient(app) as client:
        response = client.post(
            "/api/documents",
            files={"files": ("bad.exe", b"not a document", "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "不支持" in response.json()["detail"]


def test_chat_without_api_key_returns_sse_error(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "default_llm", "qwen")

    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "你好", "provider": "qwen"})
        assert response.status_code == 200
        assert "event: error" in response.text
        assert "missing_api_key" in response.text