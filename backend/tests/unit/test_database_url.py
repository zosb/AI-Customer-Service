from app.core.config import Settings
from app.db.url import build_database_url


def test_database_url_contains_expected_components() -> None:
    settings = Settings(
        _env_file=None,
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="ai_customer_service",
        mysql_password="test-password",
        mysql_database="ai_customer_service",
        mysql_charset="utf8mb4",
    )

    url = build_database_url(settings)

    assert url.drivername == "mysql+pymysql"
    assert url.username == "ai_customer_service"
    assert url.password == "test-password"
    assert url.host == "127.0.0.1"
    assert url.port == 3306
    assert url.database == "ai_customer_service"
    assert url.query["charset"] == "utf8mb4"


def test_database_url_safely_handles_special_password_characters() -> None:
    settings = Settings(
        _env_file=None,
        mysql_password="p@ss:/?#%word",
    )

    url = build_database_url(settings)
    rendered = url.render_as_string(hide_password=False)

    assert url.password == "p@ss:/?#%word"
    assert "p%40ss%3A%2F%3F%23%25word" in rendered
