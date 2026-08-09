from app.core.config import Settings


def test_large_context_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.rag_max_sources == 8
    assert settings.rag_max_chunks_per_document == 2
    assert settings.rag_critical_priority == 5
    assert settings.rag_answer_guard_enabled is True
    assert settings.rag_answer_repair_attempts == 1


def test_stage70_ollama_retry_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.ollama_retry_attempts == 3
    assert settings.ollama_retry_backoff_seconds == 0.25
