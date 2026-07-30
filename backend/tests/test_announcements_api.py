from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes import announcements as announcement_routes
from core.exceptions import register_exception_handlers
from infrastructure.external import newapi_announcements
from infrastructure.external.newapi_announcements import (
    AnnouncementItem,
    AnnouncementSnapshot,
    NewAPIAnnouncementsUnavailableError,
)


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: object):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses: dict[str, _FakeResponse], calls: list[dict[str, object]], **kwargs):
        self._responses = responses
        self._calls = calls
        self._kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url: str, *, headers: dict[str, str]):
        self._calls.append({"url": url, "headers": headers, "kwargs": self._kwargs})
        return self._responses[url]


@pytest.mark.asyncio
async def test_public_announcement_adapter_normalizes_and_caches_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newapi_announcements.reset_newapi_announcements_cache()
    calls: list[dict[str, object]] = []
    responses = {
        "https://control.example/api/notice": _FakeResponse(
            status_code=200,
            payload={"success": True, "data": " 训练服务更新 "},
        ),
        "https://control.example/api/status": _FakeResponse(
            status_code=200,
            payload={
                "success": True,
                "data": {
                    "announcements_enabled": True,
                    "announcements": [
                        {
                            "id": 7,
                            "content": "新训练模板已发布",
                            "extra": "适用于销售沟通",
                            "publishDate": "2026-07-29T09:00:00Z",
                            "type": "success",
                        },
                        {"content": "   ", "type": "warning"},
                    ],
                },
            },
        ),
    }

    monkeypatch.setattr(
        newapi_announcements.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls, **kwargs),
    )

    first = await newapi_announcements.fetch_newapi_announcements(
        base_url="https://control.example/",
        timeout_seconds=2,
        cache_ttl_seconds=30,
        max_items=20,
    )
    second = await newapi_announcements.fetch_newapi_announcements(
        base_url="https://control.example/",
        timeout_seconds=2,
        cache_ttl_seconds=30,
        max_items=20,
    )

    assert first == second
    assert first.notice == "训练服务更新"
    assert first.announcements == [
        AnnouncementItem(
            id="7",
            content="新训练模板已发布",
            extra="适用于销售沟通",
            published_at="2026-07-29T09:00:00Z",
            type="success",
        )
    ]
    assert len(calls) == 2
    assert all(call["headers"] == {"Accept": "application/json"} for call in calls)
    assert all("Authorization" not in call["headers"] for call in calls)
    assert all(call["kwargs"]["follow_redirects"] is False for call in calls)
    assert all(call["kwargs"]["trust_env"] is False for call in calls)


@pytest.mark.asyncio
async def test_public_announcement_adapter_hides_upstream_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newapi_announcements.reset_newapi_announcements_cache()
    calls: list[dict[str, object]] = []
    responses = {
        "https://control.example/api/notice": _FakeResponse(
            status_code=500,
            payload={"detail": "private upstream configuration"},
        ),
        "https://control.example/api/status": _FakeResponse(
            status_code=200,
            payload={"success": True, "data": {}},
        ),
    }
    monkeypatch.setattr(
        newapi_announcements.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls, **kwargs),
    )

    with pytest.raises(NewAPIAnnouncementsUnavailableError) as exc_info:
        await newapi_announcements.fetch_newapi_announcements(
            base_url="https://control.example",
            timeout_seconds=2,
            cache_ttl_seconds=30,
            max_items=20,
        )

    assert str(exc_info.value) == "Announcement service unavailable"
    assert "private" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_announcement_route_returns_structured_unavailable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(**_kwargs):
        raise NewAPIAnnouncementsUnavailableError("private upstream configuration")

    monkeypatch.setattr(announcement_routes, "fetch_newapi_announcements", unavailable)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(announcement_routes.router, prefix="/api/v1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/announcements")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] == {
        "state": "unavailable",
        "notice": None,
        "announcements": [],
    }
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_announcement_route_returns_normalized_read_only_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def available(**_kwargs):
        return AnnouncementSnapshot(
            notice="服务提醒",
            announcements=[
                AnnouncementItem(
                    id="a-1",
                    content="训练日程调整",
                    extra="请查看最新安排",
                    published_at="2026-07-29T09:00:00Z",
                    type="warning",
                )
            ],
        )

    monkeypatch.setattr(announcement_routes, "fetch_newapi_announcements", available)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(announcement_routes.router, prefix="/api/v1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/announcements")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state"] == "available"
    assert data["notice"] == "服务提醒"
    assert data["announcements"][0] == {
        "id": "a-1",
        "content": "训练日程调整",
        "extra": "请查看最新安排",
        "published_at": "2026-07-29T09:00:00Z",
        "type": "warning",
    }
