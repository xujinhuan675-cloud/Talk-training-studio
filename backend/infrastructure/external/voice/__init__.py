# input: NewAPI user relay settings and OpenAI-compatible voice clients
# output: gateway-only TTS/STT client lifecycle
# owner: TalkWise platform integration
# pos: infrastructure - voice protocol client lifecycle
"""Gateway-only voice client lifecycle management."""

from __future__ import annotations

from typing import Optional

from application.ports.stt import STTPort
from application.ports.tts import TTSPort
from core.config import settings
from core.logging_config import get_logger
from infrastructure.external.newapi_user_gateway import (
    runtime_api_key,
    user_billing_enabled,
    user_relay_base_url,
)

logger = get_logger(__name__)

_tts_client: Optional[TTSPort] = None
_stt_client: Optional[STTPort] = None


async def init_tts_client() -> None:
    """Initialize the OpenAI-compatible TTS client for NewAPI user billing."""
    global _tts_client

    if _tts_client is not None:
        logger.warning("TTS client already initialized")
        return
    if not user_billing_enabled():
        logger.info("tts_client_skipped", reason="NewAPI user billing is disabled")
        return

    from .openai_compatible_tts import OpenAICompatibleTTSProvider

    _tts_client = OpenAICompatibleTTSProvider(
        api_key=runtime_api_key() or "newapi-user-session",
        model=settings.voice.tts_model,
        base_url=user_relay_base_url(),
    )
    logger.info(
        "tts_client_initialized",
        provider="newapi_openai_compatible",
        model=settings.voice.tts_model,
    )


def get_tts_client() -> Optional[TTSPort]:
    return _tts_client


async def shutdown_tts_client() -> None:
    global _tts_client

    if _tts_client is None:
        return

    try:
        close = getattr(_tts_client, "close", None)
        if close:
            await close()
        logger.info("tts_client_shutdown")
    except Exception as exc:
        logger.error("tts_client_shutdown_failed", error=str(exc))
    finally:
        _tts_client = None


async def init_stt_client() -> None:
    """Initialize the OpenAI-compatible STT client for NewAPI user billing."""
    global _stt_client

    if _stt_client is not None:
        logger.warning("STT client already initialized")
        return
    if not user_billing_enabled():
        logger.info("stt_client_skipped", reason="NewAPI user billing is disabled")
        return

    from .openai_compatible_stt import OpenAICompatibleSTTProvider

    _stt_client = OpenAICompatibleSTTProvider(
        api_key=runtime_api_key() or "newapi-user-session",
        base_url=user_relay_base_url(),
        model=settings.voice.stt_model,
    )
    logger.info(
        "stt_client_initialized",
        provider="newapi_openai_compatible",
        model=settings.voice.stt_model,
    )


def get_stt_client() -> Optional[STTPort]:
    return _stt_client


async def shutdown_stt_client() -> None:
    global _stt_client

    if _stt_client is None:
        return

    try:
        close = getattr(_stt_client, "close", None)
        if close:
            await close()
        logger.info("stt_client_shutdown")
    except Exception as exc:
        logger.error("stt_client_shutdown_failed", error=str(exc))
    finally:
        _stt_client = None


__all__ = [
    "get_stt_client",
    "get_tts_client",
    "init_stt_client",
    "init_tts_client",
    "shutdown_stt_client",
    "shutdown_tts_client",
]
