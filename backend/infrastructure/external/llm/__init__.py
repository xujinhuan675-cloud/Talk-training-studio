# input: core.config.settings.llm, core.config.settings.stakeholder, OpenAI SDK, Anthropic SDK
# output: LLM client lifecycle functions for OpenAI-compatible and Anthropic providers
# owner: unknown
# pos: infrastructure - LLM client lifecycle management; update this header and folder docs when changed
"""LLM client lifecycle management."""

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
_anthropic_client: Optional[LLMPort] = None


async def init_llm_client() -> None:
    """Initialize the LLM client based on configuration."""
    global _llm_client

    if _llm_client is not None:
        logger.warning("LLM client already initialized")
        return

    llm_cfg = settings.llm
    api_key = runtime_api_key(llm_cfg.api_key)
    if not api_key:
        logger.warning(
            "llm_client_skipped",
            reason="LLM__API_KEY not configured; LLM features will be unavailable",
        )
        return

    try:
        from .openai_provider import OpenAIProvider

        _llm_client = OpenAIProvider(
            api_key=api_key,
            base_url=user_relay_base_url() if user_billing_enabled() else llm_cfg.base_url,
            wire_api=llm_cfg.wire_api,
            provider_name=llm_cfg.provider,
            default_model=llm_cfg.default_model,
            default_temperature=llm_cfg.temperature,
            default_max_tokens=llm_cfg.max_tokens,
            timeout=llm_cfg.timeout,
            max_retries=llm_cfg.max_retries,
            user_agent=llm_cfg.user_agent,
        )
        logger.info(
            "llm_client_initialized",
            provider=llm_cfg.provider,
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


async def init_anthropic_client() -> None:
    """Initialize the Anthropic client for stakeholder chat."""
    global _anthropic_client

    if _anthropic_client is not None:
        logger.warning("Anthropic client already initialized")
        return

    if user_billing_enabled():
        logger.info(
            "anthropic_client_skipped",
            reason="NewAPI per-user billing routes stakeholder LLM calls through the shared OpenAI-compatible client",
        )
        return

    stakeholder_cfg = settings.stakeholder
    if not stakeholder_cfg.anthropic_api_key:
        logger.warning(
            "anthropic_client_skipped",
            reason="STAKEHOLDER__ANTHROPIC_API_KEY not configured; stakeholder features will be unavailable",
        )
        return

    try:
        from .anthropic_provider import AnthropicProvider

        _anthropic_client = AnthropicProvider(
            api_key=stakeholder_cfg.anthropic_api_key,
            base_url=stakeholder_cfg.anthropic_base_url,
            default_model=stakeholder_cfg.model,
        )
        logger.info(
            "anthropic_client_initialized",
            model=stakeholder_cfg.model,
        )
    except Exception as exc:
        logger.error("anthropic_client_init_failed", error=str(exc))
        raise


def get_anthropic_client() -> Optional[LLMPort]:
    """Get the Anthropic client instance (may be None if not configured)."""
    return _anthropic_client


async def shutdown_anthropic_client() -> None:
    """Shutdown the Anthropic client."""
    global _anthropic_client

    if _anthropic_client is None:
        return

    try:
        client = getattr(_anthropic_client, "_client", None)
        if client is not None and hasattr(client, "close"):
            await client.close()
        logger.info("anthropic_client_shutdown")
    except Exception as exc:
        logger.error("anthropic_client_shutdown_failed", error=str(exc))
    finally:
        _anthropic_client = None


__all__ = [
    "init_llm_client",
    "get_llm_client",
    "shutdown_llm_client",
    "init_anthropic_client",
    "get_anthropic_client",
    "shutdown_anthropic_client",
]
