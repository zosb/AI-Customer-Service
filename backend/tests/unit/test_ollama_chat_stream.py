from __future__ import annotations

import json

import httpx
import pytest

from app.services.llm.chat_service import (
    ChatGenerationError,
    LLMMessage,
    OllamaChatService,
)


def service(handler):
    return OllamaChatService(
        base_url="http://ollama.test",
        model="qwen3.5:4b",
        timeout_seconds=10,
        num_ctx=4096,
        client=httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
    )


def test_stream_yields_delta_and_final_usage():
    def handler(request):
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["think"] is False
        content = (
            b'{"model":"qwen3.5:4b","message":{"role":"assistant",'
            b'"content":"\\u4e09\\u4e2a"},"done":false}\n'
            b'{"model":"qwen3.5:4b","message":{"role":"assistant",'
            b'"content":"\\u5de5\\u4f5c\\u65e5"},"done":false}\n'
            b'{"model":"qwen3.5:4b","message":{"role":"assistant",'
            b'"content":""},"done":true,"prompt_eval_count":100,'
            b'"eval_count":12}\n'
        )
        return httpx.Response(
            200,
            content=content,
            headers={
                "content-type":
                    "application/x-ndjson"
            },
        )

    chunks = list(
        service(handler).stream(
            [
                LLMMessage(
                    role="user",
                    content="退款多久？",
                )
            ]
        )
    )

    assert "".join(
        item.content
        for item in chunks
    ) == "三个工作日"
    assert chunks[-1].done is True
    assert chunks[-1].prompt_token_count == 100
    assert chunks[-1].completion_token_count == 12


def test_stream_rejects_invalid_ndjson():
    def handler(request):
        del request
        return httpx.Response(
            200,
            content=b"not-json\n",
        )

    with pytest.raises(
        ChatGenerationError,
        match="无效 JSON",
    ):
        list(
            service(handler).stream(
                [
                    LLMMessage(
                        role="user",
                        content="hi",
                    )
                ]
            )
        )


def test_stream_requires_done_frame():
    def handler(request):
        del request
        return httpx.Response(
            200,
            content=(
                b'{"message":{"content":"partial"},'
                b'"done":false}\n'
            ),
        )

    with pytest.raises(
        ChatGenerationError,
        match="提前结束",
    ):
        list(
            service(handler).stream(
                [
                    LLMMessage(
                        role="user",
                        content="hi",
                    )
                ]
            )
        )


def test_stream_http_error_is_domain_error():
    def handler(request):
        del request
        return httpx.Response(
            500,
            json={"error": "stream crashed"},
        )

    with pytest.raises(
        ChatGenerationError,
        match="HTTP 500.*stream crashed",
    ):
        list(
            service(handler).stream(
                [
                    LLMMessage(
                        role="user",
                        content="hi",
                    )
                ]
            )
        )
