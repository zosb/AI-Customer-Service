"""本地大模型与向量模型服务。"""

from app.services.llm.embedding_service import (
    EmbeddingService,
    EmbeddingServiceError,
)

__all__ = [
    "EmbeddingService",
    "EmbeddingServiceError",
]
