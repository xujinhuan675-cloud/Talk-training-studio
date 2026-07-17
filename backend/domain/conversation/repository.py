# input: 领域实体 Conversation, Message, Run, AgentConfig
# output: 4 个 ABC 仓储接口
# owner: unknown
# pos: 领域层 - 对话聚合仓储接口定义；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Repository abstractions for conversation aggregate."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from .entity import AgentConfig, Conversation, Message, Run


class ConversationRepository(ABC):
    """Contract for persisting and querying conversations."""

    @abstractmethod
    async def create(self, conversation: Conversation) -> Conversation: ...

    @abstractmethod
    async def update(self, conversation: Conversation) -> Conversation: ...

    @abstractmethod
    async def get_by_id(self, conversation_id: int) -> Optional[Conversation]: ...

    @abstractmethod
    async def list(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Conversation]: ...

    @abstractmethod
    async def count(self, *, status: Optional[str] = None) -> int: ...


class MessageRepository(ABC):
    """Contract for persisting and querying messages."""

    @abstractmethod
    async def create(self, message: Message) -> Message: ...

    @abstractmethod
    async def update(self, message: Message) -> Message: ...

    @abstractmethod
    async def get_by_id(self, message_id: int) -> Optional[Message]: ...

    @abstractmethod
    async def get_by_public_id(self, public_id: str) -> Optional[Message]: ...

    @abstractmethod
    async def get_latest_by_conversation(
        self,
        conversation_id: int,
        *,
        branch_id: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> Optional[Message]: ...

    @abstractmethod
    async def list_by_conversation(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
        branch_id: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> list[Message]: ...

    @abstractmethod
    async def list_children(
        self,
        parent_message_id: str,
        *,
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> list[Message]: ...

    @abstractmethod
    async def list_path_to_message(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        limit: int = 200,
        include_deleted: bool = False,
        statuses: Optional[Sequence[str]] = None,
    ) -> list[Message]: ...

    @abstractmethod
    async def search_by_content(
        self,
        conversation_id: int,
        query: str,
        *,
        skip: int = 0,
        limit: int = 20,
        branch_id: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        statuses: Optional[Sequence[str]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[Message]: ...

    @abstractmethod
    async def list_context_window(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        before: int = 2,
        after: int = 2,
        branch_id: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[Message]: ...

    @abstractmethod
    async def count_by_conversation(
        self,
        conversation_id: int,
        *,
        branch_id: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> int: ...


class RunRepository(ABC):
    """Contract for persisting and querying runs."""

    @abstractmethod
    async def create(self, run: Run) -> Run: ...

    @abstractmethod
    async def update(self, run: Run) -> Run: ...

    @abstractmethod
    async def get_by_id(self, run_id: int) -> Optional[Run]: ...

    @abstractmethod
    async def list_by_conversation(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        trigger_message_id: Optional[str] = None,
    ) -> list[Run]: ...


class AgentConfigRepository(ABC):
    """Contract for persisting and querying agent configurations."""

    @abstractmethod
    async def create(self, config: AgentConfig) -> AgentConfig: ...

    @abstractmethod
    async def update(self, config: AgentConfig) -> AgentConfig: ...

    @abstractmethod
    async def delete(self, config_id: int) -> None: ...

    @abstractmethod
    async def get_by_id(self, config_id: int) -> Optional[AgentConfig]: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[AgentConfig]: ...

    @abstractmethod
    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> list[AgentConfig]: ...

    @abstractmethod
    async def count(self) -> int: ...
