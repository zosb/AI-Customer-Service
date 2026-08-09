from __future__ import annotations

import json

import httpx
import pytest

from app.services.llm.chat_service import (
    ChatGenerationError,
    LLMMessage,
    OllamaChatService,
)
from app.services.llm.embedding_service import EmbeddingService


def test_embedding_retries_502_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(502, text="temporary")
        return httpx.Response(
            200,
            json={"embeddings": [[1, 2, 3, 4]]},
        )

    service = EmbeddingService(
        base_url="http://ollama.test",
        model="embed",
        dimension=4,
        timeout_seconds=10,
        client=httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
        retry_attempts=3,
        retry_backoff_seconds=0,
    )

    assert service.embed_text("退款") == [1.0, 2.0, 3.0, 4.0]
    assert calls == 2


def test_chat_generate_retries_503_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="loading")
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:4b",
                "message": {
                    "role": "assistant",
                    "content": "三个工作日[来源1]",
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    service = OllamaChatService(
        base_url="http://ollama.test",
        model="qwen3.5:4b",
        timeout_seconds=10,
        num_ctx=4096,
        client=httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
        retry_attempts=3,
        retry_backoff_seconds=0,
    )

    result = service.generate(
        [LLMMessage(role="user", content="退款多久")]
    )
    assert "三个工作日" in result.content
    assert calls == 2


def test_chat_stream_retries_504_before_any_token() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(504, text="gateway timeout")
        content = (
            b'{"model":"qwen3.5:4b","message":{"content":"ok"},'
            b'"done":false}\n'
            b'{"model":"qwen3.5:4b","message":{"content":""},'
            b'"done":true,"prompt_eval_count":3,"eval_count":1}\n'
        )
        return httpx.Response(200, content=content)

    service = OllamaChatService(
        base_url="http://ollama.test",
        model="qwen3.5:4b",
        timeout_seconds=10,
        num_ctx=4096,
        client=httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
        retry_attempts=3,
        retry_backoff_seconds=0,
    )

    chunks = list(
        service.stream(
            [LLMMessage(role="user", content="hi")]
        )
    )
    assert "".join(item.content for item in chunks) == "ok"
    assert calls == 2


def test_non_retryable_400_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={"error": "bad request"},
        )

    service = OllamaChatService(
        base_url="http://ollama.test",
        model="qwen3.5:4b",
        timeout_seconds=10,
        num_ctx=4096,
        client=httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
        retry_attempts=3,
        retry_backoff_seconds=0,
    )

    with pytest.raises(ChatGenerationError, match="HTTP 400"):
        service.generate(
            [LLMMessage(role="user", content="hi")]
        )
    assert calls == 1
