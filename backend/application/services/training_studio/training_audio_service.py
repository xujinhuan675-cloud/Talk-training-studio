"""Persist and resolve AI audio for authenticated training messages."""

from __future__ import annotations

import hashlib
import logging
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Callable

from application.ports.storage import StoragePort
from application.ports.turn_based_voice import (
    TurnBasedVoicePipelinePort,
    TurnBasedVoiceSynthesisConfig,
)
from application.services.file_asset_service import FileAssetApplicationService
from application.services.stakeholder.dto import MessageDTO
from application.services.training_studio.message_presentation import (
    strip_emotion_markers,
    strip_parenthetical_cues_for_speech,
)
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.conversation.repository import OwnedMetadataScope

logger = logging.getLogger(__name__)

_AUDIO_METADATA_KEY = "aiAudio"
_PCM_MIME_TYPES = {"audio/l16", "audio/pcm", "audio/pcm16", "audio/s16le"}
_SUPPORTED_TRAINING_MODES = {"realtime", "realtime_voice", "video", "voice"}


@dataclass(frozen=True)
class TrainingAudioContext:
    training_session_id: str
    room_id: int
    user_id: str
    team_id: str | None = None
    can_manage_team: bool = False
    training_mode: str = "voice"
    voice_id: str | None = None
    voice_speed: float = 1.0
    voice_volume: float = 1.0
    style_instruction: str | None = None

    @property
    def enabled(self) -> bool:
        return self.training_mode.strip().lower() in _SUPPORTED_TRAINING_MODES

    @property
    def metadata_scope(self) -> OwnedMetadataScope:
        return OwnedMetadataScope(
            user_id=self.user_id,
            team_id=self.team_id,
            include_team_scope=self.can_manage_team,
            allow_unscoped=False,
        )


@dataclass(frozen=True)
class TrainingAudioSegment:
    data: bytes
    mime_type: str
    sequence: int | None = None
    sentence_index: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    runtime: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class TrainingAudioDownload:
    key: str
    mime_type: str
    size: int


class TrainingAudioService:
    """Store private audio objects and bind them to one persisted AI message."""

    def __init__(
        self,
        *,
        uow_factory: Callable[..., AbstractUnitOfWork],
        storage: StoragePort,
        file_assets: FileAssetApplicationService,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage = storage
        self._file_assets = file_assets

    async def attach_audio(
        self,
        message_id: int,
        *,
        context: TrainingAudioContext,
        segments: list[TrainingAudioSegment],
        runtime: str | None = None,
        provider: str | None = None,
        original: bool = True,
        provenance: str | None = None,
    ) -> MessageDTO | None:
        if not context.enabled:
            return None

        normalized = [self._normalize_segment(segment) for segment in segments if segment.data]
        if not normalized:
            return None

        stored_segments: list[dict[str, object]] = []
        stored_asset_ids: list[int] = []
        uploaded_keys: list[str] = []
        try:
            for index, segment in enumerate(normalized):
                extension = _audio_extension(segment.mime_type)
                key = f"{_storage_prefix(context, message_id)}/" f"{index:03d}{extension}"
                object_metadata = {
                    "trainingSessionId": context.training_session_id,
                    "roomId": str(context.room_id),
                    "messageId": str(message_id),
                    "segmentIndex": str(index),
                    "originalAiAudio": str(original).lower(),
                    "audioProvenance": provenance
                    or ("generated_for_message" if original else "server_resynthesis"),
                }
                outcome = await self._storage.upload(
                    segment.data,
                    key,
                    metadata=object_metadata,
                    content_type=segment.mime_type,
                )
                uploaded_keys.append(key)
                info = self._storage.info()
                asset = await self._file_assets.upsert_active_asset(
                    owner_id=_optional_int(context.user_id),
                    storage_type=info.type,
                    bucket=info.bucket,
                    region=info.region,
                    key=key,
                    original_filename=f"ai-reply-{message_id}-{index}{extension}",
                    content_type=segment.mime_type,
                    kind="training_ai_audio",
                    size=outcome.size or len(segment.data),
                    etag=outcome.etag,
                    url=None,
                    metadata={
                        **object_metadata,
                        "trainingMode": context.training_mode,
                        **({"runtime": runtime} if runtime else {}),
                        **({"provider": provider} if provider else {}),
                    },
                    metadata_scope=context.metadata_scope,
                )
                stored_asset_ids.append(asset.id)
                stored_segments.append(
                    {
                        "index": index,
                        "mimeType": segment.mime_type,
                        "size": outcome.size or len(segment.data),
                        **({"sequence": segment.sequence} if segment.sequence is not None else {}),
                        **(
                            {"sentenceIndex": segment.sentence_index}
                            if segment.sentence_index is not None
                            else {}
                        ),
                    }
                )

            manifest: dict[str, object] = {
                "available": True,
                "original": original,
                "provenance": provenance
                or ("generated_for_message" if original else "server_resynthesis"),
                "schemaVersion": 1,
                "segmentCount": len(stored_segments),
                "segments": stored_segments,
                "messageId": message_id,
                "roomId": context.room_id,
                "trainingSessionId": context.training_session_id,
                "trainingMode": context.training_mode,
                **({"runtime": runtime} if runtime else {}),
                **({"provider": provider} if provider else {}),
            }
            async with self._uow_factory() as uow:
                message = await uow.stakeholder_message_repository.get_by_id(
                    message_id,
                    room_id=context.room_id,
                )
                if message is None or message.sender_type != "persona":
                    raise ValueError("AI audio target message was not found")
                metadata = dict(message.metadata or {})
                metadata[_AUDIO_METADATA_KEY] = manifest
                updated = await uow.stakeholder_message_repository.update_metadata(
                    message_id,
                    room_id=context.room_id,
                    metadata=metadata,
                )
                if updated is None:
                    raise ValueError("AI audio target message was not found")
                return MessageDTO.model_validate(updated)
        except Exception:
            logger.exception(
                "Failed to persist AI audio for training message %s",
                message_id,
            )
            for key in uploaded_keys:
                try:
                    await self._storage.delete(key)
                except Exception:
                    logger.warning("Failed to clean orphaned training audio object %s", key)
            for asset_id in stored_asset_ids:
                try:
                    await self._file_assets.delete_record_by_id(
                        asset_id,
                        metadata_scope=context.metadata_scope,
                    )
                except Exception:
                    logger.warning("Failed to clean orphaned training audio asset %s", asset_id)
            return None

    async def synthesize_and_attach(
        self,
        message_id: int,
        *,
        context: TrainingAudioContext,
        voice_pipeline: TurnBasedVoicePipelinePort,
        original: bool,
    ) -> MessageDTO | None:
        async with self._uow_factory(readonly=True) as uow:
            message = await uow.stakeholder_message_repository.get_by_id(
                message_id,
                room_id=context.room_id,
            )
            if message is None or message.sender_type != "persona":
                return None
            metadata = dict(message.metadata or {})
            if str(metadata.get("trainingSessionId") or "") != context.training_session_id:
                return None
            if not original:
                if str(metadata.get("trainingMode") or "").strip().lower() != "voice":
                    return None
                event_kind = str(metadata.get("eventKind") or "").strip()
                source = str(metadata.get("source") or "").strip()
                if event_kind != "scenario_opening" and source not in {
                    "training_opening_message",
                    "scenario_training_opening",
                }:
                    return None
            if audio_manifest(metadata) is not None:
                return MessageDTO.model_validate(message)
            content = strip_parenthetical_cues_for_speech(
                strip_emotion_markers(message.content)
            )
            persona_id = message.sender_id or "training_customer"

        segments: list[TrainingAudioSegment] = []
        config = TurnBasedVoiceSynthesisConfig(
            persona_id=persona_id,
            voice_id=str(
                metadata.get("trainingVoiceId")
                or metadata.get("training_voice_id")
                or context.voice_id
                or ""
            ).strip(),
            voice_speed=context.voice_speed,
            voice_volume=context.voice_volume,
            style_instruction=context.style_instruction,
            metadata={
                "trainingSessionId": context.training_session_id,
                "roomId": context.room_id,
                "messageId": message_id,
                "audioProvenance": (
                    "generated_for_message" if original else "server_resynthesis"
                ),
            },
        )
        async for output in voice_pipeline.synthesize_stream(content, config):
            segments.append(
                TrainingAudioSegment(
                    data=output.data,
                    mime_type=output.mime_type or "audio/mpeg",
                    sequence=output.sequence,
                    sample_rate=output.sample_rate,
                    channels=output.channels,
                    runtime=output.runtime,
                    provider=output.provider,
                )
            )
        if not segments:
            return None
        return await self.attach_audio(
            message_id,
            context=context,
            segments=segments,
            runtime=segments[0].runtime,
            provider=segments[0].provider,
            original=original,
            provenance="generated_for_message" if original else "server_resynthesis",
        )

    async def get_manifest(
        self,
        message_id: int,
        *,
        context: TrainingAudioContext,
    ) -> dict[str, object] | None:
        message = await self._message_for_context(message_id, context=context)
        manifest = audio_manifest(message.metadata if message else None)
        if manifest is None:
            return None
        segments = manifest.get("segments")
        public_segments = []
        if isinstance(segments, list):
            for item in segments:
                if not isinstance(item, dict):
                    continue
                index = _optional_int(item.get("index"))
                if index is None:
                    continue
                public_segments.append(
                    {
                        "index": index,
                        "mimeType": str(item.get("mimeType") or "application/octet-stream"),
                        "size": _optional_int(item.get("size")) or 0,
                    }
                )
        return {
            "available": True,
            "original": manifest.get("original") is True,
            "provenance": str(manifest.get("provenance") or ""),
            "messageId": message_id,
            "roomId": context.room_id,
            "trainingSessionId": context.training_session_id,
            "segmentCount": len(public_segments),
            "segments": public_segments,
        }

    async def get_segment(
        self,
        message_id: int,
        segment_index: int,
        *,
        context: TrainingAudioContext,
    ) -> TrainingAudioDownload | None:
        message = await self._message_for_context(message_id, context=context)
        segment = audio_manifest_segment(
            message.metadata if message else None,
            segment_index,
        )
        if segment is None:
            return None
        mime_type = str(segment.get("mimeType") or "application/octet-stream")
        key = (
            f"{_storage_prefix(context, message_id)}/"
            f"{segment_index:03d}{_audio_extension(mime_type)}"
        )
        try:
            asset = await self._file_assets.get_asset_by_key_raw(
                key,
                metadata_scope=context.metadata_scope,
            )
        except Exception:
            return None
        metadata = dict(asset.metadata or {})
        manifest = audio_manifest(message.metadata if message else None) or {}
        expected_original = str(manifest.get("original") is True).lower()
        if (
            str(metadata.get("trainingSessionId") or "") != context.training_session_id
            or str(metadata.get("roomId") or "") != str(context.room_id)
            or str(metadata.get("messageId") or "") != str(message_id)
            or str(metadata.get("segmentIndex") or "") != str(segment_index)
            or str(metadata.get("originalAiAudio") or "").lower() != expected_original
            or str(metadata.get("audioProvenance") or "")
            != str(manifest.get("provenance") or "")
        ):
            return None
        return TrainingAudioDownload(
            key=asset.key,
            mime_type=asset.content_type or "application/octet-stream",
            size=int(asset.size or 0),
        )

    def stream_segment(self, download: TrainingAudioDownload) -> AsyncIterator[bytes]:
        return self._storage.stream_download(download.key)

    async def _message_for_context(
        self,
        message_id: int,
        *,
        context: TrainingAudioContext,
    ):
        async with self._uow_factory(readonly=True) as uow:
            message = await uow.stakeholder_message_repository.get_by_id(
                message_id,
                room_id=context.room_id,
            )
            if message is None or message.sender_type != "persona":
                return None
            manifest = audio_manifest(message.metadata)
            if manifest is None:
                return None
            if (
                str(manifest.get("trainingSessionId") or "") != context.training_session_id
                or str(manifest.get("roomId") or "") != str(context.room_id)
                or str(manifest.get("messageId") or "") != str(message_id)
            ):
                return None
            return message

    @staticmethod
    def _normalize_segment(segment: TrainingAudioSegment) -> TrainingAudioSegment:
        mime_type = (segment.mime_type or "application/octet-stream").split(";", 1)[0].lower()
        if mime_type not in _PCM_MIME_TYPES:
            return TrainingAudioSegment(
                data=segment.data,
                mime_type=mime_type,
                sequence=segment.sequence,
                sentence_index=segment.sentence_index,
                sample_rate=segment.sample_rate,
                channels=segment.channels,
                runtime=segment.runtime,
                provider=segment.provider,
            )
        channels = max(1, segment.channels or 1)
        sample_rate = max(8000, segment.sample_rate or 24000)
        return TrainingAudioSegment(
            data=_pcm16_to_wav(segment.data, sample_rate=sample_rate, channels=channels),
            mime_type="audio/wav",
            sequence=segment.sequence,
            sentence_index=segment.sentence_index,
            sample_rate=sample_rate,
            channels=channels,
            runtime=segment.runtime,
            provider=segment.provider,
        )


def audio_manifest(metadata: dict[str, object] | None) -> dict[str, object] | None:
    value = (metadata or {}).get(_AUDIO_METADATA_KEY)
    if not isinstance(value, dict) or value.get("available") is not True:
        return None
    return value


def audio_manifest_segment(
    metadata: dict[str, object] | None,
    segment_index: int,
) -> dict[str, object] | None:
    manifest = audio_manifest(metadata)
    segments = manifest.get("segments") if manifest else None
    if not isinstance(segments, list) or segment_index < 0 or segment_index >= len(segments):
        return None
    segment = segments[segment_index]
    return segment if isinstance(segment, dict) else None


def _pcm16_to_wav(data: bytes, *, sample_rate: int, channels: int) -> bytes:
    byte_rate = sample_rate * channels * 2
    block_align = channels * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        len(data),
    )
    return header + data


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _audio_extension(mime_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/opus": ".opus",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
    }.get(mime_type, ".audio")


def _storage_prefix(context: TrainingAudioContext, message_id: int) -> str:
    binding = (f"{context.training_session_id}\0{context.room_id}\0{message_id}").encode("utf-8")
    digest = hashlib.sha256(binding).hexdigest()
    return f"training-ai-audio/{digest[:2]}/{digest}"
