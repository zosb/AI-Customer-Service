from __future__ import annotations

import httpx
import pytest

from app.services.llm.chat_service import (
    ChatGenerationError,
    LLMMessage,
    OllamaChatService,
)


def make_service(handler):
    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    return OllamaChatService(
        base_url="http://ollama.test",
        model="qwen3.5:4b",
        timeout_seconds=10,
        num_ctx=4096,
        client=client,
    )


def test_generate_returns_content_and_token_usage():
    def handler(request):
        payload = request.read().decode("utf-8")
        assert '"stream":false' in payload
        assert '"think":false' in payload
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:4b",
                "message": {
                    "role": "assistant",
                    "content": "退款通常三个工作日到账。",
                },
                "prompt_eval_count": 120,
                "eval_count": 18,
                "total_duration": 123456,
                "load_duration": 2345,
            },
        )

    service = make_service(handler)
    result = service.generate(
        [
            LLMMessage(
                role="system",
                content="你是客服。",
            ),
            LLMMessage(
                role="user",
                content="退款多久？",
            ),
        ]
    )

    assert result.content == "退款通常三个工作日到账。"
    assert result.model == "qwen3.5:4b"
    assert result.prompt_token_count == 120
    assert result.completion_token_count == 18


def test_generate_rejects_empty_messages():
    service = make_service(
        lambda request: httpx.Response(200)
    )

    with pytest.raises(
        ValueError,
        match="messages 不能为空",
    ):
        service.generate([])


def test_generate_rejects_empty_message_content():
    service = make_service(
        lambda request: httpx.Response(200)
    )

    with pytest.raises(
        ValueError,
        match="内容不能为空",
    ):
        service.generate(
            [
                LLMMessage(
                    role="user",
                    content="   ",
                )
            ]
        )


def test_http_error_is_converted_to_domain_error():
    service = make_service(
        lambda request: httpx.Response(
            500,
            json={"error": "model crashed"},
        )
    )

    with pytest.raises(
        ChatGenerationError,
        match="HTTP 500.*model crashed",
    ):
        service.generate(
            [
                LLMMessage(
                    role="user",
                    content="hello",
                )
            ]
        )


def test_invalid_json_is_rejected():
    service = make_service(
        lambda request: httpx.Response(
            200,
            content=b"not-json",
        )
    )

    with pytest.raises(
        ChatGenerationError,
        match="无效 JSON",
    ):
        service.generate(
            [
                LLMMessage(
                    role="user",
                    content="hello",
                )
            ]
        )


def test_empty_model_answer_is_rejected():
    service = make_service(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "   ",
                }
            },
        )
    )

    with pytest.raises(
        ChatGenerationError,
        match="空回答",
    ):
        service.generate(
            [
                LLMMessage(
                    role="user",
                    content="hello",
                )
            ]
        )
