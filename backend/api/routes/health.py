"""Health check endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status as http_status

from application.services.training_studio.voice_health_service import build_voice_health_report
from core.config import settings
from core.observability.health import full_health_check
from infrastructure.external.pipecat.realtime_pipeline import get_pipecat_capability

router = APIRouter(tags=["Health"])


def _require_health_access(request: Request, *, require_configured_token: bool = False) -> None:
    token = settings.health.access_token
    if require_configured_token and not token:
        raise HTTPException(status_code=503, detail="Health access token is not configured")
    if not token:
        return
    header = request.headers.get("Authorization") or request.headers.get("X-Access-Token")
    if header and header.lower().startswith("bearer "):
        header = header[7:]
    if header != token:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/health/live")
async def health_live():
    return {"status": "alive"}


@router.get("/health/ready")
async def health_ready(request: Request):
    _require_health_access(request)
    report = await full_health_check()
    payload = (
        report.to_dict() if settings.health.include_details else {"status": report.status.value}
    )
    status_code = (
        http_status.HTTP_200_OK if report.is_ready else http_status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/health/voice/ready")
async def health_voice_ready(request: Request):
    """Report configured voice-route and local-runtime readiness for monitoring."""

    _require_health_access(request, require_configured_token=True)
    report = await asyncio.to_thread(
        build_voice_health_report,
        pipecat_capability_loader=get_pipecat_capability,
    )
    status_code = (
        http_status.HTTP_200_OK
        if report.get("ready") is True
        else http_status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(
        status_code=status_code,
        content=report,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/health")
async def health_legacy():
    return {"status": "alive"}
