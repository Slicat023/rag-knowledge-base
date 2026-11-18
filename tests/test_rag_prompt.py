from __future__ import annotations

from types import SimpleNamespace

from app.config import settings
from app.schemas import ChatTurn
from app.services.rag import RagService


def test_prompt_contains_context_history_and_citation_rule():
    service = RagService(vectors=None, registry=None)  # type: ignore[arg-type]
    messages = service._build_messages(
        "报销标准是多少？",
        "[资料1] 来源：制度.md\n住宿标准为每晚 500 元。",
        [
            ChatTurn(role="user", content="你好"),
            ChatTurn(role="assistant", content="你好，请问有什么可以帮你？"),
        ],
    )
    assert messages[0].role.value == "system"
    assert messages[-1].role.value == "user"
    assert "报销标准是多少" in messages[-1].content
    assert "每晚 500 元" in messages[-1].content
    assert any(message.content == "你好" for message in messages)


def test_stream_emits_sources_deltas_and_done(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "test-key")
    service = RagService(vectors=None, registry=None)  # type: ignore[arg-type]

    sources = [
        {
            "index": 1,
            "doc_id": "doc-1",
            "file_name": "制度.md",
            "page": 1,
            "score": 0.9,
            "vector_score": 0.8,
            "snippet": "住宿标准 500 元。",
            "text": "住宿标准 500 元。",
        }
    ]
    monkeypatch.setattr(
        service,
        "retrieve",
        lambda *args, **kwargs: (sources, "[资料1] 住宿标准 500 元。", {"retrieved": 1}),
    )

    class FakeLLM:
        def stream_chat(self, messages):
            assert "住宿标准 500 元" in messages[-1].content
            yield SimpleNamespace(delta="答案")
            yield SimpleNamespace(delta="[1]")

    monkeypatch.setattr("app.services.rag.llm_factory.get", lambda provider: FakeLLM())

    events = list(service.stream("住哪里？", [], provider="qwen"))
    assert [event for event, _ in events] == ["sources", "delta", "delta", "done"]
    assert events[1][1]["text"] == "答案"
    assert events[-1][1]["provider"] == "qwen"