from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.ports.llm import LLMEndpointMetadata, LLMModelMetadata, LLMProviderMetadata
from application.services.conversation_service import ConversationApplicationService
from domain.conversation.entity import Conversation, Message, Run
from domain.conversation.repository import OwnedMetadataScope
from infrastructure.external.llm.openai_provider import OpenAIProvider
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


def _metadata() -> dict:
    return {
        "ownerUserId": "user-sales-001",
        "teamId": "team-revenue",
        "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
    }


def _scope() -> OwnedMetadataScope:
    return OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_messages_filters_provider_and_model(session_factory):
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        conversation = await uow.conversation_repository.create(
            Conversation(id=None, title="Provider search", model="gpt-test", metadata=_metadata())
        )
        openai_message = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="assistant",
                content="Reusable provider answer",
                provider="openai",
                model="gpt-4o",
            )
        )
        await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="assistant",
                content="Reusable provider answer",
                provider="anthropic",
                model="claude-sonnet",
            )
        )
        await uow.commit()

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    results = await service.search_messages(
        conversation.id,
        "provider answer",
        provider="openai",
        model="gpt-4o",
        limit=1,
        metadata_scope=_scope(),
    )

    assert [result.message.public_id for result in results] == [openai_message.public_id]


@pytest.mark.asyncio
async def test_list_runs_filters_provider_status_and_trigger_message(session_factory):
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        conversation = await uow.conversation_repository.create(
            Conversation(id=None, title="Run filters", model="gpt-test", metadata=_metadata())
        )
        trigger = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="user",
                content="Trigger this run",
                provider="openai",
                model="gpt-4o",
            )
        )
        matching = await uow.run_repository.create(
            Run(
                id=None,
                conversation_id=conversation.id,
                status="completed",
                provider="openai",
                model="gpt-4o",
                metadata={
                    "trigger_message_id": trigger.public_id,
                    "branch_id": trigger.branch_id,
                    "provider_metadata": {
                        "provider": "openai",
                        "endpoint": "https://gateway.example/v1",
                        "wire_api": "responses",
                        "max_retries": 1,
                    },
                },
            )
        )
        await uow.run_repository.create(
            Run(
                id=None,
                conversation_id=conversation.id,
                status="failed",
                provider="anthropic",
                model="claude-sonnet",
                metadata={"trigger_message_id": "msg_other"},
            )
        )
        await uow.commit()

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    runs = await service.list_runs(
        conversation.id,
        provider="openai",
        status="completed",
        trigger_message_id=trigger.public_id,
        metadata_scope=_scope(),
    )

    assert [run.id for run in runs] == [matching.id]
    assert runs[0].trigger_message_id == trigger.public_id
    assert runs[0].branch_id == trigger.branch_id
    assert runs[0].provider_endpoint == "https://gateway.example/v1"
    assert runs[0].provider_wire_api == "responses"
    assert runs[0].provider_max_retries == 1


@pytest.mark.asyncio
async def test_list_runs_filters_before_pagination(session_factory):
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        conversation = await uow.conversation_repository.create(
            Conversation(
                id=None,
                title="Run filter pagination",
                model="gpt-test",
                metadata=_metadata(),
            )
        )
        matching = await uow.run_repository.create(
            Run(
                id=None,
                conversation_id=conversation.id,
                status="completed",
                provider="openai",
                model="gpt-4o",
                metadata={"trigger_message_id": "msg_oldest"},
                created_at=base_time,
            )
        )
        for index in range(505):
            await uow.run_repository.create(
                Run(
                    id=None,
                    conversation_id=conversation.id,
                    status="failed",
                    provider="anthropic",
                    model="claude-sonnet",
                    metadata={"trigger_message_id": f"msg_other_{index}"},
                    created_at=base_time + timedelta(seconds=index + 1),
                )
            )
        await uow.commit()

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    runs = await service.list_runs(
        conversation.id,
        provider="openai",
        status="completed",
        trigger_message_id="msg_oldest",
        limit=1,
        metadata_scope=_scope(),
    )

    assert [run.id for run in runs] == [matching.id]


def test_openai_compatible_provider_metadata_uses_configured_provider_name():
    provider = OpenAIProvider(
        api_key="test-key",
        base_url="https://gateway.example",
        provider_name="vllm",
        wire_api="responses",
        default_model="llama-test",
        max_retries=3,
    )

    metadata = provider.provider_metadata

    assert metadata.provider == "vllm"
    assert metadata.default_model == "llama-test"
    assert metadata.endpoint == "https://gateway.example/v1"
    assert metadata.wire_api == "responses"
    assert metadata.max_retries == 3
    assert [model.name for model in metadata.models] == ["llama-test"]
    assert metadata.models[0].is_default is True
    assert [endpoint.provider for endpoint in metadata.endpoints] == ["vllm"]
    assert metadata.endpoints[0].default_model == "llama-test"
    assert [model.name for model in metadata.endpoints[0].models] == ["llama-test"]


def test_llm_provider_metadata_can_represent_multiple_provider_endpoints():
    openai_model = LLMModelMetadata(
        name="gpt-4o",
        provider="openai",
        endpoint="https://api.openai.com/v1",
        is_default=True,
    )
    anthropic_model = LLMModelMetadata(
        name="claude-sonnet",
        provider="anthropic",
        endpoint="https://api.anthropic.com",
        is_default=True,
    )
    registry = LLMProviderMetadata(
        provider="talkwise",
        default_model="gpt-4o",
        models=[openai_model, anthropic_model],
        endpoints=[
            LLMEndpointMetadata(
                provider="openai",
                endpoint="https://api.openai.com/v1",
                wire_api="responses",
                default_model="gpt-4o",
                models=[openai_model],
            ),
            LLMEndpointMetadata(
                provider="anthropic",
                endpoint="https://api.anthropic.com",
                wire_api="messages",
                default_model="claude-sonnet",
                models=[anthropic_model],
            ),
        ],
    )

    assert [endpoint.provider for endpoint in registry.endpoints] == ["openai", "anthropic"]
    assert [model.name for model in registry.models] == ["gpt-4o", "claude-sonnet"]
