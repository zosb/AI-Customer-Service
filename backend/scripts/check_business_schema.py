from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import engine

EXPECTED_TABLES = {
    "alembic_version",
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


def main() -> int:
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    missing_tables = EXPECTED_TABLES - actual_tables
    unexpected_tables = actual_tables - EXPECTED_TABLES

    print("业务表结构检查")
    print(f"预期表数量：{len(EXPECTED_TABLES)}")
    print(f"实际表数量：{len(actual_tables)}")
    print("实际数据表：" + ", ".join(sorted(actual_tables)))

    if missing_tables:
        print("缺少数据表：" + ", ".join(sorted(missing_tables)), file=sys.stderr)
        return 1

    if unexpected_tables:
        print("额外数据表：" + ", ".join(sorted(unexpected_tables)))

    key_columns = {
        "users": {"id", "email", "phone", "password_hash", "role", "status"},
        "knowledge_documents": {
            "id",
            "knowledge_base_id",
            "status",
            "sha256",
            "chunk_count",
        },
        "knowledge_chunks": {
            "id",
            "document_id",
            "vector_id",
            "content_text",
        },
        "chat_messages": {
            "id",
            "session_id",
            "content",
            "intent",
            "retrieval_status",
            "follow_up_suggestions",
        },
        "message_sources": {
            "message_id",
            "document_name",
            "chunk_summary",
            "rank",
        },
        "daily_question_usage": {
            "user_id",
            "usage_date",
            "question_count",
        },
    }

    for table_name, expected_columns in key_columns.items():
        actual_columns = {
            item["name"] for item in inspector.get_columns(table_name)
        }
        missing_columns = expected_columns - actual_columns
        if missing_columns:
            print(
                f"{table_name} 缺少字段："
                + ", ".join(sorted(missing_columns)),
                file=sys.stderr,
            )
            return 1
        print(f"{table_name} 关键字段检查通过")

    print("业务表结构检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
