from __future__ import annotations

from dataclasses import dataclass
import time


RETRYABLE_OLLAMA_STATUS_CODES = frozenset({502, 503, 504})


@dataclass(frozen=True)
class OllamaRetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts 必须大于 0")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds 不能小于 0")

    def can_retry(
        self,
        *,
        attempt: int,
        status_code: int | None = None,
    ) -> bool:
        if attempt >= self.max_attempts:
            return False
        if status_code is None:
            return True
        return status_code in RETRYABLE_OLLAMA_STATUS_CODES

    def wait(self, attempt: int) -> None:
        if self.backoff_seconds <= 0:
            return
        delay = self.backoff_seconds * (2 ** max(0, attempt - 1))
        time.sleep(delay)
