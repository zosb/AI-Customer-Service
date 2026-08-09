from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path
from typing import Any

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
LOCAL_ACCOUNT_HOSTS = ("localhost", "127.0.0.1")


class BootstrapError(RuntimeError):
    """数据库初始化失败。"""


def validate_identifier(value: str, field_name: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise BootstrapError(
            f"{field_name} 只能包含英文字母、数字和下划线：{value}"
        )
    return value


def validate_application_password(password: str) -> None:
    """提前验证项目账号密码，避免 MySQL 客户端认证阶段出现编码错误。"""
    if password == "CHANGE_ME":
        raise BootstrapError("请先在项目根目录 .env 中设置 MYSQL_PASSWORD")

    try:
        password.encode("ascii")
    except UnicodeEncodeError as exc:
        raise BootstrapError(
            "MYSQL_PASSWORD 不能包含中文、全角符号或其他非 ASCII 字符。"
            "请只使用英文字母、数字和英文半角符号。"
        ) from exc

    if len(password) < 12:
        raise BootstrapError("MYSQL_PASSWORD 至少需要 12 个字符")

    password_rules = (
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
        any(not char.isalnum() for char in password),
    )
    if not all(password_rules):
        raise BootstrapError(
            "MYSQL_PASSWORD 必须同时包含大写字母、小写字母、数字和英文特殊符号"
        )


def connect(
    *,
    user: str,
    password: str,
    database: str | None = None,
) -> Connection:
    settings = get_settings()
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=user,
        password=password,
        database=database,
        charset=settings.mysql_charset,
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=10,
        read_timeout=10,
        write_timeout=10,
    )


def fetch_one(cursor: Any, sql: str) -> dict[str, Any]:
    cursor.execute(sql)
    row = cursor.fetchone()
    if not isinstance(row, dict):
        raise BootstrapError(f"SQL 未返回有效结果：{sql}")
    return row


def create_database_and_users(root_password: str) -> None:
    settings = get_settings()
    database_name = validate_identifier(
        settings.mysql_database,
        "MYSQL_DATABASE",
    )
    app_user = validate_identifier(
        settings.mysql_user,
        "MYSQL_USER",
    )
    validate_application_password(settings.mysql_password)

    connection = connect(user="root", password=root_password)
    try:
        with connection.cursor() as cursor:
            server_info = fetch_one(
                cursor,
                """
                SELECT
                    VERSION() AS version,
                    @@port AS port,
                    @@character_set_server AS character_set_server,
                    @@collation_server AS collation_server
                """,
            )
            print("Root 管理连接成功")
            print(f"MySQL 版本：{server_info['version']}")
            print(f"MySQL 端口：{server_info['port']}")

            cursor.execute(
                f"""
                CREATE DATABASE IF NOT EXISTS `{database_name}`
                CHARACTER SET utf8mb4
                COLLATE utf8mb4_0900_ai_ci
                """
            )
            print(f"正式数据库已就绪：{database_name}")

            for account_host in LOCAL_ACCOUNT_HOSTS:
                cursor.execute(
                    f"""
                    CREATE USER IF NOT EXISTS
                    '{app_user}'@'{account_host}'
                    IDENTIFIED BY %s
                    """,
                    (settings.mysql_password,),
                )
                cursor.execute(
                    f"""
                    ALTER USER
                    '{app_user}'@'{account_host}'
                    IDENTIFIED BY %s
                    """,
                    (settings.mysql_password,),
                )
                cursor.execute(
                    f"""
                    GRANT ALL PRIVILEGES
                    ON `{database_name}`.*
                    TO '{app_user}'@'{account_host}'
                    """
                )
                print(
                    "项目账号已就绪："
                    f"'{app_user}'@'{account_host}'"
                )
    finally:
        connection.close()


def verify_application_account() -> None:
    settings = get_settings()
    validate_application_password(settings.mysql_password)

    connection = connect(
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
    )
    try:
        with connection.cursor() as cursor:
            info = fetch_one(
                cursor,
                """
                SELECT
                    DATABASE() AS database_name,
                    CURRENT_USER() AS authenticated_account,
                    @@character_set_database AS character_set_database,
                    @@collation_database AS collation_database
                """,
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bootstrap_permission_probe (
                    id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
                    note VARCHAR(64) NOT NULL
                ) ENGINE=InnoDB
                DEFAULT CHARACTER SET utf8mb4
                COLLATE utf8mb4_0900_ai_ci
                """
            )
            expected_note = "权限验证成功"
            cursor.execute(
                """
                INSERT INTO bootstrap_permission_probe (id, note)
                VALUES (1, %s)
                ON DUPLICATE KEY UPDATE note = VALUES(note)
                """,
                (expected_note,),
            )
            probe = fetch_one(
                cursor,
                """
                SELECT id, note
                FROM bootstrap_permission_probe
                WHERE id = 1
                """
            )
            cursor.execute("DROP TABLE bootstrap_permission_probe")

            if probe["note"] != expected_note:
                raise BootstrapError("项目账号中文读写验证失败")

            print("项目账号连接成功")
            print(f"当前数据库：{info['database_name']}")
            print(f"认证账号：{info['authenticated_account']}")
            print(f"数据库字符集：{info['character_set_database']}")
            print(f"数据库排序规则：{info['collation_database']}")
            print("项目账号建表、中文写入、读取和删表权限验证成功")
    finally:
        connection.close()


def main() -> int:
    settings = get_settings()

    try:
        validate_application_password(settings.mysql_password)
    except BootstrapError as exc:
        print(f"初始化失败：{exc}", file=sys.stderr)
        return 1

    print("即将创建正式项目数据库和专用 MySQL 账号。")
    root_password = getpass.getpass(
        "请输入 MySQL root 密码（输入时不会显示）："
    )

    try:
        create_database_and_users(root_password)
        verify_application_account()
        print("MySQL 正式数据库初始化完成")
        return 0
    except pymysql.MySQLError as exc:
        print(f"MySQL 初始化失败：{exc}", file=sys.stderr)
        return 1
    except BootstrapError as exc:
        print(f"初始化失败：{exc}", file=sys.stderr)
        return 1
    except UnicodeEncodeError:
        print(
            "初始化失败：MYSQL_PASSWORD 含有当前 MySQL 客户端无法用于认证的字符。"
            "请改为仅包含 ASCII 字符的强密码。",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            f"未预期错误：{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
