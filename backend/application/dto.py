"""Application DTOs shared between use cases and API routes."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from shared.codes import BusinessCode


class DTOBase(BaseModel):
    """Base DTO: unify datetime serialization to UTC-Z for all subclasses."""

    @model_serializer(mode="wrap")
    def _serialize_model(self, handler):  # type: ignore[override]
        data = handler(self)

        def convert(value):
            if isinstance(value, datetime):
                ts = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
                s = ts.astimezone(timezone.utc).isoformat()
                return s.replace("+00:00", "Z")
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, tuple):
                return tuple(convert(v) for v in value)
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            return value

        return convert(data)


class PaginationParams(DTOBase):
    """分页参数（页码/每页大小），自动派生 skip/limit。

    注意：默认值在实例化时从应用设置读取，避免在类定义阶段
    导入并实例化全局配置导致的副作用。
    """

    page: int = Field(1, ge=1, description="页码，从1开始")
    size: Optional[int] = Field(
        default=None,
        ge=1,
        description="每页大小（默认取应用配置 DEFAULT_PAGE_SIZE）",
    )

    @model_validator(mode="after")
    def _apply_runtime_defaults(self):  # type: ignore[override]
        # 延迟导入设置，只有在实例化 DTO 时才读取
        try:
            from core.config import settings  # local import to avoid import-time side effects

            default_size = int(getattr(settings, "DEFAULT_PAGE_SIZE", 20))
            max_size = int(getattr(settings, "MAX_PAGE_SIZE", 100))
        except Exception:
            default_size = 20
            max_size = 100
        if self.size is None:
            self.size = default_size
        # 运行时再约束最大页大小
        if self.size > max_size:
            self.size = max_size
        return self

    @property
    def skip(self) -> int:
        return (self.page - 1) * int(self.size or 0)

    @property
    def limit(self) -> int:
        return int(self.size or 0)


class MessageDTO(DTOBase):
    """消息响应DTO"""

    message: str
    code: int = BusinessCode.SUCCESS


class ErrorDTO(DTOBase):
    """错误响应DTO"""

    error: str
    code: int
    detail: Optional[str] = None


class FileAssetDTO(DTOBase):
    """File asset detail DTO."""

    id: int
    owner_id: Optional[int]
    storage_type: str
    bucket: Optional[str]
    region: Optional[str]
    key: str
    size: int
    etag: Optional[str]
    content_type: Optional[str]
    original_filename: Optional[str]
    kind: Optional[str]
    is_public: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    url: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class FileAssetSummaryDTO(DTOBase):
    """Reduced file asset payload for lightweight responses."""

    id: int
    key: str
    status: str
    original_filename: Optional[str]
    content_type: Optional[str]
    etag: Optional[str]
    size: int
    url: Optional[str]


class PresignUploadRequestDTO(DTOBase):
    """Input payload for requesting a presigned upload."""

    filename: str
    mime_type: Optional[str] = Field(default=None, alias="mime_type")
    size_bytes: int = Field(ge=0, alias="size_bytes")
    kind: str = Field(default="uploads")
    method: Literal["PUT", "POST"] = Field(default="PUT")
    expires_in: int = Field(default=600, ge=60, le=3600)


class CompleteUploadRequestDTO(DTOBase):
    """Payload for confirming a presigned upload."""

    id: Optional[int] = None
    key: Optional[str] = None

    @field_validator("id", "key")
    def _strip_empty(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("key")
    def _normalize_key(cls, value):
        if value:
            return value.lstrip("/")
        return value

    def ensure_identifier(self) -> None:
        if self.id is None and not self.key:
            raise ValueError("id 或 key 必须提供一个")


class FileAccessURLRequestDTO(DTOBase):
    """Payload for generating access URLs."""

    expires_in: int = Field(default=600, ge=60, le=3600)
    filename: Optional[str] = None


class PresignUploadDetailDTO(DTOBase):
    """Presigned request information returned to clients."""

    url: str
    method: str
    headers: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, str] = Field(default_factory=dict)
    expires_in: int


class PresignUploadResponseDTO(DTOBase):
    """Response payload for presigned upload preparation."""

    file: FileAssetSummaryDTO
    upload: PresignUploadDetailDTO


class StorageUploadResponseDTO(DTOBase):
    """Response payload after direct upload completes via API relay."""

    key: str
    etag: Optional[str]
    size: int
    content_type: Optional[str]
    url: Optional[str]
    file_id: int
    file_status: str


# ── Agent / Conversation DTOs ────────────────────────────────────────


class CreateConversationDTO(DTOBase):
    """Input for creating a new conversation."""

    title: str = Field(max_length=255)
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateConversationDTO(DTOBase):
    """Input for updating a conversation."""

    title: Optional[str] = Field(default=None, max_length=255)
    system_prompt: Optional[str] = None
    model: Optional[str] = None


class ConversationDTO(DTOBase):
    """Conversation detail DTO."""

    id: int
    title: str
    system_prompt: Optional[str]
    model: Optional[str]
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MessageDTO_Agent(DTOBase):
    """Message DTO for conversation history."""

    id: int
    conversation_id: int
    role: str
    content: str
    public_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    branch_id: Optional[str] = None
    status: str = "active"
    finish_reason: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    content_parts: list[dict[str, Any]] = Field(default_factory=list)
    run_id: Optional[int] = None
    token_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageLocationDTO(DTOBase):
    """Message location data for branch navigation."""

    message: MessageDTO_Agent
    path: list[MessageDTO_Agent] = Field(default_factory=list)
    context: list[MessageDTO_Agent] = Field(default_factory=list)


class MessageSearchResultDTO(DTOBase):
    """A message search hit with enough context to jump to its branch."""

    message: MessageDTO_Agent
    path: list[MessageDTO_Agent] = Field(default_factory=list)
    context: list[MessageDTO_Agent] = Field(default_factory=list)


class ForkConversationDTO(DTOBase):
    """Input for copying a message tree into a new conversation."""

    title: Optional[str] = Field(default=None, max_length=255)
    option: Literal["directPath", "includeBranches", "targetLevel"] = "targetLevel"
    include_deleted: bool = False
    statuses: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ForkConversationResultDTO(DTOBase):
    """Result of forking a conversation message tree."""

    conversation: ConversationDTO
    messages: list[MessageDTO_Agent] = Field(default_factory=list)
    source_to_forked_id: dict[str, str] = Field(default_factory=dict)


class EditMessageDTO(DTOBase):
    """Input for creating an edited message branch."""

    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryMessageDTO(DTOBase):
    """Input for creating a retry branch from an existing message."""

    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunDTO(DTOBase):
    """Run tracking DTO."""

    id: int
    conversation_id: int
    public_id: Optional[str] = None
    status: str
    provider: Optional[str] = None
    model: Optional[str]
    finish_reason: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    trigger_message_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    branch_id: Optional[str] = None
    provider_endpoint: Optional[str] = None
    provider_wire_api: Optional[str] = None
    provider_max_retries: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _derive_run_metadata_fields(self):  # type: ignore[override]
        metadata = self.metadata or {}
        self.trigger_message_id = self.trigger_message_id or _metadata_text(
            metadata, "trigger_message_id"
        )
        self.parent_message_id = self.parent_message_id or _metadata_text(
            metadata, "parent_message_id"
        )
        self.branch_id = self.branch_id or _metadata_text(metadata, "branch_id")
        provider_metadata = metadata.get("provider_metadata")
        if isinstance(provider_metadata, dict):
            self.provider_endpoint = self.provider_endpoint or _metadata_text(
                provider_metadata, "endpoint"
            )
            self.provider_wire_api = self.provider_wire_api or _metadata_text(
                provider_metadata, "wire_api"
            )
            retries = provider_metadata.get("max_retries")
            if self.provider_max_retries is None and isinstance(retries, int):
                self.provider_max_retries = retries
        return self


class ChatRequestDTO(DTOBase):
    """Input for sending a chat message."""

    message: str = Field(min_length=1)
    parent_message_id: Optional[str] = None
    branch_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    history_limit: int = Field(default=200, ge=1, le=200)
    stream: bool = True


def _metadata_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


class CreateAgentConfigDTO(DTOBase):
    """Input for creating an agent configuration."""

    name: str = Field(max_length=100)
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateAgentConfigDTO(DTOBase):
    """Input for updating an agent configuration."""

    name: Optional[str] = Field(default=None, max_length=100)
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    metadata: Optional[dict[str, Any]] = None


class AgentConfigDTO(DTOBase):
    """Agent configuration DTO."""

    id: int
    name: str
    system_prompt: Optional[str]
    model: Optional[str]
    temperature: Optional[float]
    max_tokens: Optional[int]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
