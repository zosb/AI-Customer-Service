from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models.user import User


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_auth_api_with_real_mysql() -> None:
    """通过真实 FastAPI + SQLAlchemy + MySQL 验证认证接口。"""
    account = f"auth-api-{uuid4().hex}@example.com"
    password = "ApiIntegration123!"
    display_name = "接口测试用户"

    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            anonymous_response = await client.get("/api/v1/auth/me")
            assert anonymous_response.status_code == 401

            register_response = await client.post(
                "/api/v1/auth/register",
                json={
                    "account": account,
                    "password": password,
                    "display_name": display_name,
                },
            )
            assert register_response.status_code == 201
            registered_user = register_response.json()
            assert registered_user["email"] == account
            assert registered_user["phone"] is None
            assert registered_user["display_name"] == display_name
            assert registered_user["role"] == "user"
            assert registered_user["status"] == "active"
            user_id = registered_user["id"]

            duplicate_response = await client.post(
                "/api/v1/auth/register",
                json={
                    "account": account.upper(),
                    "password": password,
                },
            )
            assert duplicate_response.status_code == 409

            wrong_password_response = await client.post(
                "/api/v1/auth/login",
                json={
                    "account": account,
                    "password": "WrongPassword123!",
                },
            )
            assert wrong_password_response.status_code == 401

            login_response = await client.post(
                "/api/v1/auth/login",
                json={
                    "account": account.upper(),
                    "password": password,
                },
            )
            assert login_response.status_code == 200
            login_data = login_response.json()
            assert login_data["token_type"] == "bearer"
            assert login_data["expires_in"] > 0
            assert login_data["user"]["id"] == user_id
            access_token = login_data["access_token"]
            assert access_token

            me_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert me_response.status_code == 200
            assert me_response.json()["id"] == user_id
            assert me_response.json()["email"] == account

            invalid_token_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid-token"},
            )
            assert invalid_token_response.status_code == 401

        with SessionLocal() as database:
            stored_user = database.scalar(
                select(User).where(User.email == account)
            )
            assert stored_user is not None
            assert stored_user.last_login_at is not None
    finally:
        with SessionLocal() as database:
            database.execute(delete(User).where(User.email == account))
            database.commit()

        with SessionLocal() as database:
            remaining_user = database.scalar(
                select(User).where(User.email == account)
            )
            assert remaining_user is None
