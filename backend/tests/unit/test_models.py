from app.db.base import Base
import app.models  # noqa: F401


EXPECTED_TABLES = {
    "users",
    "knowledge_bases",
    "knowledge_documents",
    "knowledge_chunks",
    "chat_sessions",
    "chat_messages",
    "message_sources",
    "message_feedback",
    "daily_question_usage",
}


def test_all_expected_business_tables_are_registered() -> None:
    assert EXPECTED_TABLES.issubset(Base.metadata.tables)


def test_user_supports_phone_or_email_login() -> None:
    columns = Base.metadata.tables["users"].columns

    assert columns["email"].nullable is True
    assert columns["phone"].nullable is True
    assert columns["password_hash"].nullable is False


def test_document_status_and_vector_linkage_columns_exist() -> None:
    document_columns = Base.metadata.tables["knowledge_documents"].columns
    chunk_columns = Base.metadata.tables["knowledge_chunks"].columns

    assert "status" in document_columns
    assert "error_message" in document_columns
    assert "vector_id" in chunk_columns
    assert "content_text" in chunk_columns


def test_message_supports_intent_sources_and_follow_up_suggestions() -> None:
    message_columns = Base.metadata.tables["chat_messages"].columns
    source_columns = Base.metadata.tables["message_sources"].columns

    assert "intent" in message_columns
    assert "routed_knowledge_base_id" in message_columns
    assert "follow_up_suggestions" in message_columns
    assert "document_name" in source_columns
    assert "chunk_summary" in source_columns


def test_daily_usage_has_user_date_uniqueness() -> None:
    table = Base.metadata.tables["daily_question_usage"]
    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if constraint.name is not None
    }

    assert "uq_daily_question_usage_user_date" in constraint_names
