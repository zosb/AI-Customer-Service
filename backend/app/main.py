from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI 智能客服系统后端 API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["系统状态"], summary="后端根接口")
def root() -> dict[str, str]:
    """返回服务入口信息。"""
    return {
        "message": "AI Customer Service API is running",
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
