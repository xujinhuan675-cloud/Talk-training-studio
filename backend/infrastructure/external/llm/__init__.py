# input: NewAPI user relay settings and OpenAI-compatible model selection
# output: gateway-only LLM client lifecycle
# owner: TalkWise platform integration
# pos: infrastructure - NewAPI LLM protocol client lifecycle
"""Gateway-only LLM client lifecycle management."""

from __future__ import annotations

from typing import Optional

from core.config import settings
from core.logging_config import get_logger
from application.ports.llm import LLMPort
from infrastructure.external.newapi_user_gateway import (
    runtime_api_key,
    user_billing_enabled,
    user_relay_base_url,
)

logger = get_logger(__name__)

_llm_client: Optional[LLMPort] = None
async def init_llm_client() -> None:
    """Initialize the OpenAI-compatible client through NewAPI user billing."""
    global _llm_client

    if _llm_client is not None:
        logger.warning("LLM client already initialized")
        return

    if not user_billing_enabled():
        logger.warning(
            "llm_client_skipped",
            reason="NewAPI user billing is disabled",
        )
        return

    llm_cfg = settings.llm
    try:
        from .openai_provider import OpenAIProvider

        _llm_client = OpenAIProvider(
            api_key=runtime_api_key() or "newapi-user-session",
            base_url=user_relay_base_url(),
            wire_api=llm_cfg.wire_api,
            provider_name="newapi_openai_compatible",
            default_model=llm_cfg.default_model,
            default_temperature=llm_cfg.temperature,
            default_max_tokens=llm_cfg.max_tokens,
            timeout=llm_cfg.timeout,
            max_retries=llm_cfg.max_retries,
            user_agent=llm_cfg.user_agent,
        )
        logger.info(
            "llm_client_initialized",
            provider="newapi_openai_compatible",
            model=llm_cfg.default_model,
        )
    except Exception as exc:
        logger.error("llm_client_init_failed", error=str(exc))
        raise


def get_llm_client() -> Optional[LLMPort]:
    """Get the LLM client instance (may be None if not configured)."""
    return _llm_client


async def shutdown_llm_client() -> None:
    """Shutdown the LLM client."""
    global _llm_client

    if _llm_client is None:
        return

    try:
        # OpenAI client uses httpx internally; close if available
        client = getattr(_llm_client, "_client", None)
        if client is not None and hasattr(client, "close"):
            await client.close()
        logger.info("llm_client_shutdown")
    except Exception as exc:
        logger.error("llm_client_shutdown_failed", error=str(exc))
    finally:
        _llm_client = None


__all__ = [
    "init_llm_client",
    "get_llm_client",
    "shutdown_llm_client",
]
