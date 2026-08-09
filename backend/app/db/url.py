from __future__ import annotations

from sqlalchemy import URL

from app.core.config import Settings


def build_database_url(settings: Settings) -> URL:
    """使用结构化参数创建 MySQL URL，安全处理密码中的特殊字符。"""
    return URL.create(
        drivername="mysql+pymysql",
        username=settings.mysql_user,
        password=settings.mysql_password,
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        query={"charset": settings.mysql_charset},
    )
