from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import AccessTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.admin_repository import AdminRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.user_repository import SqlAlchemyUserRepository
from app.services.admin.service import AdminService
from app.services.agent.execution_plan_service import AgentExecutionPlanService
from app.services.chat.session_service import ChatSessionService
from app.services.chat.streaming_answer_service import ChatStreamingAnswerService
from app.services.knowledge.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from app.services.knowledge.knowledge_upload_service import (
    KnowledgeUploadService,
)
from app.services.vector.chroma_store import ChromaVectorStore
from app.services.llm.chat_service import OllamaChatService
from app.services.chat.prompt_builder import RAGPromptBuilder

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
    database: Annotated[Session, Depends(get_db)],
) -> User:
    """解析 Bearer JWT 并返回当前登录用户。"""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (AccessTokenError, KeyError, TypeError, ValueError) as exc:
        raise unauthorized from exc

    repository = SqlAlchemyUserRepository(database)
    user = repository.get_by_id(user_id)

    if user is None:
        raise unauthorized
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    return user


def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """仅允许 role=admin 的已登录用户访问管理后台。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def get_admin_repository(
    database: Annotated[Session, Depends(get_db)],
) -> AdminRepository:
    return AdminRepository(database)


def get_admin_service(
    repository: Annotated[
        AdminRepository,
        Depends(get_admin_repository),
    ],
) -> AdminService:
    return AdminService(repository)



def get_agent_execution_plan_service() -> AgentExecutionPlanService:
    return AgentExecutionPlanService()

def get_knowledge_repository(
    database: Annotated[Session, Depends(get_db)],
) -> KnowledgeRepository:
    return KnowledgeRepository(database)


@lru_cache(maxsize=1)
def get_knowledge_vector_store() -> ChromaVectorStore:
    """
    复用正式知识库 Chroma 客户端。

    测试脚本使用独立 verification collection，
    正式 API 固定使用 <prefix>_knowledge。
    """
    settings = get_settings()
    return ChromaVectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=(
            f"{settings.chroma_collection_prefix}_knowledge"
        ),
    )


def get_knowledge_ingestion_service(
    repository: Annotated[
        KnowledgeRepository,
        Depends(get_knowledge_repository),
    ],
) -> KnowledgeIngestionService:
    return KnowledgeIngestionService(
        repository=repository,
        vector_store=get_knowledge_vector_store(),
    )


def get_knowledge_upload_service(
    repository: Annotated[
        KnowledgeRepository,
        Depends(get_knowledge_repository),
    ],
) -> KnowledgeUploadService:
    ingestion_service = KnowledgeIngestionService(
        repository=repository,
        vector_store=get_knowledge_vector_store(),
    )
    return KnowledgeUploadService(
        repository=repository,
        ingestion_service=ingestion_service,
    )


def get_chat_repository(
    database: Annotated[Session, Depends(get_db)],
) -> ChatRepository:
    return ChatRepository(database)


def get_chat_session_service(
    repository: Annotated[
        ChatRepository,
        Depends(get_chat_repository),
    ],
) -> ChatSessionService:
    return ChatSessionService(repository)


def get_chat_streaming_answer_service(
    session_service: Annotated[
        ChatSessionService,
        Depends(get_chat_session_service),
    ],
    knowledge_service: Annotated[
        KnowledgeIngestionService,
        Depends(get_knowledge_ingestion_service),
    ],
) -> ChatStreamingAnswerService:
    return ChatStreamingAnswerService(
        session_service=session_service,
        knowledge_service=knowledge_service,
        chat_model=OllamaChatService(),
        prompt_builder=RAGPromptBuilder(),
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
DatabaseSession = Annotated[Session, Depends(get_db)]

AdminRepositoryDep = Annotated[
    AdminRepository,
    Depends(get_admin_repository),
]
AdminServiceDep = Annotated[
    AdminService,
    Depends(get_admin_service),
]

KnowledgeRepositoryDep = Annotated[
    KnowledgeRepository,
    Depends(get_knowledge_repository),
]
KnowledgeUploadServiceDep = Annotated[
    KnowledgeUploadService,
    Depends(get_knowledge_upload_service),
]

ChatRepositoryDep = Annotated[
    ChatRepository,
    Depends(get_chat_repository),
]
ChatSessionServiceDep = Annotated[
    ChatSessionService,
    Depends(get_chat_session_service),
]

ChatStreamingAnswerServiceDep = Annotated[
    ChatStreamingAnswerService,
    Depends(get_chat_streaming_answer_service),
]


AgentExecutionPlanServiceDep = Annotated[
    AgentExecutionPlanService,
    Depends(get_agent_execution_plan_service),
]
