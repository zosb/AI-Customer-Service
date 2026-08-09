from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.core.config import get_settings
from app.services.llm.retry import OllamaRetryPolicy


class EmbeddingServiceError(RuntimeError):
    """Embedding 请求失败或响应不符合预期。"""


class EmbeddingService:
    """通过本地 Ollama /api/embed 生成文本向量。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
        retry_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        settings = get_settings()

        self.base_url = (
            base_url or settings.ollama_base_url
        ).rstrip("/")
        self.model = model or settings.ollama_embedding_model
        self.dimension = (
            dimension
            if dimension is not None
            else settings.ollama_embedding_dimension
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.ollama_request_timeout_seconds
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
            raise ValueError("Embedding 模型名称不能为空")
        if self.dimension <= 0:
            raise ValueError("Embedding 维度必须大于 0")
        if self.timeout_seconds <= 0:
            raise ValueError("请求超时时间必须大于 0")

    def embed_text(self, text: str) -> list[float]:
        """生成单条文本向量。"""
        return self.embed_texts([text])[0]

    def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """批量生成文本向量并严格校验数量和维度。"""
        normalized = self._normalize_texts(texts)

        payload = {
            "model": self.model,
            "input": normalized,
        }

        response = self._post_with_retry(payload)

        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            raise EmbeddingServiceError(
                f"Ollama Embedding 请求失败："
                f"HTTP {response.status_code}"
                f"{' - ' + detail if detail else ''}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise EmbeddingServiceError(
                "Ollama Embedding 返回了无效 JSON"
            ) from exc

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list):
            raise EmbeddingServiceError(
                "Ollama Embedding 响应缺少 embeddings"
            )

        if len(embeddings) != len(normalized):
            raise EmbeddingServiceError(
                "Embedding 数量与输入文本数量不一致"
            )

        validated: list[list[float]] = []

        for index, embedding in enumerate(embeddings):
            if not isinstance(embedding, list):
                raise EmbeddingServiceError(
                    f"第 {index + 1} 个 Embedding 格式无效"
                )

            if len(embedding) != self.dimension:
                raise EmbeddingServiceError(
                    f"第 {index + 1} 个 Embedding 维度错误："
                    f"预期 {self.dimension}，实际 {len(embedding)}"
                )

            vector: list[float] = []
            for value in embedding:
                if isinstance(value, bool) or not isinstance(
                    value,
                    (int, float),
                ):
                    raise EmbeddingServiceError(
                        f"第 {index + 1} 个 Embedding 包含非数值"
                    )
                vector.append(float(value))

            validated.append(vector)

        return validated

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
                        f"{self.base_url}/api/embed",
                        json=payload,
                        timeout=self.timeout_seconds,
                    )
                else:
                    with httpx.Client(
                        timeout=self.timeout_seconds,
                        # 本机 Ollama 不经过系统代理。
                        trust_env=False,
                    ) as client:
                        response = client.post(
                            f"{self.base_url}/api/embed",
                            json=payload,
                        )
            except httpx.TimeoutException as exc:
                last_error = exc
                if self.retry_policy.can_retry(
                    attempt=attempt
                ):
                    self.retry_policy.wait(attempt)
                    continue
                raise EmbeddingServiceError(
                    "Ollama Embedding 请求超时"
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if self.retry_policy.can_retry(
                    attempt=attempt
                ):
                    self.retry_policy.wait(attempt)
                    continue
                raise EmbeddingServiceError(
                    "无法连接 Ollama Embedding 服务"
                ) from exc

            if self.retry_policy.can_retry(
                attempt=attempt,
                status_code=response.status_code,
            ):
                self.retry_policy.wait(attempt)
                continue
            return response

        raise EmbeddingServiceError(
            "Ollama Embedding 重试后仍然失败"
        ) from last_error

    @staticmethod
    def _normalize_texts(
        texts: Sequence[str],
    ) -> list[str]:
        if isinstance(texts, (str, bytes)):
            raise ValueError(
                "embed_texts 必须接收文本序列，不能直接传字符串"
            )

        normalized: list[str] = []

        for index, text in enumerate(texts):
            if not isinstance(text, str):
                raise ValueError(
                    f"第 {index + 1} 条输入必须是字符串"
                )

            value = text.strip()
            if not value:
                raise ValueError(
                    f"第 {index + 1} 条输入不能为空"
                )

            normalized.append(value)

        if not normalized:
            raise ValueError("Embedding 输入不能为空")

        return normalized

    @staticmethod
    def _extract_error_detail(
        response: httpx.Response,
    ) -> str:
        try:
            data = response.json()
        except ValueError:
            # 代理服务器常返回 HTML / 纯文本 502。保留响应正文，
            # 让错误日志能够直接显示真实上游信息。
            body = response.text.strip()
            return body[:500]

        if isinstance(data, dict):
            for key in ("error", "detail", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:500]

        return ""
