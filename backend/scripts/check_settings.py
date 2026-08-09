from __future__ import annotations

import sys
from pathlib import Path

# 允许直接执行：
# python scripts/check_settings.py
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import ENV_FILE, get_settings


def main() -> int:
    settings = get_settings()

    print("配置读取成功")
    print(f"环境文件：{ENV_FILE}")
    print(f"应用名称：{settings.app_name}")
    print(f"运行环境：{settings.environment}")
    print(f"API 前缀：{settings.api_v1_prefix}")
    print(f"前端地址：{settings.frontend_origin}")
    print(f"MySQL：{settings.mysql_safe_dsn}")
    print(f"Ollama 生成模型：{settings.ollama_chat_model}")
    print(f"Ollama Embedding：{settings.ollama_embedding_model}")
    print(f"Embedding 维度：{settings.ollama_embedding_dimension}")
    print(f"Chroma 目录：{settings.chroma_persist_dir}")
    print(f"上传目录：{settings.upload_dir}")
    print(f"允许格式：{','.join(settings.allowed_document_extensions)}")
    print(f"单次问题上限：{settings.question_max_length}")
    print(f"每日问题上限：{settings.daily_question_limit}")
    print(f"RAG Top-K：{settings.rag_top_k}")
    print(f"相似度阈值：{settings.rag_similarity_threshold}")

    errors: list[str] = []

    if not ENV_FILE.exists():
        errors.append("项目根目录缺少 .env 文件")
    if settings.mysql_password == "CHANGE_ME":
        errors.append("MYSQL_PASSWORD 仍是占位值")
    if settings.jwt_secret_key == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET":
        errors.append("JWT_SECRET_KEY 仍是占位值")
    if settings.ollama_embedding_dimension != 1024:
        errors.append("Embedding 维度必须与 qwen3-embedding:0.6b 的 1024 维一致")
    if settings.chunk_overlap >= settings.chunk_size:
        errors.append("CHUNK_OVERLAP 必须小于 CHUNK_SIZE")

    if errors:
        print("\n配置校验未通过：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    print("配置校验通过")
    print("存储目录检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
