# input: AbstractUnitOfWork, LLMPort, Conversation/Message/Run domain entities
# output: ChatApplicationService chat orchestration for streaming and non-streaming turns
# owner: unknown
# pos: application service - text chat workflow, message tree history, run tracking, and LLM calls; update this header and folder docs when changed
"""Application service for the chat workflow (send message -> LLM -> stream response)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Callable, Optional

from application.dto import (
    ChatRequestDTO,
    MessageDTO_Agent,
    RunDTO,
)
from application.ports.llm import LLMChunk, LLMMessage, LLMPort, LLMProviderMetadata, LLMResponse
from core.logging_config import get_logger
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.conversation.entity import Message, Run
from domain.conversation.exceptions import (
    ConversationArchivedException,
    ConversationNotFoundException,
    LLMProviderException,
)

logger = get_logger(__name__)
_HISTORY_MESSAGE_STATUSES = {"active", "superseded"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _RuntimeSelection:
    provider: str | None
    model: str | None
    model_spec: str | None
    source: str


class ChatApplicationService:
    """Orchestrates sending a message to LLM and streaming the response."""

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        llm: LLMPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._llm = llm

    async def _load_history(
        self,
        uow,
        conversation_id: int,
        *,
        tail_message_id: str | None = None,
        branch_id: str | None = None,
        limit: int = 200,
    ) -> list[LLMMessage]:
        """Load the active branch path as an LLMMessage list."""

        limit = max(1, min(limit, 200))
        if tail_message_id:
            messages: list[Message] = []
            seen: set[str] = set()
            current_id: str | None = tail_message_id
            while current_id and len(messages) < limit:
                if current_id in seen:
                    raise ValueError("Message tree contains a cycle")
                seen.add(current_id)
                message = await uow.message_repository.get_by_public_id(current_id)
                if message is None or message.conversation_id != conversation_id:
                    raise ValueError("Message tree path contains an invalid message")
                if message.status not in _HISTORY_MESSAGE_STATUSES:
                    raise ValueError("Message tree path contains an inactive message")
                messages.append(message)
                current_id = message.parent_message_id
            messages.reverse()
        else:
            messages = await uow.message_repository.list_by_conversation(
                conversation_id,
                limit=limit,
                branch_id=branch_id,
            )
            messages = [
                message for message in messages if message.status in _HISTORY_MESSAGE_STATUSES
            ]
        return [LLMMessage(role=m.role, content=m.content) for m in messages]

    async def _resolve_parent_message(
        self,
        uow,
        conversation_id: int,
        dto: ChatRequestDTO,
    ) -> tuple[Message | None, str]:
        requested_branch = _clean_optional_text(dto.branch_id)
        parent_public_id = _clean_optional_text(dto.parent_message_id)
        if parent_public_id:
            parent = await uow.message_repository.get_by_public_id(parent_public_id)
            if parent is None or parent.conversation_id != conversation_id:
                raise ValueError("parent_message_id does not reference this conversation")
            if parent.status not in _HISTORY_MESSAGE_STATUSES:
                raise ValueError("parent_message_id references an inactive message")
            return parent, requested_branch or parent.branch_id or "main"

        branch_id = requested_branch or "main"
        parent = await uow.message_repository.get_latest_by_conversation(
            conversation_id,
            branch_id=branch_id,
            statuses=tuple(_HISTORY_MESSAGE_STATUSES),
        )
        return parent, branch_id

    async def _create_user_message_run_and_history(
        self,
        uow,
        *,
        conversation_id: int,
        dto: ChatRequestDTO,
        model: str | None,
        now: datetime,
    ) -> tuple[Message, Run, list[LLMMessage], _RuntimeSelection]:
        parent_message, branch_id = await self._resolve_parent_message(uow, conversation_id, dto)
        provider_metadata = _llm_provider_metadata(self._llm)
        runtime_selection = _resolve_runtime_selection(
            dto=dto,
            parent_message=parent_message,
            conversation_model=model,
            provider_metadata=provider_metadata,
        )
        request_metadata = _run_request_metadata(
            provider=runtime_selection.provider,
            model=runtime_selection.model,
            model_spec=runtime_selection.model_spec,
            provider_metadata=provider_metadata,
            runtime_selection=runtime_selection,
            request_metadata=dto.metadata,
        )
        user_msg = Message(
            id=None,
            conversation_id=conversation_id,
            role="user",
            content=dto.message,
            parent_message_id=parent_message.public_id if parent_message else None,
            branch_id=branch_id,
            provider=runtime_selection.provider,
            model=runtime_selection.model,
            metadata=request_metadata,
            created_at=now,
        )
        user_msg = await uow.message_repository.create(user_msg)

        run = Run(
            id=None,
            conversation_id=conversation_id,
            status="running",
            provider=runtime_selection.provider,
            model=runtime_selection.model,
            metadata={
                "trigger_message_id": user_msg.public_id,
                "branch_id": branch_id,
                "parent_message_id": user_msg.parent_message_id,
                **request_metadata,
                "history_limit": dto.history_limit,
            },
            started_at=now,
            created_at=now,
        )
        run = await uow.run_repository.create(run)

        history = await self._load_history(
            uow,
            conversation_id,
            tail_message_id=user_msg.public_id,
            branch_id=branch_id,
            limit=dto.history_limit,
        )
        return user_msg, run, history, runtime_selection

    async def send_message_stream(
        self,
        conversation_id: int,
        dto: ChatRequestDTO,
    ) -> AsyncIterator[str]:
        """Send a user message and stream the assistant response as SSE events.

        Yields SSE-formatted strings: `data: {...}\\n\\n`
        """
        # Phase 1: persist user message and create run
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            if not conv.is_active():
                raise ConversationArchivedException(conversation_id)

            model = dto.model or conv.model
            now = _utcnow()
            user_msg, run, history, runtime_selection = (
                await self._create_user_message_run_and_history(
                    uow,
                    conversation_id=conversation_id,
                    dto=dto,
                    model=model,
                    now=now,
                )
            )

            await uow.commit()

        run_id = run.id
        user_msg_id = user_msg.id

        # Build LLM messages
        llm_messages: list[LLMMessage] = []
        # Add system prompt if present
        if conv.system_prompt:
            llm_messages.append(LLMMessage(role="system", content=conv.system_prompt))
        llm_messages.extend(history)

        # Yield user message event
        yield _sse_event(
            "message_created",
            {
                "message_id": user_msg_id,
                "public_id": user_msg.public_id,
                "parent_message_id": user_msg.parent_message_id,
                "branch_id": user_msg.branch_id,
                "role": "user",
            },
        )

        # Phase 2: stream LLM response
        full_content = ""
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        finish_reason: Optional[str] = None
        provider_metadata = _llm_provider_metadata(self._llm)
        response_model = runtime_selection.model
        response_provider = runtime_selection.provider

        try:
            async for chunk in self._llm.stream(
                llm_messages,
                model=runtime_selection.model,
                temperature=dto.temperature,
                max_tokens=dto.max_tokens,
            ):
                if chunk.content:
                    full_content += chunk.content
                    yield _sse_event(
                        "message_delta",
                        {
                            "content": chunk.content,
                        },
                    )
                # Capture usage from final chunk
                if chunk.total_tokens > 0:
                    prompt_tokens = chunk.prompt_tokens
                    completion_tokens = chunk.completion_tokens
                    total_tokens = chunk.total_tokens
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
                if chunk.model:
                    response_model = chunk.model

        except Exception as exc:
            logger.error("llm_stream_failed", error=str(exc), run_id=run_id)
            # Persist failure
            async with self._uow_factory() as uow:
                run_entity = await uow.run_repository.get_by_id(run_id)
                if run_entity:
                    run_entity.mark_failed(str(exc))
                    run_entity.metadata = _failed_run_metadata(run_entity.metadata, exc)
                    await uow.run_repository.update(run_entity)
                await uow.commit()

            yield _sse_event(
                "error", {"message": "An error occurred while generating the response."}
            )
            yield _sse_event("done", {})
            return

        # Phase 3: persist assistant message and complete run
        async with self._uow_factory() as uow:
            assistant_msg = Message(
                id=None,
                conversation_id=conversation_id,
                role="assistant",
                content=full_content,
                parent_message_id=user_msg.public_id,
                branch_id=user_msg.branch_id,
                finish_reason=finish_reason,
                provider=response_provider,
                model=response_model,
                run_id=run_id,
                token_count=completion_tokens,
                metadata=_run_request_metadata(
                    provider=response_provider,
                    model=response_model,
                    model_spec=runtime_selection.model_spec,
                    provider_metadata=provider_metadata,
                    runtime_selection=runtime_selection,
                    request_metadata=dto.metadata,
                ),
                created_at=_utcnow(),
            )
            assistant_msg = await uow.message_repository.create(assistant_msg)

            run_entity = await uow.run_repository.get_by_id(run_id)
            if run_entity:
                run_entity.mark_completed(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    finish_reason=finish_reason,
                )
                await uow.run_repository.update(run_entity)

            await uow.commit()

        yield _sse_event(
            "message_complete",
            {
                "message_id": assistant_msg.id,
                "public_id": assistant_msg.public_id,
                "parent_message_id": assistant_msg.parent_message_id,
                "branch_id": assistant_msg.branch_id,
                "role": "assistant",
                "content": full_content,
            },
        )
        yield _sse_event(
            "run_complete",
            {
                "run_id": run_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        )
        yield _sse_event("done", {})

    async def send_message_sync(
        self,
        conversation_id: int,
        dto: ChatRequestDTO,
    ) -> dict:
        """Send a user message and return the full assistant response (non-streaming)."""
        # Phase 1: persist user message and create run
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            if not conv.is_active():
                raise ConversationArchivedException(conversation_id)

            model = dto.model or conv.model
            now = _utcnow()
            user_msg, run, history, runtime_selection = (
                await self._create_user_message_run_and_history(
                    uow,
                    conversation_id=conversation_id,
                    dto=dto,
                    model=model,
                    now=now,
                )
            )
            await uow.commit()

        run_id = run.id

        llm_messages: list[LLMMessage] = []
        if conv.system_prompt:
            llm_messages.append(LLMMessage(role="system", content=conv.system_prompt))
        llm_messages.extend(history)

        # Phase 2: call LLM
        try:
            response: LLMResponse = await self._llm.generate(
                llm_messages,
                model=runtime_selection.model,
                temperature=dto.temperature,
                max_tokens=dto.max_tokens,
            )
        except Exception as exc:
            logger.error("llm_generate_failed", error=str(exc), run_id=run_id)
            async with self._uow_factory() as uow:
                run_entity = await uow.run_repository.get_by_id(run_id)
                if run_entity:
                    run_entity.mark_failed(str(exc))
                    run_entity.metadata = _failed_run_metadata(run_entity.metadata, exc)
                    await uow.run_repository.update(run_entity)
                await uow.commit()
            raise LLMProviderException(str(exc))

        # Phase 3: persist assistant message and complete run
        async with self._uow_factory() as uow:
            provider_metadata = _llm_provider_metadata(self._llm)
            response_provider = runtime_selection.provider
            response_model = response.model or runtime_selection.model
            assistant_msg = Message(
                id=None,
                conversation_id=conversation_id,
                role="assistant",
                content=response.content,
                parent_message_id=user_msg.public_id,
                branch_id=user_msg.branch_id,
                finish_reason=response.finish_reason,
                provider=response_provider,
                model=response_model,
                run_id=run_id,
                token_count=response.completion_tokens,
                metadata=_run_request_metadata(
                    provider=response_provider,
                    model=response_model,
                    model_spec=runtime_selection.model_spec,
                    provider_metadata=provider_metadata,
                    runtime_selection=runtime_selection,
                    request_metadata=dto.metadata,
                ),
                created_at=_utcnow(),
            )
            assistant_msg = await uow.message_repository.create(assistant_msg)

            run_entity = await uow.run_repository.get_by_id(run_id)
            if run_entity:
                run_entity.mark_completed(
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    total_tokens=response.total_tokens,
                    finish_reason=response.finish_reason,
                )
                await uow.run_repository.update(run_entity)

            await uow.commit()

        return {
            "message": MessageDTO_Agent.model_validate(assistant_msg).model_dump(),
            "run": RunDTO.model_validate(run_entity).model_dump() if run_entity else None,
        }


def _sse_event(event: str, data: dict) -> str:
    """Format an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _clean_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _llm_provider_metadata(llm: LLMPort) -> LLMProviderMetadata:
    metadata = getattr(llm, "provider_metadata", None)
    if isinstance(metadata, LLMProviderMetadata):
        return metadata
    provider = _clean_optional_text(getattr(llm, "provider", None)) or "unknown"
    default_model = _clean_optional_text(getattr(llm, "_default_model", None))
    return LLMProviderMetadata(provider=provider, default_model=default_model)


def _metadata_mapping(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _metadata_text(metadata: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        text = _clean_optional_text(metadata.get(key))
        if text:
            return text
    return None


def _selection_from_metadata(
    metadata: dict[str, object],
) -> tuple[str | None, str | None, str | None]:
    nested_llm = _metadata_mapping(metadata.get("llm"))
    provider = _metadata_text(metadata, "provider", "llm_provider") or _metadata_text(
        nested_llm,
        "provider",
    )
    model = _metadata_text(metadata, "model", "llm_model") or _metadata_text(
        nested_llm,
        "model",
    )
    model_spec = _metadata_text(
        metadata,
        "model_spec",
        "modelSpec",
        "llm_model_spec",
    ) or _metadata_text(nested_llm, "model_spec", "modelSpec", "model_spec_id", "name")
    return provider, model, model_spec


def _resolve_runtime_selection(
    *,
    dto: ChatRequestDTO,
    parent_message: Message | None,
    conversation_model: str | None,
    provider_metadata: LLMProviderMetadata,
) -> _RuntimeSelection:
    request_provider, request_model, request_model_spec = _selection_from_metadata(dto.metadata)
    parent_provider, parent_model, parent_model_spec = _selection_from_metadata(
        _metadata_mapping(parent_message.metadata if parent_message else None)
    )
    provider = (
        _clean_optional_text(dto.provider)
        or request_provider
        or parent_provider
        or _clean_optional_text(provider_metadata.provider)
    )
    model = (
        _clean_optional_text(dto.model)
        or request_model
        or parent_model
        or conversation_model
        or provider_metadata.default_model
    )
    model_spec = _clean_optional_text(dto.model_spec) or request_model_spec or parent_model_spec
    if _clean_optional_text(dto.provider) or _clean_optional_text(dto.model) or _clean_optional_text(
        dto.model_spec
    ) or request_provider or request_model or request_model_spec:
        source = "chat_request"
    elif parent_provider or parent_model or parent_model_spec:
        source = "parent_message_metadata"
    elif conversation_model:
        source = "conversation"
    else:
        source = "provider_default"
    return _RuntimeSelection(
        provider=provider,
        model=model,
        model_spec=model_spec,
        source=source,
    )


def _run_request_metadata(
    *,
    provider: str | None,
    model: str | None,
    provider_metadata: LLMProviderMetadata,
    model_spec: str | None = None,
    runtime_selection: _RuntimeSelection | None = None,
    request_metadata: dict[str, object] | None = None,
) -> dict[str, object | None]:
    metadata: dict[str, object | None] = {
        **_metadata_mapping(request_metadata),
        "provider": provider,
        "model": model,
        "model_spec": model_spec,
        "provider_metadata": {
            "provider": provider_metadata.provider,
            "default_model": provider_metadata.default_model,
            "endpoint": provider_metadata.endpoint,
            "wire_api": provider_metadata.wire_api,
            "max_retries": provider_metadata.max_retries,
            **provider_metadata.extra,
        },
    }
    if runtime_selection is not None:
        metadata["runtime_selection"] = {
            "provider": runtime_selection.provider,
            "model": runtime_selection.model,
            "model_spec": runtime_selection.model_spec,
            "source": runtime_selection.source,
        }
    return metadata


def _failed_run_metadata(
    metadata: dict | None,
    exc: Exception,
) -> dict[str, object | None]:
    return {
        **(metadata or {}),
        "error_type": type(exc).__name__,
        "retryable": _is_retryable_llm_error(exc),
    }


def _is_retryable_llm_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code in {408, 409, 429} or 500 <= status_code < 600
    name = type(exc).__name__.lower()
    return any(
        token in name
        for token in (
            "timeout",
            "rate",
            "connection",
            "temporary",
            "overload",
        )
    )
