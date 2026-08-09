from __future__ import annotations

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.deps import (
    CurrentUser,
    KnowledgeRepositoryDep,
    KnowledgeUploadServiceDep,
)
from app.repositories.knowledge_repository import (
    KnowledgeRepositoryError,
)
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseDeleteResponse,
    KnowledgeBaseListResponse,
    KnowledgeBasePublic,
    KnowledgeBaseUpdate,
    KnowledgeDocumentDeleteResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentPublic,
    KnowledgeDocumentUploadResponse,
)
from app.services.knowledge.knowledge_upload_service import (
    DuplicateKnowledgeDocumentError,
    KnowledgeUploadError,
)

router = APIRouter(
    prefix="/knowledge",
    tags=["知识库"],
)


def _knowledge_base_public(
    repository,
    knowledge_base,
) -> KnowledgeBasePublic:
    return KnowledgeBasePublic(
        id=knowledge_base.id,
        name=knowledge_base.name,
        description=knowledge_base.description,
        routing_description=knowledge_base.routing_description,
        is_active=knowledge_base.is_active,
        created_by=knowledge_base.created_by,
        document_count=repository.count_documents(
            knowledge_base_id=knowledge_base.id
        ),
        created_at=knowledge_base.created_at,
        updated_at=knowledge_base.updated_at,
    )


@router.get(
    "/bases",
    response_model=KnowledgeBaseListResponse,
    summary="获取知识库列表",
)
def list_knowledge_bases(
    current_user: CurrentUser,
    repository: KnowledgeRepositoryDep,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> KnowledgeBaseListResponse:
    del current_user

    try:
        knowledge_bases = repository.list_knowledge_bases(
            limit=limit,
            offset=offset,
        )
        total = repository.count_knowledge_bases()

        items = [
            KnowledgeBasePublic(
                id=item.id,
                name=item.name,
                description=item.description,
                routing_description=item.routing_description,
                is_active=item.is_active,
                created_by=item.created_by,
                document_count=repository.count_documents(
                    knowledge_base_id=item.id
                ),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in knowledge_bases
        ]
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc

    return KnowledgeBaseListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/bases",
    response_model=KnowledgeBasePublic,
    status_code=status.HTTP_201_CREATED,
    summary="创建知识库",
)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    current_user: CurrentUser,
    repository: KnowledgeRepositoryDep,
) -> KnowledgeBasePublic:
    try:
        knowledge_base = repository.create_knowledge_base(
            name=payload.name,
            description=payload.description,
            routing_description=payload.routing_description,
            created_by=current_user.id,
        )
    except IntegrityError as exc:
        repository.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已存在同名知识库",
        ) from exc
    except SQLAlchemyError as exc:
        repository.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc

    return KnowledgeBasePublic(
        id=knowledge_base.id,
        name=knowledge_base.name,
        description=knowledge_base.description,
        routing_description=knowledge_base.routing_description,
        is_active=knowledge_base.is_active,
        created_by=knowledge_base.created_by,
        document_count=0,
        created_at=knowledge_base.created_at,
        updated_at=knowledge_base.updated_at,
    )




@router.patch(
    "/bases/{knowledge_base_id}",
    response_model=KnowledgeBasePublic,
    summary="编辑知识库或启用/停用知识库",
)
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    current_user: CurrentUser,
    repository: KnowledgeRepositoryDep,
) -> KnowledgeBasePublic:
    del current_user

    if knowledge_base_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="knowledge_base_id 必须大于 0",
        )

    fields = set(payload.model_fields_set)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="至少提供一个需要修改的字段",
        )

    if "name" in fields and payload.name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="知识库名称不能为 null",
        )
    if "is_active" in fields and payload.is_active is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="is_active 不能为 null",
        )

    values = payload.model_dump(
        exclude_unset=True,
    )

    try:
        knowledge_base = repository.get_base_for_management(
            knowledge_base_id
        )
        updated = repository.update_knowledge_base(
            knowledge_base,
            values=values,
        )
        return _knowledge_base_public(repository, updated)
    except KnowledgeRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        repository.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已存在同名知识库",
        ) from exc
    except SQLAlchemyError as exc:
        repository.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc


@router.delete(
    "/bases/{knowledge_base_id}",
    response_model=KnowledgeBaseDeleteResponse,
    summary="删除知识库并清理文档、向量和上传文件",
)
def delete_knowledge_base(
    knowledge_base_id: int,
    current_user: CurrentUser,
    service: KnowledgeUploadServiceDep,
) -> KnowledgeBaseDeleteResponse:
    del current_user

    if knowledge_base_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="knowledge_base_id 必须大于 0",
        )

    try:
        result = service.delete_knowledge_base(
            knowledge_base_id
        )
        return KnowledgeBaseDeleteResponse(
            knowledge_base_id=result.knowledge_base_id,
            document_count=result.document_count,
            chunk_count=result.chunk_count,
            vector_count=result.vector_count,
            disk_files_removed=result.disk_files_removed,
            disk_cleanup_failures=list(
                result.disk_cleanup_failures
            ),
        )
    except KnowledgeRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except KnowledgeUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc


@router.post(
    "/documents",
    response_model=KnowledgeDocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传并向量化知识库文档",
)
def upload_document(
    current_user: CurrentUser,
    service: KnowledgeUploadServiceDep,
    file: UploadFile = File(
        ...,
        description="支持 .txt / .md / .pdf，最大大小由服务端配置决定",
    ),
    knowledge_base_id: int = Form(
        ...,
        gt=0,
        description="目标知识库 ID",
    ),
    priority: int = Form(
        0,
        ge=0,
        description="Chunk 业务优先级，默认 0",
    ),
) -> KnowledgeDocumentUploadResponse:
    """
    上传文件后同步完成：

    文件落盘 → SHA256 去重 → 文档解析 → Chunk →
    Ollama Embedding → Chroma → MySQL → ready。
    """
    original_name = file.filename or ""

    try:
        result = service.upload(
            file.file,
            original_name=original_name,
            knowledge_base_id=knowledge_base_id,
            uploaded_by=current_user.id,
            priority=priority,
        )

        document = service.repository.get_document_for_delete(
            result.ingestion.document_id
        )

        return KnowledgeDocumentUploadResponse(
            document=KnowledgeDocumentPublic.model_validate(
                document
            ),
            embedding_dimension=(
                result.ingestion.embedding_dimension
            ),
            sha256=result.sha256,
        )
    except DuplicateKnowledgeDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "existing_document_id": (
                    exc.existing_document_id
                ),
            },
        ) from exc
    except KnowledgeRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except KnowledgeUploadError as exc:
        message = str(exc)
        if "超过" in message and "MB" in message:
            http_status = status.HTTP_413_CONTENT_TOO_LARGE
        elif (
            "不支持的文档类型" in message
            or "不能为空" in message
            or "文件名" in message
        ):
            http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

        raise HTTPException(
            status_code=http_status,
            detail=message,
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc
    finally:
        file.file.close()


@router.get(
    "/documents",
    response_model=KnowledgeDocumentListResponse,
    summary="获取知识库文档列表",
)
def list_documents(
    current_user: CurrentUser,
    repository: KnowledgeRepositoryDep,
    knowledge_base_id: int | None = Query(
        default=None,
        gt=0,
        description="可选：只查看指定知识库",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
) -> KnowledgeDocumentListResponse:
    del current_user

    try:
        documents = repository.list_documents(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
        )
        total = repository.count_documents(
            knowledge_base_id=knowledge_base_id
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc

    return KnowledgeDocumentListResponse(
        items=[
            KnowledgeDocumentPublic.model_validate(document)
            for document in documents
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentDeleteResponse,
    summary="删除知识库文档及对应向量",
)
def delete_document(
    document_id: int,
    current_user: CurrentUser,
    service: KnowledgeUploadServiceDep,
) -> KnowledgeDocumentDeleteResponse:
    del current_user

    if document_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="document_id 必须大于 0",
        )

    try:
        result = service.delete_document(document_id)
        return KnowledgeDocumentDeleteResponse(
            document_id=result.document_id,
            disk_file_removed=result.disk_file_removed,
        )
    except KnowledgeRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except KnowledgeUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        ) from exc
