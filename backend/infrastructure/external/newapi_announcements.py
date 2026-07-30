"""Read-only announcement adapter for the NewAPI public status endpoints.

The response shape follows ``outside-project/new-api-main/controller/misc.go``.
It deliberately uses neither gateway tokens nor dashboard client credentials.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


class NewAPIAnnouncementsUnavailableError(Exception):
    """Raised when the public announcement endpoints cannot be used safely."""


@dataclass(frozen=True)
class AnnouncementItem:
    id: str
    content: str
    extra: str | None = None
    published_at: str | None = None
    type: str = "default"


@dataclass(frozen=True)
class AnnouncementSnapshot:
    notice: str | None
    announcements: list[AnnouncementItem]


@dataclass(frozen=True)
class _CacheEntry:
    base_url: str
    expires_at: float
    snapshot: AnnouncementSnapshot


_cache_entry: _CacheEntry | None = None
_cache_lock = asyncio.Lock()
_MAX_NOTICE_LENGTH = 8_000
_MAX_CONTENT_LENGTH = 2_000
_MAX_EXTRA_LENGTH = 500
_ALLOWED_TYPES = {"default", "ongoing", "success", "warning", "error"}


def _optional_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:limit] or None


def _announcement_id(item: Mapping[str, Any]) -> str:
    raw_id = item.get("id")
    item_id = _optional_text(raw_id, limit=80)
    if item_id is None and isinstance(raw_id, (int, float)) and not isinstance(raw_id, bool):
        item_id = str(raw_id)[:80]
    if item_id:
        return item_id
    fingerprint = "\x1f".join(
        (
            _optional_text(item.get("content"), limit=_MAX_CONTENT_LENGTH) or "",
            _optional_text(item.get("extra"), limit=_MAX_EXTRA_LENGTH) or "",
            _optional_text(item.get("publishDate"), limit=120) or "",
            _optional_text(item.get("type"), limit=24) or "",
        )
    )
    return f"hash:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:20]}"


def _normalize_announcements(status_payload: Mapping[str, Any], *, max_items: int) -> list[AnnouncementItem]:
    data = status_payload.get("data")
    if not isinstance(data, Mapping):
        raise NewAPIAnnouncementsUnavailableError("Announcement service unavailable")
    if data.get("announcements_enabled") is not True:
        return []

    raw_items = data.get("announcements")
    if not isinstance(raw_items, list):
        return []

    normalized: list[AnnouncementItem] = []
    for raw_item in raw_items:
        if len(normalized) >= max_items:
            break
        if not isinstance(raw_item, Mapping):
            continue
        content = _optional_text(raw_item.get("content"), limit=_MAX_CONTENT_LENGTH)
        if not content:
            continue
        item_type = _optional_text(raw_item.get("type"), limit=24) or "default"
        normalized.append(
            AnnouncementItem(
                id=_announcement_id(raw_item),
                content=content,
                extra=_optional_text(raw_item.get("extra"), limit=_MAX_EXTRA_LENGTH),
                published_at=_optional_text(raw_item.get("publishDate"), limit=120),
                type=item_type if item_type in _ALLOWED_TYPES else "default",
            )
        )
    return normalized


def _notice_from_payload(notice_payload: Mapping[str, Any]) -> str | None:
    return _optional_text(notice_payload.get("data"), limit=_MAX_NOTICE_LENGTH)


def _validate_public_payload(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("success") is not True:
        raise NewAPIAnnouncementsUnavailableError("Announcement service unavailable")
    return payload


async def _fetch_snapshot(*, base_url: str, timeout_seconds: float, max_items: int) -> AnnouncementSnapshot:
    base = base_url.rstrip("/")
    if not base:
        raise NewAPIAnnouncementsUnavailableError("Announcement service unavailable")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            notice_response, status_response = await asyncio.gather(
                client.get(f"{base}/api/notice", headers={"Accept": "application/json"}),
                client.get(f"{base}/api/status", headers={"Accept": "application/json"}),
            )
    except httpx.HTTPError as exc:
        raise NewAPIAnnouncementsUnavailableError("Announcement service unavailable") from exc

    if notice_response.status_code >= 400 or status_response.status_code >= 400:
        raise NewAPIAnnouncementsUnavailableError("Announcement service unavailable")

    try:
        notice_payload = _validate_public_payload(notice_response.json())
        status_payload = _validate_public_payload(status_response.json())
    except (ValueError, TypeError) as exc:
        raise NewAPIAnnouncementsUnavailableError("Announcement service unavailable") from exc

    return AnnouncementSnapshot(
        notice=_notice_from_payload(notice_payload),
        announcements=_normalize_announcements(status_payload, max_items=max_items),
    )


async def fetch_newapi_announcements(
    *,
    base_url: str,
    timeout_seconds: float,
    cache_ttl_seconds: int,
    max_items: int,
) -> AnnouncementSnapshot:
    """Fetch a single bounded public announcement snapshot with a short TTL."""

    global _cache_entry
    normalized_base_url = base_url.rstrip("/")
    now = time.monotonic()
    cached = _cache_entry
    if cached and cached.base_url == normalized_base_url and cached.expires_at > now:
        return cached.snapshot

    async with _cache_lock:
        now = time.monotonic()
        cached = _cache_entry
        if cached and cached.base_url == normalized_base_url and cached.expires_at > now:
            return cached.snapshot

        snapshot = await _fetch_snapshot(
            base_url=normalized_base_url,
            timeout_seconds=max(0.1, timeout_seconds),
            max_items=max(1, max_items),
        )
        _cache_entry = _CacheEntry(
            base_url=normalized_base_url,
            expires_at=now + max(1, cache_ttl_seconds),
            snapshot=snapshot,
        )
        return snapshot


def reset_newapi_announcements_cache() -> None:
    """Clear the process-local snapshot for tests and controlled reloads."""

    global _cache_entry
    _cache_entry = None
