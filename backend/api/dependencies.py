"""
API 依赖项
"""

import time
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request

from application.services.file_asset_service import FileAssetApplicationService
from application.services.idempotency_service import IdempotencyService
from application.services.conversation_service import ConversationApplicationService
from application.services.chat_service import ChatApplicationService
from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
from application.services.stakeholder.persona_loader import PersonaLoader
from application.services.stakeholder.persona_editor_service import PersonaEditorService
from application.services.stakeholder.scenario_service import ScenarioApplicationService
from application.services.stakeholder.analysis_service import AnalysisService, AnalysisReaderService
from application.services.stakeholder.coaching_service import CoachingService
from application.services.stakeholder.stakeholder_chat_service import StakeholderChatService
from application.ports.storage import StoragePort
from application.ports.llm import LLMPort
from application.ports.tts import TTSPort
from application.ports.stt import STTPort
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from infrastructure.external.storage import get_storage
from infrastructure.external.llm import get_llm_client, get_anthropic_client
from infrastructure.external.voice import get_tts_client, get_stt_client
from infrastructure.adapters.storage_port import StorageProviderPortAdapter
from infrastructure.adapters.idempotency_store import RedisIdempotencyStore
from infrastructure.external.newapi_auth import (
    NewAPIAuthError,
    NewAPIAuthUnavailableError,
    NewAPIIdentity,
    exchange_newapi_authorization_code,
    fetch_newapi_identity,
)
from infrastructure.auth_session import current_user_from_session_cookie
from core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    system_role: str
    team_id: str | None = None
    team_name: str | None = None
    team_role: str | None = None
    username: str | None = None
    display_name: str | None = None
    business_role: str | None = None
    newapi_group: str | None = None
    quota_remaining: int | None = None
    quota_used: int | None = None
    quota_total: int | None = None
    request_count: int | None = None
    subscription_plan: str | None = None
    subscription_status: str | None = None
    newapi_gateway_base_url: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.system_role == "admin"

    @property
    def can_manage_team(self) -> bool:
        return self.is_admin or self.team_role in {"owner", "admin"}

    @property
    def is_staff(self) -> bool:
        return not self.is_admin


@dataclass(frozen=True)
class TrainingScope:
    user_id: str | None = None
    team_id: str | None = None


_MOCK_USERS: dict[str, CurrentUser] = {
    "admin": CurrentUser(
        user_id="user-admin-001",
        username="admin",
        system_role="admin",
        business_role="operations",
        team_id="team-ops",
    ),
    "sales": CurrentUser(
        user_id="user-sales-001",
        username="sales",
        system_role="staff",
        business_role="sales",
        team_id="team-revenue",
    ),
    "customer_service": CurrentUser(
        user_id="user-cs-001",
        username="customer_service",
        system_role="staff",
        business_role="customer_service",
        team_id="team-service",
    ),
}
_MOCK_USERS_BY_USER_ID = {user.user_id: user for user in _MOCK_USERS.values()}
_SYSTEM_ROLES = {"admin", "staff"}
_AI_RATE_WINDOWS: dict[str, tuple[int, int]] = {}


def _coerce_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_bearer_token(authorization: str | None) -> str | None:
    value = _coerce_optional_text(authorization)
    if not value:
        return None
    scheme, separator, token = value.partition(" ")
    if separator and scheme.lower() == "bearer":
        return token.strip() or None
    return None


def _has_mock_auth_signal(*values: object | None) -> bool:
    return any(_coerce_optional_text(value) for value in values)


def _is_admin_from_newapi_role(role: int) -> bool:
    if role >= settings.NEWAPI_ADMIN_ROLE_VALUE:
        return True
    return False


def _current_user_from_newapi_identity(identity: NewAPIIdentity) -> CurrentUser:
    group = _coerce_optional_text(identity.group)
    team_id = _coerce_optional_text(identity.team_id)
    team_name = _coerce_optional_text(identity.team_name)
    gateway_base_url = _coerce_optional_text(identity.gateway_base_url)
    quota_remaining = identity.quota
    quota_used = identity.used_quota
    quota_total = (
        quota_remaining + quota_used
        if quota_remaining is not None and quota_used is not None
        else None
    )
    is_admin = _is_admin_from_newapi_role(identity.role)
    return CurrentUser(
        user_id=f"newapi:{identity.id}",
        username=identity.username,
        display_name=identity.display_name,
        system_role="admin" if is_admin else "staff",
        business_role=settings.NEWAPI_DEFAULT_BUSINESS_ROLE,
        team_id=team_id,
        team_name=team_name,
        team_role=_coerce_optional_text(identity.team_role),
        newapi_group=group,
        quota_remaining=quota_remaining,
        quota_used=quota_used,
        quota_total=quota_total,
        request_count=identity.request_count,
        subscription_plan=identity.subscription_plan,
        subscription_status=identity.subscription_status,
        newapi_gateway_base_url=gateway_base_url or settings.NEWAPI_GATEWAY_BASE_URL,
    )


async def get_current_user_from_newapi_token(access_token: str) -> CurrentUser:
    try:
        identity = await fetch_newapi_identity(
            access_token,
            base_url=settings.NEWAPI_BASE_URL,
            timeout_seconds=settings.NEWAPI_AUTH_TIMEOUT_SECONDS,
        )
    except NewAPIAuthUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        ) from exc
    except NewAPIAuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    return _current_user_from_newapi_identity(identity)


async def get_current_user_from_newapi_code(
    code: str,
    *,
    redirect_uri: str | None = None,
) -> CurrentUser:
    try:
        identity = await exchange_newapi_authorization_code(
            code,
            base_url=settings.NEWAPI_BASE_URL,
            client_id=settings.NEWAPI_TALKWISE_CLIENT_ID,
            client_secret=settings.NEWAPI_TALKWISE_CLIENT_SECRET,
            redirect_uri=redirect_uri or settings.NEWAPI_TALKWISE_REDIRECT_URI,
            exchange_path=settings.NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH,
            timeout_seconds=settings.NEWAPI_AUTH_TIMEOUT_SECONDS,
        )
    except NewAPIAuthUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        ) from exc
    except NewAPIAuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid authorization code") from exc
    return _current_user_from_newapi_identity(identity)


async def get_current_user(
    talkwise_session: str | None = Cookie(
        default=None,
        alias=settings.TALKWISE_SESSION_COOKIE_NAME,
    ),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_mock_user: str | None = Header(default=None, alias="X-Mock-User"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_system_role: str | None = Header(default=None, alias="X-System-Role"),
    x_role: str | None = Header(default=None, alias="X-Role"),
    x_team_id: str | None = Header(default=None, alias="X-Team-Id"),
    q_mock_user: str | None = Query(default=None, alias="mock_user"),
    q_user_id: str | None = Query(default=None, alias="auth_user_id"),
    q_system_role: str | None = Query(default=None, alias="auth_role"),
    q_team_id: str | None = Query(default=None, alias="auth_team_id"),
) -> CurrentUser:
    bearer_token = extract_bearer_token(authorization)
    if bearer_token:
        try:
            return await get_current_user_from_newapi_token(bearer_token)
        except HTTPException:
            if settings.NEWAPI_AUTH_ENABLED or not _has_mock_auth_signal(
                x_mock_user,
                x_user_id,
                x_user_role,
                x_system_role,
                x_role,
                x_team_id,
                q_mock_user,
                q_user_id,
                q_system_role,
                q_team_id,
            ):
                raise

    # The NewAPI bearer identity is authoritative for same-origin module
    # requests. The signed cookie remains a compatibility fallback, but must
    # not preserve stale team membership after an administrator changes it.
    session_user = current_user_from_session_cookie(talkwise_session)
    if session_user is not None:
        return session_user

    if settings.NEWAPI_AUTH_ENABLED and not settings.NEWAPI_AUTH_ALLOW_MOCK_FALLBACK:
        raise HTTPException(status_code=401, detail="Access token required")

    named_mock_key = _coerce_optional_text(x_mock_user) or _coerce_optional_text(q_mock_user)
    if named_mock_key:
        if named_mock_key in _MOCK_USERS:
            return _MOCK_USERS[named_mock_key]
        if named_mock_key not in _MOCK_USERS_BY_USER_ID:
            raise HTTPException(status_code=401, detail="Unknown mock user")

    explicit_user_id = _coerce_optional_text(x_user_id) or _coerce_optional_text(q_user_id)
    known_user_id = named_mock_key or explicit_user_id
    if known_user_id in _MOCK_USERS_BY_USER_ID:
        base = _MOCK_USERS_BY_USER_ID[known_user_id]
        return CurrentUser(
            user_id=base.user_id,
            username=base.username,
            system_role=base.system_role,
            business_role=base.business_role,
            team_id=(
                _coerce_optional_text(x_team_id)
                or _coerce_optional_text(q_team_id)
                or base.team_id
            ),
        )

    role = (
        _coerce_optional_text(x_system_role)
        or _coerce_optional_text(q_system_role)
        or _coerce_optional_text(x_user_role)
        or _coerce_optional_text(x_role)
    )
    role = role.lower() if role else None
    if role in {"sales", "customer_service", "operations"}:
        business_role = role
        role = "staff"
    else:
        business_role = None
    if role is not None and role not in _SYSTEM_ROLES:
        raise HTTPException(status_code=401, detail="Unsupported mock user role")

    if explicit_user_id:
        return CurrentUser(
            user_id=explicit_user_id,
            username=explicit_user_id,
            system_role=role or "staff",
            business_role=business_role,
            team_id=_coerce_optional_text(x_team_id) or _coerce_optional_text(q_team_id),
        )

    # Local development default: keep existing tests and no-auth workflows working.
    return _MOCK_USERS["admin"]


def require_system_roles(*roles: str):
    allowed = {role.lower() for role in roles}

    async def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.system_role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return _dependency


def training_scope_for(
    current_user: CurrentUser,
    *,
    requested_user_id: str | None = None,
    requested_team_id: str | None = None,
) -> TrainingScope:
    user_id = _coerce_optional_text(requested_user_id)
    if current_user.is_admin:
        return TrainingScope(user_id=user_id, team_id=current_user.team_id)
    return TrainingScope(user_id=current_user.user_id, team_id=current_user.team_id)


def reset_ai_rate_limit_state() -> None:
    _AI_RATE_WINDOWS.clear()


async def enforce_ai_rate_limit(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    limit = int(settings.RATE_LIMIT_PER_MINUTE or 0)
    if limit <= 0:
        return

    client_host = request.client.host if request.client else "unknown"
    if current_user.user_id:
        bucket = f"user:{current_user.system_role}:{current_user.user_id}"
    else:
        bucket = f"ip:{client_host}"
    window = int(time.time() // 60)
    current_window, count = _AI_RATE_WINDOWS.get(bucket, (window, 0))
    if current_window != window:
        current_window, count = window, 0
    count += 1
    _AI_RATE_WINDOWS[bucket] = (current_window, count)
    if count > limit:
        raise HTTPException(status_code=429, detail="AI rate limit exceeded")


async def get_storage_port(provider=Depends(get_storage)) -> StoragePort:
    return StorageProviderPortAdapter(provider)


async def get_file_asset_service(
    storage: StoragePort = Depends(get_storage_port),
) -> FileAssetApplicationService:
    return FileAssetApplicationService(uow_factory=SQLAlchemyUnitOfWork, storage=storage)


async def get_idempotency_service() -> IdempotencyService:
    if not settings.redis.url:

        class _NoopStore:
            async def get(self, *, scope: str, key: str):
                return None

            async def try_start(
                self, *, scope: str, key: str, request_hash: str, ttl_seconds: int
            ) -> bool:
                return True

            async def set_result(
                self, *, scope: str, key: str, request_hash: str, payload: dict, ttl_seconds: int
            ) -> None:
                return None

            async def release(self, *, scope: str, key: str) -> None:
                return None

        store = _NoopStore()
    else:
        store = RedisIdempotencyStore()
    return IdempotencyService(
        store=store,
        lock_ttl_seconds=settings.idempotency.lock_ttl_seconds,
        result_ttl_seconds=settings.idempotency.result_ttl_seconds,
    )


async def get_conversation_service() -> ConversationApplicationService:
    return ConversationApplicationService(uow_factory=SQLAlchemyUnitOfWork)


async def get_llm_port() -> LLMPort:
    client = get_llm_client()
    if client is None:
        raise RuntimeError(
            "LLM client not initialized. " "Set LLM__API_KEY in environment or .env and restart."
        )
    return client


def get_stakeholder_llm_client() -> LLMPort | None:
    """Prefer the configured OpenAI-compatible client for stakeholder flows.

    Anthropic remains a fallback for deployments that still configure the
    stakeholder-specific Claude provider.
    """
    return get_llm_client() or get_anthropic_client()


async def get_stakeholder_llm_port() -> LLMPort:
    client = get_stakeholder_llm_client()
    if client is None:
        raise RuntimeError(
            "Stakeholder LLM client not initialized. "
            "Set LLM__API_KEY for OpenAI-compatible mode, or "
            "STAKEHOLDER__ANTHROPIC_API_KEY for Anthropic mode, then restart."
        )
    return client


async def get_tts_port() -> TTSPort:
    client = get_tts_client()
    if client is None:
        raise RuntimeError(
            "TTS client not initialized. "
            "Set VOICE__TTS_API_KEY in environment or .env and restart."
        )
    return client


async def get_stt_port() -> STTPort:
    client = get_stt_client()
    if client is None:
        raise RuntimeError(
            "STT client not initialized. "
            "Set VOICE__STT_API_KEY in environment or .env and restart."
        )
    return client


def get_persona_loader() -> PersonaLoader:
    return PersonaLoader(persona_dir=settings.stakeholder.persona_dir)


async def get_persona_loader_with_v2(
    loader: PersonaLoader = Depends(get_persona_loader),
    current_user: CurrentUser = Depends(get_current_user),
) -> PersonaLoader:
    """Story 2.8: make v2 DB personas visible to chat / battle flows.

    Merges v2 structured personas into the loader's cache once per request.
    PersonaLoader itself has a 30 s TTL so repeated calls within a single
    request are near-free.
    """
    async with SQLAlchemyUnitOfWork() as uow:
        try:
            from application.services.stakeholder.persona_access_policy import can_read_persona

            scope = persona_access_scope_for(current_user)
            persisted = await uow.stakeholder_persona_repository.list_all()
            visible = [persona for persona in persisted if can_read_persona(persona, scope)]
            await loader.refresh_from_db(
                uow.stakeholder_persona_repository,
                personas=visible,
            )
        except Exception:
            # Best-effort: a broken DB shouldn't knock out the chat flow entirely.
            pass
    return loader


def get_persona_editor_service(
    loader: PersonaLoader = Depends(get_persona_loader),
) -> PersonaEditorService:
    return PersonaEditorService(persona_dir=settings.stakeholder.persona_dir, persona_loader=loader)


def get_chatroom_service(
    loader: PersonaLoader = Depends(get_persona_loader_with_v2),
) -> ChatRoomApplicationService:
    return ChatRoomApplicationService(uow_factory=SQLAlchemyUnitOfWork, persona_loader=loader)


async def get_stakeholder_chat_service(
    loader: PersonaLoader = Depends(get_persona_loader_with_v2),
    llm: LLMPort = Depends(get_stakeholder_llm_port),
) -> StakeholderChatService:
    from application.services.stakeholder.compression_service import CompressionService
    from application.services.stakeholder.dispatcher import Dispatcher

    dispatcher = Dispatcher(llm=llm, persona_loader=loader)
    compression = CompressionService(
        uow_factory=SQLAlchemyUnitOfWork,
        llm=llm,
        persona_loader=loader,
    )
    # TTS is optional — None if not configured
    tts = get_tts_client()
    tts_provider = settings.voice.tts_provider
    normalized_tts_provider = str(tts_provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    native_tts_provider = (
        normalized_tts_provider in {"openai", "openai_tts"}
        and _turn_based_openai_tts_key_available()
    )
    voice_pipeline = None
    if tts is not None or native_tts_provider:
        from infrastructure.external.pipecat import PipecatTurnBasedCascadePipeline

        voice_pipeline = PipecatTurnBasedCascadePipeline(
            tts,
            tts_provider=tts_provider,
            tts_model=settings.voice.tts_model,
            tts_api_key=settings.voice.tts_api_key,
            tts_base_url=settings.voice.tts_base_url,
        )
    return StakeholderChatService(
        uow_factory=SQLAlchemyUnitOfWork,
        persona_loader=loader,
        llm=llm,
        dispatcher=dispatcher,
        max_group_rounds=settings.stakeholder.max_group_rounds,
        compression_service=compression,
        voice_pipeline=voice_pipeline,
    )


def _turn_based_openai_tts_key_available() -> bool:
    llm_provider = (
        str(getattr(settings.llm, "provider", "") or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )
    llm_base_url = str(getattr(settings.llm, "base_url", "") or "").strip().lower()
    llm_key = None
    if (
        llm_provider not in {"openrouter", "open_router", "openrouter_ai", "openrouter_compatible"}
        and "openrouter.ai" not in llm_base_url
    ):
        llm_key = settings.llm.api_key
    return bool(
        settings.voice.tts_api_key
        or settings.REALTIME_OPENAI_API_KEY
        or settings.OPENAI_API_KEY
        or llm_key
    )


async def get_analysis_service(
    loader: PersonaLoader = Depends(get_persona_loader),
    llm: LLMPort = Depends(get_stakeholder_llm_port),
) -> AnalysisService:
    return AnalysisService(uow_factory=SQLAlchemyUnitOfWork, llm=llm, persona_loader=loader)


async def get_analysis_reader_service(
    loader: PersonaLoader = Depends(get_persona_loader_with_v2),
) -> AnalysisReaderService:
    """Read-only analysis service for list/get."""
    return AnalysisReaderService(uow_factory=SQLAlchemyUnitOfWork, persona_loader=loader)


async def get_coaching_service(
    loader: PersonaLoader = Depends(get_persona_loader),
    llm: LLMPort = Depends(get_stakeholder_llm_port),
) -> CoachingService:
    return CoachingService(uow_factory=SQLAlchemyUnitOfWork, llm=llm, persona_loader=loader)


def get_scenario_service() -> ScenarioApplicationService:
    return ScenarioApplicationService(uow_factory=SQLAlchemyUnitOfWork)


def get_organization_service():
    from application.services.stakeholder.organization_service import OrganizationService

    return OrganizationService(uow_factory=SQLAlchemyUnitOfWork)


async def get_growth_service(
    loader: PersonaLoader = Depends(get_persona_loader),
):
    from application.services.stakeholder.growth_service import GrowthService

    llm = get_stakeholder_llm_client()
    return GrowthService(uow_factory=SQLAlchemyUnitOfWork, llm=llm, persona_loader=loader)


async def get_battle_prep_service(
    loader: PersonaLoader = Depends(get_persona_loader_with_v2),
    editor: PersonaEditorService = Depends(get_persona_editor_service),
    llm: LLMPort = Depends(get_stakeholder_llm_port),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
):
    from application.services.stakeholder.battle_prep_service import BattlePrepService

    return BattlePrepService(
        uow_factory=SQLAlchemyUnitOfWork,
        llm=llm,
        chatroom_service=chatroom_svc,
        persona_editor=editor,
        persona_loader=loader,
        persona_dir=settings.stakeholder.persona_dir,
    )


async def get_chat_service(
    llm: LLMPort = Depends(get_llm_port),
) -> ChatApplicationService:
    return ChatApplicationService(uow_factory=SQLAlchemyUnitOfWork, llm=llm)


# ---------------------------------------------------------------------------
# Speaker Detection dependency
# ---------------------------------------------------------------------------


async def get_speaker_detection_service(
    llm: LLMPort = Depends(get_stakeholder_llm_port),
):
    from application.services.stakeholder.speaker_detection_service import SpeakerDetectionService

    return SpeakerDetectionService(llm=llm)


# ---------------------------------------------------------------------------
# Persona Builder dependencies (Story 2.4 / 2.5)
# ---------------------------------------------------------------------------


def persona_access_scope_for(current_user: CurrentUser):
    """Translate authenticated NewAPI identity into Persona asset scope."""
    from application.services.stakeholder.persona_access_policy import PersonaAccessScope

    return PersonaAccessScope(
        user_id=current_user.user_id,
        team_id=current_user.team_id,
        can_manage_team=current_user.can_manage_team,
        unrestricted=current_user.is_admin,
    )


class _UoWBoundStakeholderPersonaRepo:
    """Adapter that gives PersonaBuilderService a save method that creates
    its own UoW per call (the build runs across many seconds, so binding to
    a single request-scoped session would be unsafe)."""

    def __init__(self, uow_factory, *, access_scope):
        self._uow_factory = uow_factory
        self._access_scope = access_scope

    async def save_structured_persona(self, persona):
        from application.services.stakeholder.persona_access_policy import require_persona_manage

        async with self._uow_factory() as uow:
            existing = await uow.stakeholder_persona_repository.get_by_id(persona.id)
            if existing is None:
                # Owner/team are always derived from the authenticated service
                # context. The builder never accepts these fields from a request.
                persona.owner_user_id = self._access_scope.user_id
                persona.owner_team_id = self._access_scope.team_id
                persona.visibility = "private"
                persona.version = 1
            else:
                require_persona_manage(existing, self._access_scope)
                # An LLM merge may return a newly constructed aggregate; keep
                # the existing asset boundary intact before persisting it.
                persona.owner_user_id = existing.owner_user_id
                persona.owner_team_id = existing.owner_team_id
                persona.visibility = existing.visibility
            await uow.stakeholder_persona_repository.save_structured_persona(persona)
            await uow.commit()

    async def get_by_id(self, persona_id: str):
        from application.services.stakeholder.persona_access_policy import require_persona_read

        async with self._uow_factory() as uow:
            persona = await uow.stakeholder_persona_repository.get_by_id(persona_id)
        if persona is not None:
            require_persona_read(persona, self._access_scope)
        return persona


def _load_stakeholder_prompt(name: str) -> str:
    """Load a prompt markdown file from application/services/stakeholder/prompts/."""
    from importlib.resources import files

    return (
        files("application.services.stakeholder.prompts").joinpath(name).read_text(encoding="utf-8")
    )


async def get_persona_builder_service(
    llm: LLMPort = Depends(get_stakeholder_llm_port),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Construct a PersonaBuilderService for one request (Story 2.5).

    Uses the singleton AgentSkillClient + stakeholder LLM; persistence is via
    a UoW-bound adapter so the builder can save without holding the request
    session open across the entire build.
    """
    from application.services.stakeholder.persona_build_cache import PersonaBuildCache
    from application.services.stakeholder.persona_builder_service import (
        PersonaBuilderService,
    )
    from infrastructure.external.agent_sdk.lifespan import get_agent_sdk_client
    from infrastructure.external.cache.redis_client import (
        _redis_client as _shared_redis,
    )

    agent_client = get_agent_sdk_client()
    repo = _UoWBoundStakeholderPersonaRepo(
        SQLAlchemyUnitOfWork,
        access_scope=persona_access_scope_for(current_user),
    )
    cache = PersonaBuildCache(redis=_shared_redis)
    return PersonaBuilderService(
        agent_client=agent_client,
        llm=llm,
        repo=repo,
        cache=cache,
        adversarialize_prompt=_load_stakeholder_prompt("adversarialize.md"),
        parse_prompt=_load_stakeholder_prompt("persona_markdown_to_json.md"),
    )


# ---------------------------------------------------------------------------
# Persona V2 editor dependencies (Story 2.7)
# ---------------------------------------------------------------------------


def get_persona_v2_service():
    """Construct a PersonaV2Service for one request (Story 2.7).

    Takes the SQLAlchemy UoW class as its own factory so the service can open
    and close a session per call.
    """
    from application.services.stakeholder.persona_v2_service import PersonaV2Service

    return PersonaV2Service(uow_factory=SQLAlchemyUnitOfWork)


def get_persona_asset_service():
    """Persisted Persona asset lifecycle; markdown templates are excluded."""
    from application.services.stakeholder.persona_asset_service import PersonaAssetService

    return PersonaAssetService(uow_factory=SQLAlchemyUnitOfWork)


# ---------------------------------------------------------------------------
# Defense Prep dependencies
# ---------------------------------------------------------------------------


async def get_defense_prep_service(
    loader: PersonaLoader = Depends(get_persona_loader_with_v2),
    llm: LLMPort = Depends(get_stakeholder_llm_port),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
):
    from application.services.defense_prep_service import DefensePrepService
    from application.services.defense_training_workspace_service import (
        DefenseTrainingWorkspaceService,
    )
    from application.services.training_studio.session_service import TrainingSessionService
    from infrastructure.external.document_parser.parser import FileDocumentParser
    from infrastructure.adapters.training_conversation import (
        ConversationTrainingConversationAdapter,
    )

    return DefensePrepService(
        uow_factory=SQLAlchemyUnitOfWork,
        llm=llm,
        document_parser=FileDocumentParser(),
        chatroom_service=chatroom_svc,
        persona_loader=loader,
        training_workspace_service=DefenseTrainingWorkspaceService(
            session_service=TrainingSessionService(uow_factory=SQLAlchemyUnitOfWork),
            conversation_adapter=ConversationTrainingConversationAdapter(
                SQLAlchemyUnitOfWork
            ),
        ),
    )
