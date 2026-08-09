from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterator, Literal, Sequence

import httpx

from app.core.config import get_settings
from app.services.llm.retry import OllamaRetryPolicy


class ChatGenerationError(RuntimeError):
    """Ollama 对话生成失败或响应不符合预期。"""


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatGenerationResult:
    content: str
    model: str
    prompt_token_count: int | None
    completion_token_count: int | None
    total_duration_ns: int | None
    load_duration_ns: int | None


@dataclass(frozen=True)
class ChatStreamChunk:
    content: str
    done: bool
    model: str
    prompt_token_count: int | None = None
    completion_token_count: int | None = None
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None


class OllamaChatService:
    """通过本地 Ollama /api/chat 调用正式客服生成模型。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        num_ctx: int | None = None,
        client: httpx.Client | None = None,
        retry_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        settings = get_settings()

        self.base_url = (
            base_url or settings.ollama_base_url
        ).rstrip("/")
        self.model = model or settings.ollama_chat_model
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.ollama_request_timeout_seconds
        )
        self.num_ctx = (
            num_ctx
            if num_ctx is not None
            else settings.ollama_num_ctx
        )
        self._client = client
        self.retry_policy = OllamaRetryPolicy(
            max_attempts=(
                retry_attempts
                if retry_attempts is not None
                else settings.ollama_retry_attempts
            ),
            backoff_seconds=(
                retry_backoff_seconds
                if retry_backoff_seconds is not None
                else settings.ollama_retry_backoff_seconds
            ),
        )

        if not self.base_url:
            raise ValueError("Ollama base_url 不能为空")
        if not self.model:
            raise ValueError("Ollama Chat 模型名称不能为空")
        if self.timeout_seconds <= 0:
            raise ValueError("请求超时时间必须大于 0")
        if self.num_ctx < 1024:
            raise ValueError("num_ctx 不能小于 1024")

    def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.15,
    ) -> ChatGenerationResult:
        normalized = self._normalize_messages(messages)
        self._validate_temperature(temperature)

        payload = self._payload(
            normalized,
            stream=False,
            temperature=temperature,
        )

        response = self._post_with_retry(payload)

        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            raise ChatGenerationError(
                "Ollama Chat 请求失败："
                f"HTTP {response.status_code}"
                f"{' - ' + detail if detail else ''}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ChatGenerationError(
                "Ollama Chat 返回了无效 JSON"
            ) from exc

        message = data.get("message")
        if not isinstance(message, dict):
            raise ChatGenerationError(
                "Ollama Chat 响应缺少 message"
            )

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ChatGenerationError(
                "Ollama Chat 返回了空回答"
            )

        return ChatGenerationResult(
            content=content.strip(),
            model=self._resolve_model(data),
            prompt_token_count=self._optional_non_negative_int(
                data.get("prompt_eval_count")
            ),
            completion_token_count=self._optional_non_negative_int(
                data.get("eval_count")
            ),
            total_duration_ns=self._optional_non_negative_int(
                data.get("total_duration")
            ),
            load_duration_ns=self._optional_non_negative_int(
                data.get("load_duration")
            ),
        )

    def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.15,
    ) -> Iterator[ChatStreamChunk]:
        """
        流式调用 Ollama /api/chat。

        502/503/504 或连接错误只在"尚未向上游输出 token"时重试。
        一旦已经输出任何 token，就绝不重新开始请求，避免浏览器收到
        重复文本；此时交给上层 SSE replace + 安全兜底处理。
        """
        normalized = self._normalize_messages(messages)
        self._validate_temperature(temperature)

        payload = self._payload(
            normalized,
            stream=True,
            temperature=temperature,
        )

        if self._client is not None:
            yield from self._stream_with_retry(
                self._client,
                payload,
            )
            return

        with httpx.Client(
            timeout=self.timeout_seconds,
            # 本机 Ollama 不应经过系统/环境代理。
            trust_env=False,
        ) as client:
            yield from self._stream_with_retry(
                client,
                payload,
            )

    def _post_with_retry(
        self,
        payload: dict,
    ) -> httpx.Response:
        last_error: Exception | None = None

        for attempt in range(
            1,
            self.retry_policy.max_attempts + 1,
        ):
            try:
                if self._client is not None:
                    response = self._client.post(
                        f"{self.base_url}/api/chat",
                        json=payload,
                        timeout=self.timeout_seconds,
                    )
                else:
                    with httpx.Client(
                        timeout=self.timeout_seconds,
                        trust_env=False,
                    ) as client:
                        response = client.post(
                            f"{self.base_url}/api/chat",
                            json=payload,
                        )
            except httpx.TimeoutException as exc:
                last_error = exc
                if self.retry_policy.can_retry(
                    attempt=attempt
                ):
                    self.retry_policy.wait(attempt)
                    continue
                raise ChatGenerationError(
                    "Ollama Chat 请求超时"
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if self.retry_policy.can_retry(
                    attempt=attempt
                ):
                    self.retry_policy.wait(attempt)
                    continue
                raise ChatGenerationError(
                    "无法连接 Ollama Chat 服务"
                ) from exc

            if self.retry_policy.can_retry(
                attempt=attempt,
                status_code=response.status_code,
            ):
                self.retry_policy.wait(attempt)
                continue
            return response

        raise ChatGenerationError(
            "Ollama Chat 重试后仍然失败"
        ) from last_error

    def _stream_with_retry(
        self,
        client: httpx.Client,
        payload: dict,
    ) -> Iterator[ChatStreamChunk]:
        last_error: Exception | None = None

        for attempt in range(
            1,
            self.retry_policy.max_attempts + 1,
        ):
            emitted = False
            try:
                with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout_seconds,
                ) as response:
                    if response.status_code >= 400:
                        body = response.read()
                        error_response = httpx.Response(
                            response.status_code,
                            content=body,
                            headers=response.headers,
                        )
                        if self.retry_policy.can_retry(
                            attempt=attempt,
                            status_code=response.status_code,
                        ):
                            self.retry_policy.wait(attempt)
                            continue

                        detail = self._extract_error_detail(
                            error_response
                        )
                        raise ChatGenerationError(
                            "Ollama Chat 流式请求失败："
                            f"HTTP {response.status_code}"
                            f"{' - ' + detail if detail else ''}"
                        )

                    saw_done = False
                    for line in response.iter_lines():
                        if not line or not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ChatGenerationError(
                                "Ollama Chat 流式响应包含无效 JSON"
                            ) from exc

                        if not isinstance(data, dict):
                            raise ChatGenerationError(
                                "Ollama Chat 流式响应格式无效"
                            )

                        if isinstance(data.get("error"), str):
                            raise ChatGenerationError(
                                "Ollama Chat 流式生成失败："
                                f"{data['error']}"
                            )

                        message = data.get("message")
                        content = ""
                        if isinstance(message, dict):
                            raw = message.get("content")
                            if isinstance(raw, str):
                                content = raw

                        done = bool(data.get("done"))
                        if done:
                            saw_done = True

                        if content or done:
                            if content:
                                emitted = True
                            yield ChatStreamChunk(
                                content=content,
                                done=done,
                                model=self._resolve_model(data),
                                prompt_token_count=(
                                    self._optional_non_negative_int(
                                        data.get("prompt_eval_count")
                                    )
                                ),
                                completion_token_count=(
                                    self._optional_non_negative_int(
                                        data.get("eval_count")
                                    )
                                ),
                                total_duration_ns=(
                                    self._optional_non_negative_int(
                                        data.get("total_duration")
                                    )
                                ),
                                load_duration_ns=(
                                    self._optional_non_negative_int(
                                        data.get("load_duration")
                                    )
                                ),
                            )

                    if not saw_done:
                        raise ChatGenerationError(
                            "Ollama Chat 流式响应提前结束"
                        )
                    return

            except ChatGenerationError:
                raise
            except httpx.TimeoutException as exc:
                last_error = exc
                if (
                    not emitted
                    and self.retry_policy.can_retry(
                        attempt=attempt
                    )
                ):
                    self.retry_policy.wait(attempt)
                    continue
                raise ChatGenerationError(
                    "Ollama Chat 流式请求超时"
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if (
                    not emitted
                    and self.retry_policy.can_retry(
                        attempt=attempt
                    )
                ):
                    self.retry_policy.wait(attempt)
                    continue
                raise ChatGenerationError(
                    "无法连接 Ollama Chat 流式服务"
                ) from exc

        raise ChatGenerationError(
            "Ollama Chat 流式重试后仍然失败"
        ) from last_error

    def _payload(
        self,
        messages: Sequence[LLMMessage],
        *,
        stream: bool,
        temperature: float,
    ) -> dict:
        return {
            "model": self.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "stream": stream,
            "think": False,
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": temperature,
            },
        }

    @staticmethod
    def _validate_temperature(
        temperature: float,
    ) -> None:
        if not 0.0 <= temperature <= 2.0:
            raise ValueError(
                "temperature 必须在 0 到 2 之间"
            )

    @staticmethod
    def _normalize_messages(
        messages: Sequence[LLMMessage],
    ) -> list[LLMMessage]:
        if isinstance(messages, (str, bytes)):
            raise ValueError(
                "messages 必须是 LLMMessage 序列"
            )
        if not messages:
            raise ValueError("messages 不能为空")

        normalized: list[LLMMessage] = []

        for index, item in enumerate(messages):
            if not isinstance(item, LLMMessage):
                raise TypeError(
                    f"第 {index + 1} 条消息必须是 LLMMessage"
                )

            content = item.content.strip()
            if not content:
                raise ValueError(
                    f"第 {index + 1} 条消息内容不能为空"
                )

            normalized.append(
                LLMMessage(
                    role=item.role,
                    content=content,
                )
            )

        return normalized

    def _resolve_model(
        self,
        data: dict,
    ) -> str:
        response_model = data.get("model")
        if (
            isinstance(response_model, str)
            and response_model.strip()
        ):
            return response_model.strip()
        return self.model

    @staticmethod
    def _extract_error_detail(
        response: httpx.Response,
    ) -> str | None:
        try:
            data = response.json()
        except ValueError:
            body = response.text.strip()
            return body[:500] or None

        if isinstance(data, dict):
            for key in ("error", "detail", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:500]

        return None

    @staticmethod
    def _optional_non_negative_int(
        value: object,
    ) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if value < 0:
            return None
        return value
