from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import engine


def main() -> int:
    try:
        with engine.connect() as connection:
            row: dict[str, Any] = dict(
                connection.execute(
                    text(
                        """
                        SELECT
                            VERSION() AS version,
                            DATABASE() AS database_name,
                            CURRENT_USER() AS authenticated_account,
                            @@character_set_database AS character_set_database,
                            @@collation_database AS collation_database
                        """
                    )
                ).mappings().one()
            )

        table_names = inspect(engine).get_table_names()

        print("SQLAlchemy 数据库连接成功")
        print(f"MySQL 版本：{row['version']}")
        print(f"当前数据库：{row['database_name']}")
        print(f"认证账号：{row['authenticated_account']}")
        print(f"数据库字符集：{row['character_set_database']}")
        print(f"数据库排序规则：{row['collation_database']}")
        print(
            "当前数据表："
            + (", ".join(table_names) if table_names else "暂无业务表")
        )
        return 0
    except SQLAlchemyError as exc:
        print(f"SQLAlchemy 数据库检查失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
