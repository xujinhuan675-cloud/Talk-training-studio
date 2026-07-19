# input: 无外部依赖，纯业务逻辑
# output: Conversation, Message, Run, AgentConfig 领域实体
# owner: unknown
# pos: 领域层 - 对话聚合根及关联实体定义；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Domain entities for the conversation aggregate."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from domain.common.exceptions import DomainValidationException

_CONVERSATION_STATUSES = {"active", "archived"}
_MESSAGE_ROLES = {"system", "user", "assistant"}
_MESSAGE_STATUSES = {"active", "superseded", "deleted", "failed"}
_RUN_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def normalize_agent_resource_ids(values: Sequence[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


@dataclass
class Conversation:
    """Aggregate root for a chat conversation."""

    id: Optional[int]
    title: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.status = self.status or "active"
        if self.status not in _CONVERSATION_STATUSES:
            raise DomainValidationException(
                f"Invalid conversation status: {self.status}",
                field="status",
                details={"allowed": sorted(_CONVERSATION_STATUSES)},
            )
        self.created_at = _ensure_utc(self.created_at)
        self.updated_at = _ensure_utc(self.updated_at)
        self.deleted_at = _ensure_utc(self.deleted_at)
        if self.metadata is None:
            self.metadata = {}

    def _touch(self) -> None:
        now = _utcnow()
        self.updated_at = now
        if self.created_at is None:
            self.created_at = now

    def update_title(self, title: str) -> None:
        self.title = title
        self._touch()

    def archive(self) -> None:
        self.status = "archived"
        self._touch()

    def soft_delete(self) -> None:
        self.status = "archived"
        self.deleted_at = _utcnow()
        self._touch()

    def is_active(self) -> bool:
        return self.status == "active" and self.deleted_at is None


@dataclass
class Message:
    """A single message within a conversation."""

    id: Optional[int]
    conversation_id: int
    role: str  # system | user | assistant
    content: str
    public_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    branch_id: Optional[str] = None
    status: str = "active"
    finish_reason: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    content_parts: list[dict[str, Any]] = field(default_factory=list)
    run_id: Optional[int] = None
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.public_id:
            self.public_id = _new_public_id("msg")
        if not self.branch_id:
            self.branch_id = "main"
        self.status = self.status or "active"
        if self.role not in _MESSAGE_ROLES:
            raise DomainValidationException(
                f"Invalid message role: {self.role}",
                field="role",
                details={"allowed": sorted(_MESSAGE_ROLES)},
            )
        if self.status not in _MESSAGE_STATUSES:
            raise DomainValidationException(
                f"Invalid message status: {self.status}",
                field="status",
                details={"allowed": sorted(_MESSAGE_STATUSES)},
            )
        self.created_at = _ensure_utc(self.created_at)
        if self.content_parts is None:
            self.content_parts = []
        if self.metadata is None:
            self.metadata = {}

    def is_child_of(self, message: "Message") -> bool:
        return self.parent_message_id == message.public_id

    def create_child(
        self,
        *,
        role: str,
        content: str,
        run_id: Optional[int] = None,
        token_count: int = 0,
        finish_reason: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        content_parts: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "Message":
        return Message(
            id=None,
            conversation_id=self.conversation_id,
            role=role,
            content=content,
            public_id=None,
            parent_message_id=self.public_id,
            branch_id=self.branch_id,
            status="active",
            finish_reason=finish_reason,
            provider=provider,
            model=model,
            content_parts=content_parts or [],
            run_id=run_id,
            token_count=token_count,
            metadata=metadata or {},
            created_at=_utcnow(),
        )

    def create_edit(self, *, content: str, metadata: Optional[dict[str, Any]] = None) -> "Message":
        return Message(
            id=None,
            conversation_id=self.conversation_id,
            role=self.role,
            content=content,
            public_id=None,
            parent_message_id=self.parent_message_id,
            branch_id=_new_public_id("branch"),
            status="active",
            provider=self.provider,
            model=self.model,
            content_parts=[],
            metadata={"edit_of": self.public_id, **(metadata or {})},
            created_at=_utcnow(),
        )

    def create_retry(
        self,
        *,
        content: str = "",
        run_id: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "Message":
        return Message(
            id=None,
            conversation_id=self.conversation_id,
            role=self.role,
            content=content,
            public_id=None,
            parent_message_id=self.parent_message_id,
            branch_id=_new_public_id("branch"),
            status="active",
            provider=self.provider,
            model=self.model,
            run_id=run_id,
            metadata={"retry_of": self.public_id, **(metadata or {})},
            created_at=_utcnow(),
        )

    def mark_superseded(self) -> None:
        self.status = "superseded"


@dataclass
class Run:
    """Tracks a single LLM invocation within a conversation.

    Phase 1 state machine: running → completed | failed
    """

    id: Optional[int]
    conversation_id: int
    public_id: Optional[str] = None
    status: str = "running"
    provider: Optional[str] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.public_id:
            self.public_id = _new_public_id("run")
        if self.status not in _RUN_STATUSES:
            raise DomainValidationException(
                f"Invalid run status: {self.status}",
                field="status",
                details={"allowed": sorted(_RUN_STATUSES)},
            )
        if self.metadata is None:
            self.metadata = {}
        self.started_at = _ensure_utc(self.started_at) or _utcnow()
        self.completed_at = _ensure_utc(self.completed_at)
        self.created_at = _ensure_utc(self.created_at)

    def mark_completed(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        finish_reason: Optional[str] = None,
    ) -> None:
        self.status = "completed"
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.finish_reason = finish_reason
        self.completed_at = _utcnow()

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.error_message = error
        self.completed_at = _utcnow()


@dataclass
class AgentConfig:
    """Standalone aggregate for reusable agent configurations."""

    id: Optional[int]
    name: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tool_ids: tuple[str, ...] = field(default_factory=tuple)
    mcp_server_ids: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise DomainValidationException(
                "Agent config name is required",
                field="name",
            )
        self.created_at = _ensure_utc(self.created_at)
        self.updated_at = _ensure_utc(self.updated_at)
        self.tool_ids = normalize_agent_resource_ids(self.tool_ids)
        self.mcp_server_ids = normalize_agent_resource_ids(self.mcp_server_ids)
        if self.metadata is None:
            self.metadata = {}

    def _touch(self) -> None:
        now = _utcnow()
        self.updated_at = now
        if self.created_at is None:
            self.created_at = now
