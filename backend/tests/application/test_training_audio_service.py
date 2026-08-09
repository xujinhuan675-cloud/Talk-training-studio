from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.services.training_studio.training_audio_service import (
    TrainingAudioContext,
    TrainingAudioSegment,
    TrainingAudioService,
)
from domain.stakeholder.entity import Message


_HISTORICAL_AUDIO_RESYNTHESIS_NOTICE = (
    "历史音频已按当前语音配置重新合成并保存，不是此前播放的原始音频。"
)


def test_normalize_segment_uses_container_magic_over_declared_pcm() -> None:
    ogg_audio = b"OggS\x00\x02" + b"\x00" * 22 + b"OpusHead"

    normalized = TrainingAudioService._normalize_segment(
        TrainingAudioSegment(
            data=ogg_audio,
            mime_type="audio/pcm",
            sample_rate=24000,
            channels=1,
        )
    )

    assert normalized.mime_type == "audio/ogg"
    assert normalized.data == ogg_audio


def test_normalize_segment_wraps_actual_raw_pcm_as_wav() -> None:
    normalized = TrainingAudioService._normalize_segment(
        TrainingAudioSegment(
            data=b"\x00\x00\x01\x00",
            mime_type="audio/pcm",
            sample_rate=24000,
            channels=1,
        )
    )

    assert normalized.mime_type == "audio/wav"
    assert normalized.data.startswith(b"RIFF")
    assert normalized.data[8:12] == b"WAVE"


class _MessageRepository:
    def __init__(self, message: Message) -> None:
        self.message = message

    async def get_by_id(self, message_id: int, *, room_id: int | None = None):
        if self.message.id != message_id:
            return None
        if room_id is not None and self.message.room_id != room_id:
            return None
        return self.message

    async def update_metadata(self, message_id: int, *, room_id: int, metadata: dict):
        message = await self.get_by_id(message_id, room_id=room_id)
        if message is None:
            return None
        message.metadata = dict(metadata)
        return message


class _UnitOfWork:
    def __init__(self, repository: _MessageRepository) -> None:
        self.stakeholder_message_repository = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _Storage:
    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.objects: dict[str, bytes] = {}

    def info(self):
        return SimpleNamespace(type="local", bucket=None, region=None)

    async def upload(self, data, key, metadata=None, content_type=None):
        self.uploads.append(
            {
                "data": data,
                "key": key,
                "metadata": metadata,
                "content_type": content_type,
            }
        )
        self.objects[key] = data
        return SimpleNamespace(
            key=key,
            etag="etag",
            size=len(data),
            content_type=content_type,
            url=None,
        )

    async def delete(self, key):
        self.objects.pop(key, None)
        return True

    async def stream_download(self, key, chunk_size=8192):
        yield self.objects[key]


class _FileAssets:
    def __init__(self) -> None:
        self.assets: dict[int, SimpleNamespace] = {}
        self.scopes = []

    async def upsert_active_asset(self, **kwargs):
        asset_id = len(self.assets) + 1
        metadata = {
            **dict(kwargs.get("metadata") or {}),
            "ownerUserId": kwargs["metadata_scope"].user_id,
        }
        asset = SimpleNamespace(
            id=asset_id,
            key=kwargs["key"],
            size=kwargs["size"],
            content_type=kwargs["content_type"],
            metadata=metadata,
        )
        self.assets[asset_id] = asset
        self.scopes.append(kwargs["metadata_scope"])
        return asset

    async def get_asset_raw(self, asset_id, *, metadata_scope):
        self.scopes.append(metadata_scope)
        asset = self.assets.get(asset_id)
        if asset is None or asset.metadata.get("ownerUserId") != metadata_scope.user_id:
            raise ValueError("not found")
        return asset

    async def get_asset_by_key_raw(self, key, *, metadata_scope):
        self.scopes.append(metadata_scope)
        for asset in self.assets.values():
            if asset.key == key and asset.metadata.get("ownerUserId") == metadata_scope.user_id:
                return asset
        raise ValueError("not found")

    async def delete_record_by_id(self, asset_id, *, metadata_scope):
        self.assets.pop(asset_id, None)


class _VoicePipeline:
    def __init__(self) -> None:
        self.configs = []
        self.texts = []

    async def synthesize_stream(self, text, config):
        self.configs.append(config)
        self.texts.append(text)
        yield SimpleNamespace(
            data=b"voice",
            mime_type="audio/mpeg",
            sequence=0,
            sample_rate=None,
            channels=None,
            runtime="pipecat",
            provider="pipecat",
        )


def _service(message: Message):
    repository = _MessageRepository(message)
    storage = _Storage()
    assets = _FileAssets()
    service = TrainingAudioService(
        uow_factory=lambda **_: _UnitOfWork(repository),
        storage=storage,
        file_assets=assets,
    )
    return service, storage, assets


@pytest.mark.asyncio
async def test_persists_pcm_as_private_wav_and_hides_asset_identity_from_manifest():
    message = Message(
        id=7,
        room_id=42,
        sender_type="persona",
        sender_id="salesperson",
        content="Hello",
    )
    service, storage, assets = _service(message)
    context = TrainingAudioContext(
        training_session_id="session-1",
        room_id=42,
        user_id="101",
        team_id="team-9",
        training_mode="realtime_voice",
    )

    attached = await service.attach_audio(
        7,
        context=context,
        segments=[
            TrainingAudioSegment(
                data=b"\x01\x00\x02\x00",
                mime_type="audio/pcm",
                sample_rate=24000,
                channels=1,
                runtime="pipecat",
                provider="openai",
            )
        ],
        runtime="pipecat",
        provider="openai",
    )

    assert attached is not None
    assert storage.uploads[0]["content_type"] == "audio/wav"
    assert storage.uploads[0]["data"].startswith(b"RIFF")
    assert assets.scopes[0].user_id == "101"
    assert message.metadata["aiAudio"]["trainingSessionId"] == "session-1"

    manifest = await service.get_manifest(7, context=context)
    assert manifest == {
        "available": True,
        "original": True,
        "provenance": "generated_for_message",
        "messageId": 7,
        "roomId": 42,
        "trainingSessionId": "session-1",
        "segmentCount": 1,
        "segments": [{"index": 0, "mimeType": "audio/wav", "size": 48}],
    }
    assert "assetId" not in manifest["segments"][0]

    download = await service.get_segment(7, 0, context=context)
    assert download is not None
    assert download.mime_type == "audio/wav"

    wrong_session = TrainingAudioContext(
        training_session_id="session-2",
        room_id=42,
        user_id="101",
        training_mode="voice",
    )
    assert await service.get_manifest(7, context=wrong_session) is None


@pytest.mark.asyncio
async def test_text_mode_does_not_persist_or_expose_audio():
    message = Message(
        id=8,
        room_id=42,
        sender_type="persona",
        sender_id="salesperson",
        content="Text only",
    )
    service, storage, _ = _service(message)
    context = TrainingAudioContext(
        training_session_id="session-1",
        room_id=42,
        user_id="101",
        training_mode="text",
    )

    assert (
        await service.attach_audio(
            8,
            context=context,
            segments=[TrainingAudioSegment(data=b"audio", mime_type="audio/mpeg")],
        )
        is None
    )
    assert storage.uploads == []
    assert message.metadata == {}


@pytest.mark.asyncio
async def test_historical_server_resynthesis_is_persisted_but_never_marked_original():
    message = Message(
        id=9,
        room_id=42,
        sender_type="persona",
        sender_id="salesperson",
        content="（皱眉）Historical opening",
        metadata={
            "trainingSessionId": "session-1",
            "trainingMode": "voice",
            "eventKind": "scenario_opening",
            "trainingVoiceId": "zh_female_vv_uranus_bigtts",
        },
    )
    service, _, _ = _service(message)
    context = TrainingAudioContext(
        training_session_id="session-1",
        room_id=42,
        user_id="101",
        training_mode="voice",
        tts_provider="openai",
        tts_model="gpt-4o-mini-tts",
    )

    pipeline = _VoicePipeline()
    attached = await service.synthesize_and_attach(
        9,
        context=context,
        voice_pipeline=pipeline,
        original=False,
    )

    assert attached is not None
    manifest = await service.get_manifest(9, context=context)
    assert manifest is not None
    assert manifest["original"] is False
    assert manifest["provenance"] == "server_resynthesis"
    assert pipeline.configs[0].voice_id == "zh_female_vv_uranus_bigtts"
    assert pipeline.configs[0].tts_provider == "openai"
    assert pipeline.configs[0].tts_model == "gpt-4o-mini-tts"
    assert pipeline.texts == ["Historical opening"]
    assert _HISTORICAL_AUDIO_RESYNTHESIS_NOTICE not in pipeline.texts


@pytest.mark.asyncio
async def test_route_voice_overrides_legacy_message_voice_for_resynthesis():
    message = Message(
        id=10,
        room_id=42,
        sender_type="persona",
        sender_id="salesperson",
        content="Welcome",
        metadata={
            "trainingSessionId": "session-1",
            "trainingMode": "voice",
            "eventKind": "scenario_opening",
            "trainingVoiceId": "zh_female_vv_uranus_bigtts",
        },
    )
    service, _, _ = _service(message)
    pipeline = _VoicePipeline()

    attached = await service.synthesize_and_attach(
        10,
        context=TrainingAudioContext(
            training_session_id="session-1",
            room_id=42,
            user_id="101",
            training_mode="voice",
            voice_id="marin",
            tts_provider="openai",
            tts_model="gpt-4o-mini-tts",
        ),
        voice_pipeline=pipeline,
        original=False,
    )

    assert attached is not None
    assert pipeline.configs[0].voice_id == "marin"
    assert pipeline.configs[0].tts_provider == "openai"
    assert pipeline.configs[0].tts_model == "gpt-4o-mini-tts"


@pytest.mark.asyncio
async def test_historical_server_resynthesis_rejects_non_voice_openings():
    message = Message(
        id=7,
        room_id=42,
        sender_type="persona",
        sender_id="persona-1",
        content="Welcome",
        metadata={
            "trainingSessionId": "session-1",
            "trainingMode": "video",
            "eventKind": "scenario_opening",
        },
    )
    service, _, _ = _service(message)
    context = TrainingAudioContext(
        training_session_id="session-1",
        room_id=42,
        user_id="101",
        training_mode="video",
    )

    attached = await service.synthesize_and_attach(
        7,
        context=context,
        voice_pipeline=_VoicePipeline(),
        original=False,
    )

    assert attached is None
