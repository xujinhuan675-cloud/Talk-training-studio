# input: DefenseSession 领域实体
# output: DefenseSessionRepository ABC 仓储接口
# owner: wanhua.gu
# pos: 领域层 - 答辩准备会话仓储接口；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Repository abstraction for defense prep sessions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .entity import DefenseSession


@dataclass(frozen=True)
class DefenseSessionAccessScope:
    """Server-side visibility boundary for defense prep sessions."""

    user_id: str | None = None
    team_id: str | None = None
    include_team_scope: bool = False
    unrestricted: bool = False


def defense_session_matches_access_scope(
    session: DefenseSession,
    access_scope: DefenseSessionAccessScope | None,
) -> bool:
    """Unowned legacy sessions are invisible outside an explicit admin scope."""

    if access_scope is None or access_scope.unrestricted:
        return True
    owner_user_id = (session.owner_user_id or "").strip()
    owner_team_id = (session.owner_team_id or "").strip()
    if not owner_user_id and not owner_team_id:
        return False
    if owner_user_id and owner_user_id == (access_scope.user_id or "").strip():
        return True
    return bool(
        access_scope.include_team_scope
        and owner_team_id
        and owner_team_id == (access_scope.team_id or "").strip()
    )


class DefenseSessionRepository(ABC):
    @abstractmethod
    async def create(self, session: DefenseSession) -> DefenseSession: ...

    @abstractmethod
    async def get_by_id(
        self,
        session_id: int,
        *,
        access_scope: DefenseSessionAccessScope | None = None,
    ) -> Optional[DefenseSession]: ...

    @abstractmethod
    async def update(self, session: DefenseSession) -> DefenseSession: ...

    @abstractmethod
    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        access_scope: DefenseSessionAccessScope | None = None,
    ) -> list[DefenseSession]: ...

    @abstractmethod
    async def delete(
        self,
        session_id: int,
        *,
        access_scope: DefenseSessionAccessScope | None = None,
    ) -> bool: ...
