from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4000)
    routing_description: str | None = Field(
        default=None,
        max_length=4000,
    )

    @field_validator(
        "name",
        "description",
        "routing_description",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value:
            raise ValueError("知识库名称不能为空")
        return value

    @field_validator(
        "description",
        "routing_description",
    )
    @classmethod
    def empty_optional_text_to_none(
        cls,
        value: str | None,
    ) -> str | None:
        return value or None


class KnowledgeBasePublic(BaseModel):
    """知识库前端展示模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    routing_description: str | None
    is_active: bool
    created_by: int | None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(BaseModel):
    """知识库分页列表。"""

    items: list[KnowledgeBasePublic]
    total: int
    limit: int
    offset: int




class KnowledgeBaseUpdate(BaseModel):
    """部分更新知识库。仅允许修改业务可编辑字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4000)
    routing_description: str | None = Field(default=None, max_length=4000)
    is_active: bool | None = None

    @field_validator(
        "name",
        "description",
        "routing_description",
        mode="before",
    )
    @classmethod
    def strip_update_text(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("name")
    @classmethod
    def validate_update_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and not value:
            raise ValueError("知识库名称不能为空")
        return value

    @field_validator(
        "description",
        "routing_description",
    )
    @classmethod
    def normalize_update_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        return value or None


class KnowledgeBaseDeleteResponse(BaseModel):
    """知识库级联删除结果。"""

    knowledge_base_id: int
    deleted: bool = True
    document_count: int
    chunk_count: int
    vector_count: int
    disk_files_removed: bool
    disk_cleanup_failures: list[str] = Field(default_factory=list)


class KnowledgeDocumentPublic(BaseModel):
    """知识库文档前端展示模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    original_name: str
    file_extension: str
    mime_type: str | None
    file_size_bytes: int
    status: str
    error_message: str | None
    chunk_count: int
    content_version: int
    uploaded_by: int | None
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentUploadResponse(BaseModel):
    """上传成功响应。"""

    document: KnowledgeDocumentPublic
    embedding_dimension: int
    sha256: str


class KnowledgeDocumentListResponse(BaseModel):
    """知识库文档分页列表。"""

    items: list[KnowledgeDocumentPublic]
    total: int
    limit: int
    offset: int


class KnowledgeDocumentDeleteResponse(BaseModel):
    """知识库文档删除结果。"""

    document_id: int
    deleted: bool = True
    vector_data_deleted: bool = True
    disk_file_removed: bool


class KnowledgeUploadFormDocumentation(BaseModel):
    """
    仅用于 OpenAPI 文档说明，不作为 multipart 请求体直接解析。
    """

    knowledge_base_id: int = Field(gt=0)
    priority: int = Field(default=0, ge=0)
