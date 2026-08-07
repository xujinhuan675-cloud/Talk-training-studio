from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.ports.stt import TranscriptionResult
from application.services.training_studio.live_assist_service import (
    LiveAssistError,
    LiveAssistService,
    decode_audio_base64,
    normalize_live_assist_speaker,
)
from application.services.training_studio.live_guidance_service import (
    TrainingLiveGuidanceService,
    TranscriptSpeaker,
)
from domain.training_studio.session import TrainingSessionStatus
from domain.training_studio.session_repository import TrainingSessionAccessScope


class _FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    async def transcribe(self, audio: bytes, *, language: str = "zh", audio_format: str = "webm"):
        self.calls.append({"audio": audio, "language": language, "audio_format": audio_format})
        return TranscriptionResult(text=self.text, language=language)


class _FakeSessionService:
    def __init__(self, session) -> None:
        self.session = session
        self.scopes: list[TrainingSessionAccessScope] = []
        self.metadata: list[dict[str, object]] = []

    async def get_session(self, session_id: str, *, access_scope: TrainingSessionAccessScope):
        self.scopes.append(access_scope)
        return self.session

    async def record_session_metadata(self, session_id: str, *, metadata, access_scope):
        self.scopes.append(access_scope)
        self.metadata.append(dict(metadata))
        self.session.task_config.metadata.update(metadata)
        return self.session


def _session(*, status=TrainingSessionStatus.ACTIVE, metadata=None):
    config = SimpleNamespace(
        role="Account Executive",
        level="senior",
        tech_stack=["discovery"],
        category="sales",
        framework="star",
        rubric_weights={"substance": 0.5, "structure": 0.5},
        metadata=dict(metadata or {}),
    )
    return SimpleNamespace(session_id="session-1", status=status, task_config=config)


def test_speaker_resolution_prefers_explicit_hint_then_capture_source() -> None:
    assert normalize_live_assist_speaker(speaker_source="system", speaker_hint="me") == TranscriptSpeaker.USER
    assert normalize_live_assist_speaker(speaker_source="microphone", speaker_hint="remote") == TranscriptSpeaker.COUNTERPART
    assert normalize_live_assist_speaker(speaker_source="system", speaker_hint=None) == TranscriptSpeaker.COUNTERPART
    assert normalize_live_assist_speaker(speaker_source="mixed", speaker_hint=None) == TranscriptSpeaker.USER


@pytest.mark.asyncio
async def test_process_turn_transcribes_normalizes_persists_and_generates_guidance() -> None:
    session = _session()
    sessions = _FakeSessionService(session)
    stt = _FakeSTT("We are worried about the cost.")
    service = LiveAssistService(stt=stt, guidance=TrainingLiveGuidanceService())
    scope = TrainingSessionAccessScope(user_id="user-1", team_id="team-1")

    result = await service.process_turn(
        "session-1",
        user_id="user-1",
        session_service=sessions,
        access_scope=scope,
        audio=b"pcm",
        audio_format="wav",
        language="en",
        speaker_source="system",
        client_metadata={"callId": "call-1"},
    )

    assert stt.calls == [{"audio": b"pcm", "language": "en", "audio_format": "wav"}]
    assert result["turn"]["speaker"] == "counterpart"
    assert result["turn"]["text"] == "We are worried about the cost."
    assert result["turn"]["metadata"]["transcribed"] is True
    assert any(event["event_type"] == "risk" for event in result["guidance"])
    assert result["transcript_turn_count"] == 1
    assert sessions.scopes == [scope, scope]
    persisted = sessions.metadata[0]["liveAssist"]
    assert persisted["schemaVersion"] == 1
    assert persisted["turns"][0]["speaker"] == "counterpart"


@pytest.mark.asyncio
async def test_process_turn_reuses_bounded_transcript_and_accepts_text_without_stt() -> None:
    session = _session(
        metadata={
            "liveAssist": {
                "turns": [
                    {"speaker": "counterpart", "text": "What is the goal?", "turn_id": "old"}
                ]
            }
        }
    )
    sessions = _FakeSessionService(session)
    stt = _FakeSTT("must not be called")
    service = LiveAssistService(stt=stt, guidance=TrainingLiveGuidanceService(), max_turns=2)

    result = await service.process_turn(
        "session-1",
        user_id="user-1",
        session_service=sessions,
        access_scope=TrainingSessionAccessScope(user_id="user-1"),
        text="I will start with the outcome.",
        speaker_source="microphone",
    )

    assert stt.calls == []
    assert result["transcript_turn_count"] == 2
    assert [turn["speaker"] for turn in sessions.metadata[0]["liveAssist"]["turns"]] == [
        "counterpart",
        "user",
    ]


@pytest.mark.asyncio
async def test_process_turn_rejects_inactive_session_and_missing_input() -> None:
    inactive = _FakeSessionService(_session(status=TrainingSessionStatus.COMPLETED))
    service = LiveAssistService(stt=None, guidance=TrainingLiveGuidanceService())
    with pytest.raises(LiveAssistError) as inactive_error:
        await service.process_turn(
            "session-1",
            user_id="user-1",
            session_service=inactive,
            access_scope=TrainingSessionAccessScope(user_id="user-1"),
        )
    assert inactive_error.value.code == "training_session_not_active"

    active = _FakeSessionService(_session())
    with pytest.raises(LiveAssistError) as input_error:
        await service.process_turn(
            "session-1",
            user_id="user-1",
            session_service=active,
            access_scope=TrainingSessionAccessScope(user_id="user-1"),
        )
    assert input_error.value.code == "turn_input_required"


def test_decode_audio_base64_accepts_data_url_and_rejects_invalid_payload() -> None:
    assert decode_audio_base64("data:audio/webm;base64,YWJj") == b"abc"
    with pytest.raises(LiveAssistError) as error:
        decode_audio_base64("not base64")
    assert error.value.code == "invalid_audio"
