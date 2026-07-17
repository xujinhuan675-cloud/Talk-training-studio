# input: openai SDK, LLMPort interface
# output: OpenAIProvider LLM implementation (Chat Completions / Responses API)
# owner: unknown
# pos: infrastructure - OpenAI-compatible LLM provider implementation; update this header and folder docs when changed
"""OpenAI SDK implementation of LLMPort."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlsplit, urlunsplit

from openai import AsyncOpenAI

from application.ports.llm import (
    LLMChunk,
    LLMEndpointMetadata,
    LLMMessage,
    LLMModelMetadata,
    LLMPort,
    LLMProviderMetadata,
    LLMResponse,
)
from core.logging_config import get_logger

logger = get_logger(__name__)


class OpenAIProvider:
    """LLMPort implementation using the OpenAI Python SDK.

    Compatible with OpenAI, Azure OpenAI, vLLM, and other
    OpenAI-API-compatible providers via base_url.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: Optional[str] = None,
        wire_api: str = "chat_completions",
        provider_name: str = "openai",
        default_model: str = "gpt-4o-mini",
        default_temperature: float = 0.7,
        default_max_tokens: int = 4096,
        timeout: int = 60,
        max_retries: int = 2,
        user_agent: str = "TalkTrainingStudio/1.0",
    ) -> None:
        normalized_base_url = self._normalize_base_url(base_url)
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=normalized_base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers={"User-Agent": user_agent},
        )
        self.provider = (provider_name or "openai").strip() or "openai"
        self._default_model = default_model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._wire_api = wire_api.lower().replace("-", "_")
        self._endpoint = normalized_base_url
        self._max_retries = max_retries

    @property
    def provider_metadata(self) -> LLMProviderMetadata:
        """Return stable provider identity for run/message tracking."""
        endpoint = str(self._endpoint) if self._endpoint else None
        default_model = LLMModelMetadata(
            name=self._default_model,
            provider=self.provider,
            endpoint=endpoint,
            is_default=True,
            max_output_tokens=self._default_max_tokens,
        )
        endpoint_metadata = LLMEndpointMetadata(
            provider=self.provider,
            endpoint=endpoint,
            wire_api=self._wire_api,
            default_model=self._default_model,
            models=[default_model],
        )
        return LLMProviderMetadata(
            provider=self.provider,
            default_model=self._default_model,
            endpoint=endpoint,
            wire_api=self._wire_api,
            max_retries=self._max_retries,
            models=[default_model],
            endpoints=[endpoint_metadata],
        )

    def _build_messages(self, messages: list[LLMMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _uses_responses_api(self) -> bool:
        return self._wire_api in {"responses", "response"}

    @staticmethod
    def _normalize_base_url(base_url: Optional[str]) -> Optional[str]:
        if not base_url:
            return None

        stripped = base_url.rstrip("/")
        parsed = urlsplit(stripped)
        if not parsed.scheme or not parsed.netloc:
            return base_url
        if parsed.path in {"", "/"}:
            return urlunsplit((parsed.scheme, parsed.netloc, "/v1", "", ""))
        return base_url

    def _build_responses_input(self, messages: list[LLMMessage]) -> list[dict]:
        return [
            {
                "role": (
                    m.role if m.role in {"user", "assistant", "system", "developer"} else "user"
                ),
                "content": m.content,
            }
            for m in messages
        ]

    @classmethod
    def _build_responses_schema(cls, schema: dict) -> dict:
        response_schema = deepcopy(schema)
        cls._fill_object_additional_properties(response_schema)
        return response_schema

    @classmethod
    def _fill_object_additional_properties(cls, node: Any) -> None:
        if not isinstance(node, dict):
            return

        type_decl = node.get("type")
        is_object = type_decl == "object" or (isinstance(type_decl, list) and "object" in type_decl)
        if is_object and "properties" in node and "additionalProperties" not in node:
            node["additionalProperties"] = False

        for key in ("properties", "$defs", "definitions"):
            children = node.get(key)
            if isinstance(children, dict):
                for child in children.values():
                    cls._fill_object_additional_properties(child)

        items = node.get("items")
        if isinstance(items, dict):
            cls._fill_object_additional_properties(items)
        elif isinstance(items, list):
            for item in items:
                cls._fill_object_additional_properties(item)

        additional_properties = node.get("additionalProperties")
        if isinstance(additional_properties, dict):
            cls._fill_object_additional_properties(additional_properties)

        for key in ("anyOf", "oneOf", "allOf"):
            variants = node.get(key)
            if isinstance(variants, list):
                for variant in variants:
                    cls._fill_object_additional_properties(variant)

    @staticmethod
    def _extract_response_text(response) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text

        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)
        return "".join(parts)

    @staticmethod
    def _response_usage(response) -> tuple[int, int, int]:
        usage = getattr(response, "usage", None)
        if not usage:
            return 0, 0, 0
        prompt_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = (
            getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
        )
        total_tokens = getattr(usage, "total_tokens", 0) or prompt_tokens + completion_tokens
        return prompt_tokens, completion_tokens, total_tokens

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        if self._uses_responses_api():
            response = await self._client.responses.create(
                model=model or self._default_model,
                input=self._build_responses_input(messages),
                temperature=temperature if temperature is not None else self._default_temperature,
                max_output_tokens=max_tokens or self._default_max_tokens,
            )
            prompt_tokens, completion_tokens, total_tokens = self._response_usage(response)
            return LLMResponse(
                content=self._extract_response_text(response),
                model=getattr(response, "model", model or self._default_model),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                finish_reason=getattr(response, "status", None),
            )

        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=self._build_messages(messages),
            temperature=temperature if temperature is not None else self._default_temperature,
            max_tokens=max_tokens or self._default_max_tokens,
            stream=False,
        )
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            finish_reason=choice.finish_reason,
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        *,
        schema: dict,
        schema_name: str = "output",
        schema_description: str = "",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Use OpenAI function calling to force structured output."""
        if self._uses_responses_api():
            response = await self._client.responses.create(
                model=model or self._default_model,
                input=self._build_responses_input(messages),
                temperature=temperature if temperature is not None else self._default_temperature,
                max_output_tokens=max_tokens or self._default_max_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "description": schema_description
                        or f"Output structured data as {schema_name}",
                        "schema": self._build_responses_schema(schema),
                        "strict": False,
                    }
                },
            )
            text = self._extract_response_text(response).strip()
            if not text:
                raise ValueError(f"Model did not return structured output '{schema_name}'")
            return json.loads(text)

        tool_def = {
            "type": "function",
            "function": {
                "name": schema_name,
                "description": schema_description or f"Output structured data as {schema_name}",
                "parameters": schema,
            },
        }

        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=self._build_messages(messages),
            temperature=temperature if temperature is not None else self._default_temperature,
            max_tokens=max_tokens or self._default_max_tokens,
            tools=[tool_def],
            tool_choice={"type": "function", "function": {"name": schema_name}},
            stream=False,
        )

        choice = response.choices[0]
        if choice.message.tool_calls:
            return json.loads(choice.message.tool_calls[0].function.arguments)

        raise ValueError(f"Model did not return expected function call '{schema_name}'")

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[LLMChunk]:
        if self._uses_responses_api():
            stream = await self._client.responses.create(
                model=model or self._default_model,
                input=self._build_responses_input(messages),
                temperature=temperature if temperature is not None else self._default_temperature,
                max_output_tokens=max_tokens or self._default_max_tokens,
                stream=True,
            )
            async for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    yield LLMChunk(content=getattr(event, "delta", "") or "")
                elif event_type == "response.completed":
                    response = getattr(event, "response", None)
                    prompt_tokens, completion_tokens, total_tokens = self._response_usage(response)
                    yield LLMChunk(
                        content="",
                        model=getattr(response, "model", model or self._default_model),
                        finish_reason=getattr(response, "status", None),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )
            return

        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=self._build_messages(messages),
            temperature=temperature if temperature is not None else self._default_temperature,
            max_tokens=max_tokens or self._default_max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in response:
            if not chunk.choices and chunk.usage:
                # Final chunk with usage stats only
                yield LLMChunk(
                    content="",
                    model=chunk.model or "",
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )
                continue

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            yield LLMChunk(
                content=delta.content or "",
                model=chunk.model or "",
                finish_reason=chunk.choices[0].finish_reason,
            )
