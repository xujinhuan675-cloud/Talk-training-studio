"""Repository abstraction for file assets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from domain.conversation.repository import OwnedMetadataScope

from .entity import FileAsset


class FileAssetRepository(ABC):
    """Contract for persisting and querying file assets.

    Application-service callers must pass ``metadata_scope`` explicitly for
    read/write access. Repository-level unscoped helpers must be narrow and
    named for their purpose rather than hidden behind ``metadata_scope=None``.
    """

    @abstractmethod
    async def create(self, asset: FileAsset) -> FileAsset: ...

    @abstractmethod
    async def update(
        self,
        asset: FileAsset,
        *,
        metadata_scope: OwnedMetadataScope | None,
    ) -> FileAsset: ...

    @abstractmethod
    async def delete(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None,
    ) -> None: ...

    @abstractmethod
    async def delete_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope | None,
    ) -> None: ...

    @abstractmethod
    async def get_by_id(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None,
    ) -> Optional[FileAsset]: ...

    @abstractmethod
    async def get_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope | None,
    ) -> Optional[FileAsset]: ...

    @abstractmethod
    async def key_exists_outside_metadata_scope(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> bool: ...

    @abstractmethod
    async def list(
        self,
        *,
        owner_id: Optional[int] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        metadata_scope: OwnedMetadataScope | None,
    ) -> list[FileAsset]: ...

    @abstractmethod
    async def count(
        self,
        *,
        owner_id: Optional[int] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        metadata_scope: OwnedMetadataScope | None,
    ) -> int: ...
