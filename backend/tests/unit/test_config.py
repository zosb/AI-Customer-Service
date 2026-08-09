from pathlib import Path

from app.core.config import BACKEND_ROOT, Settings


def test_default_business_limits() -> None:
    settings = Settings(_env_file=None)

    assert settings.question_max_length == 500
    assert settings.daily_question_limit == 100
    assert settings.follow_up_suggestion_count == 3


def test_required_document_extensions() -> None:
    settings = Settings(
        _env_file=None,
        allowed_document_extensions=".TXT,.md,.pdf",
    )

    assert settings.allowed_document_extensions == (".txt", ".md", ".pdf")


def test_relative_storage_paths_resolve_under_backend() -> None:
    settings = Settings(
        _env_file=None,
        chroma_persist_dir="storage/chroma",
        upload_dir="storage/uploads",
    )

    assert settings.chroma_persist_dir == (
        BACKEND_ROOT / Path("storage/chroma")
    ).resolve()
    assert settings.upload_dir == (
        BACKEND_ROOT / Path("storage/uploads")
    ).resolve()


def test_embedding_configuration_matches_selected_model() -> None:
    settings = Settings(_env_file=None)

    assert settings.ollama_embedding_model == "qwen3-embedding:0.6b"
    assert settings.ollama_embedding_dimension == 1024
