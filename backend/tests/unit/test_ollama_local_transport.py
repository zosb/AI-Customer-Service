from __future__ import annotations

from types import SimpleNamespace

import httpx

from app.services.llm import chat_service as chat_module
from app.services.llm import embedding_service as embedding_module
from app.services.llm.chat_service import LLMMessage, OllamaChatService
from app.services.llm.embedding_service import EmbeddingService


class _EmbeddingClient:
    def __init__(self, captured: dict[str, object], **kwargs) -> None:
        captured.update(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, *, json):
        del url, json
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2, 0.3, 0.4]]},
        )


class _ChatClient:
    def __init__(self, captured: dict[str, object], **kwargs) -> None:
        captured.update(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, *, json):
        del url, json
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:4b",
                "message": {"content": "测试回答"},
            },
        )


def test_embedding_default_client_ignores_environment_proxy(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        embedding_module.httpx,
        "Client",
        lambda **kwargs: _EmbeddingClient(captured, **kwargs),
    )

    service = EmbeddingService(
        base_url="http://127.0.0.1:11434",
        model="test-embedding",
        dimension=4,
        timeout_seconds=10,
    )

    assert service.embed_text("测试") == [0.1, 0.2, 0.3, 0.4]
    assert captured["trust_env"] is False


def test_chat_default_client_ignores_environment_proxy(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        chat_module.httpx,
        "Client",
        lambda **kwargs: _ChatClient(captured, **kwargs),
    )

    service = OllamaChatService(
        base_url="http://127.0.0.1:11434",
        model="qwen3.5:4b",
        timeout_seconds=10,
        num_ctx=4096,
    )

    result = service.generate(
        [LLMMessage(role="user", content="你好")]
    )

    assert result.content == "测试回答"
    assert captured["trust_env"] is False
