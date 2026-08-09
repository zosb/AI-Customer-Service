from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["系统状态"])


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: Literal["ok"]
    service: str
    version: str
    environment: str


@router.get(
    "",
    response_model=HealthResponse,
    summary="检查后端服务状态",
)
def health_check() -> HealthResponse:
    """返回不依赖外部组件的基础健康状态。"""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
