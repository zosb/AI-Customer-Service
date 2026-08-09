from __future__ import annotations

import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.services.llm.chat_service import (
    ChatGenerationError,
    LLMMessage,
    OllamaChatService,
)
from app.services.llm.embedding_service import (
    EmbeddingService,
    EmbeddingServiceError,
)


def _model_names(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    models = payload.get("models")
    if not isinstance(models, list):
        return set()

    names: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        for key in ("name", "model"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                names.add(value.strip())
    return names


def main() -> int:
    settings = get_settings()
    base_url = settings.ollama_base_url.rstrip("/")

    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            version_response = client.get(f"{base_url}/api/version")
            version_response.raise_for_status()
            version_payload = version_response.json()
            version = (
                version_payload.get("version")
                if isinstance(version_payload, dict)
                else None
            )

            tags_response = client.get(f"{base_url}/api/tags")
            tags_response.raise_for_status()
            installed_models = _model_names(tags_response.json())
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        print(f"Ollama 服务检查失败：{exc}", file=sys.stderr)
        print(
            "请确认 Ollama 已启动，并检查 OLLAMA_BASE_URL。",
            file=sys.stderr,
        )
        return 1

    print(f"Ollama 服务连接成功：{version or 'version unknown'}")

    required_models = {
        settings.ollama_chat_model,
        settings.ollama_embedding_model,
    }
    missing_models = required_models - installed_models
    if missing_models:
        print("缺少 Ollama 模型：", file=sys.stderr)
        for model in sorted(missing_models):
            print(f"- {model}", file=sys.stderr)
        print(
            "请先执行 ollama pull <model> 下载缺失模型。",
            file=sys.stderr,
        )
        return 1

    print("Ollama 必需模型检查通过")

    try:
        embedding = EmbeddingService().embed_text("运行健康检查")
    except EmbeddingServiceError as exc:
        print(f"Embedding 实际调用失败：{exc}", file=sys.stderr)
        return 1

    if len(embedding) != settings.ollama_embedding_dimension:
        print(
            "Embedding 维度不一致："
            f"预期 {settings.ollama_embedding_dimension}，"
            f"实际 {len(embedding)}",
            file=sys.stderr,
        )
        return 1

    print(
        "Embedding 实际调用通过："
        f"{len(embedding)} 维"
    )

    try:
        result = OllamaChatService().generate(
            [
                LLMMessage(
                    role="user",
                    content="这是运行健康检查，请只回复 OK。",
                )
            ],
            temperature=0.0,
        )
    except ChatGenerationError as exc:
        print(f"Chat 模型实际调用失败：{exc}", file=sys.stderr)
        return 1

    print(
        "Chat 模型实际调用通过："
        f"{result.model}，返回内容非空"
    )
    print("Ollama 运行检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
