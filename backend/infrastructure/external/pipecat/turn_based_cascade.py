"""Pipecat cascade adapter for turn-based voice synthesis."""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import logging
import wave
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from typing import Any

from application.ports.realtime import (
    REALTIME_RUNTIME_PIPECAT,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    RealtimeOutputAudio,
    TrainingVoiceContext,
    sanitize_realtime_public_value,
)
from application.ports.tts import TTSConfig, TTSPort
from application.ports.turn_based_voice import TurnBasedVoiceSynthesisConfig
from infrastructure.external.pipecat.realtime_pipeline import (
    PipecatRuntime,
    build_pipecat_pipeline_handle,
    build_pipecat_voice_processors,
    import_pipecat_runtime,
)

_PIPECAT_PROVIDER = "pipecat"
_PIPECAT_CASCADE_PROFILE = "cascade"
_PIPECAT_NATIVE_FRAME_RUNTIME = "pipecat_native_frame_processor"
_TURN_BASED_TRANSPORT = "talkwise.audio_chunks"
_OPENAI_TTS_PROVIDERS = {"openai", "openai_tts"}
_DEFAULT_NATIVE_OUTPUT_SAMPLE_RATE = 24000
_DEFAULT_NATIVE_OUTPUT_CHANNELS = 1
_DEFAULT_NATIVE_TIMEOUT_SECONDS = 30.0
_DEFAULT_NATIVE_IDLE_TIMEOUT_SECONDS = 0.25
_NATIVE_RUNNER_CLOSE_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)


class PipecatTurnBasedCascadePipeline:
    """Small cascade pipeline that adapts current TTS providers to Pipecat events.

    This keeps the existing turn-based SSE contract while moving the application
    boundary from direct provider calls to Pipecat-style cascade audio output.
    """

    def __init__(
        self,
        tts: TTSPort | None = None,
        *,
        tts_provider: str | None = None,
        tts_model: str | None = None,
        tts_api_key: str | None = None,
        tts_base_url: str | None = None,
        output_mime_type: str = "audio/mpeg",
        native_runtime: PipecatRuntime | None = None,
        native_timeout_seconds: float = _DEFAULT_NATIVE_TIMEOUT_SECONDS,
        native_idle_timeout_seconds: float = _DEFAULT_NATIVE_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._tts = tts
        self._tts_provider = _clean_text(tts_provider)
        self._tts_model = _clean_text(tts_model)
        self._tts_api_key = _clean_text(tts_api_key)
        self._tts_base_url = _clean_text(tts_base_url)
        self._output_mime_type = output_mime_type
        self._native_runtime = native_runtime
        self._native_timeout_seconds = native_timeout_seconds
        self._native_idle_timeout_seconds = native_idle_timeout_seconds

    async def synthesize_stream(
        self,
        text: str,
        config: TurnBasedVoiceSynthesisConfig,
    ) -> AsyncIterator[RealtimeOutputAudio]:
        clean_text = text.strip()
        if not clean_text:
            return

        if self._supports_native_openai_tts(config):
            try:
                native_output = await self._synthesize_with_native_pipecat(clean_text, config)
                if native_output is not None:
                    yield native_output
                    return
            except Exception:
                if self._tts is None:
                    raise
                logger.info(
                    "turn_based_pipecat_native_tts_fallback",
                    extra={
                        "tts_provider": config.tts_provider or self._tts_provider,
                        "tts_model": config.tts_model or self._tts_model,
                    },
                    exc_info=True,
                )

        if self._tts is None:
            return

        async for output in self._synthesize_with_tts_port(clean_text, config):
            yield output

    def _supports_native_openai_tts(self, config: TurnBasedVoiceSynthesisConfig) -> bool:
        provider = _normalize_provider(config.tts_provider or self._tts_provider)
        return provider in _OPENAI_TTS_PROVIDERS

    async def _synthesize_with_tts_port(
        self,
        clean_text: str,
        config: TurnBasedVoiceSynthesisConfig,
    ) -> AsyncIterator[RealtimeOutputAudio]:
        assert self._tts is not None
        audio_parts: list[bytes] = []
        tts_config = TTSConfig(
            voice_id=config.voice_id,
            speed=config.voice_speed,
            volume=config.voice_volume,
            pitch=config.voice_pitch,
            style_instruction=config.style_instruction,
            language=config.language,
        )
        async for audio_bytes in self._tts.synthesize_stream(clean_text, tts_config):
            if audio_bytes:
                audio_parts.append(audio_bytes)

        if not audio_parts:
            return

        yield RealtimeOutputAudio(
            data=b"".join(audio_parts),
            provider=_PIPECAT_PROVIDER,
            runtime=REALTIME_RUNTIME_PIPECAT,
            mime_type=config.output_mime_type or self._output_mime_type,
            sequence=config.audio_sequence,
            context_id=_context_id(config),
            metadata=_audio_metadata(
                config,
                tts_provider=self._tts_provider,
                tts_model=self._tts_model,
            ),
        )

    async def _synthesize_with_native_pipecat(
        self,
        clean_text: str,
        config: TurnBasedVoiceSynthesisConfig,
    ) -> RealtimeOutputAudio | None:
        runtime = self._native_runtime or import_pipecat_runtime()
        realtime_config = self._native_realtime_config(config)
        context = _native_context(config)
        processors = build_pipecat_voice_processors(runtime, realtime_config, context=context)
        handle = build_pipecat_pipeline_handle(
            runtime=runtime,
            context=context,
            config=realtime_config,
            processors=processors,
            websocket=None,
        )
        await handle.runner.add_workers(handle.worker)
        handle.run_task = asyncio.create_task(
            handle.runner.run(),
            name="talkwise-pipecat-turn-based-tts",
        )
        try:
            await handle.worker.queue_frame(_text_frame(runtime, clean_text))
            if hasattr(handle.worker, "flush_pipeline"):
                await handle.worker.flush_pipeline()
            output = await _collect_native_audio_output(
                handle.event_queue,
                config,
                tts_provider="openai",
                tts_model=config.tts_model or self._tts_model,
                output_mime_type=self._output_mime_type,
                timeout_seconds=self._native_timeout_seconds,
                idle_timeout_seconds=self._native_idle_timeout_seconds,
            )
            _raise_runner_error_if_finished(handle.run_task)
            return output
        finally:
            await _close_pipecat_handle(handle, runtime)

    def _native_realtime_config(self, config: TurnBasedVoiceSynthesisConfig) -> RealtimePipelineConfig:
        tts_config: dict[str, object] = {
            "provider": "openai",
            "speed": config.voice_speed,
        }
        if config.tts_model or self._tts_model:
            tts_config["model"] = config.tts_model or self._tts_model
        if config.voice_id:
            tts_config["voice"] = config.voice_id
        if self._tts_base_url:
            tts_config["baseUrl"] = self._tts_base_url
        output_sample_rate = (
            _metadata_int(config.metadata, "outputSampleRate", "output_sample_rate")
            or _DEFAULT_NATIVE_OUTPUT_SAMPLE_RATE
        )
        metadata: dict[str, object] = {
            "tts": tts_config,
            "outputSampleRate": output_sample_rate,
            "outputMimeType": "audio/pcm",
            "talkwise": _audio_metadata(
                config,
                tts_provider="openai",
                tts_model=config.tts_model or self._tts_model,
                pipeline_runtime=_PIPECAT_NATIVE_FRAME_RUNTIME,
            ),
        }
        if self._tts_api_key:
            metadata["openaiApiKey"] = self._tts_api_key
        return RealtimePipelineConfig(
            provider=_PIPECAT_PROVIDER,
            runtime=REALTIME_RUNTIME_PIPECAT,
            model=config.tts_model or self._tts_model,
            voice=config.voice_id or None,
            output_audio_format="pcm16",
            instructions=config.style_instruction,
            metadata=metadata,
        )


def _audio_metadata(
    config: TurnBasedVoiceSynthesisConfig,
    *,
    tts_provider: str | None,
    tts_model: str | None,
    pipeline_runtime: str | None = None,
) -> dict[str, object]:
    pipeline_metadata: dict[str, object] = {
        "profile": _PIPECAT_CASCADE_PROFILE,
        "mode": "turn_based",
        "transport": _TURN_BASED_TRANSPORT,
    }
    if pipeline_runtime:
        pipeline_metadata["runtime"] = pipeline_runtime
    metadata: dict[str, object] = {
        "source": _PIPECAT_PROVIDER,
        "pipeline": pipeline_metadata,
        "tts": {
            "provider": config.tts_provider or tts_provider,
            "model": config.tts_model or tts_model,
            "voice": config.voice_id,
            "language": config.language,
        },
    }
    safe_input = sanitize_realtime_public_value(dict(config.metadata))
    if isinstance(safe_input, dict):
        for key, value in safe_input.items():
            if key not in metadata:
                metadata[key] = value
    return metadata


def _context_id(config: TurnBasedVoiceSynthesisConfig) -> str | None:
    reply_id = _clean_text(config.metadata.get("replyId"))
    if reply_id is None:
        reply_id = _clean_text(config.metadata.get("reply_id"))
    if reply_id is None:
        return None
    if config.audio_sequence is None:
        return reply_id
    return f"{reply_id}:{config.audio_sequence}"


def _clean_text(value: object | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_provider(value: object | None) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _native_context(config: TurnBasedVoiceSynthesisConfig) -> TrainingVoiceContext:
    metadata: dict[str, object] = {"turnBased": True}
    safe_input = sanitize_realtime_public_value(dict(config.metadata))
    if isinstance(safe_input, dict):
        metadata.update(safe_input)
    metadata.setdefault("personaIds", [config.persona_id])
    metadata.setdefault("personaId", config.persona_id)
    return TrainingVoiceContext(
        binding=RealtimeSessionBinding(
            training_session_id=_context_id(config) or config.persona_id or "turn-based-voice",
            room_id=_metadata_int(config.metadata, "roomId", "room_id") or 0,
        ),
        metadata=metadata,
    )


def _metadata_int(metadata: Mapping[str, object], *keys: str) -> int | None:
    for key in keys:
        if key not in metadata:
            continue
        try:
            value = int(metadata[key])
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _text_frame(runtime: PipecatRuntime, text: str) -> Any:
    try:
        return runtime.TextFrame(text=text)
    except TypeError:
        return runtime.TextFrame(text)


async def _collect_native_audio_output(
    event_queue: asyncio.Queue[Mapping[str, Any]],
    config: TurnBasedVoiceSynthesisConfig,
    *,
    tts_provider: str,
    tts_model: str | None,
    output_mime_type: str,
    timeout_seconds: float,
    idle_timeout_seconds: float,
) -> RealtimeOutputAudio | None:
    audio_parts: list[bytes] = []
    event_metadata: dict[str, object] = {}
    mime_type: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.1, timeout_seconds)

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            if audio_parts:
                break
            raise TimeoutError("Pipecat native turn-based TTS produced no audio before timeout")
        next_timeout = min(
            remaining,
            max(0.05, idle_timeout_seconds) if audio_parts else remaining,
        )
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=next_timeout)
        except TimeoutError:
            if audio_parts:
                break
            raise

        if event.get("type") == "talkwise.pipecat.closed":
            break
        if event.get("type") != "audio.output":
            continue
        audio = _audio_bytes_from_event(event)
        if not audio:
            continue
        audio_parts.append(audio)
        mime_type = _event_text(event, "mimeType", "mime_type") or mime_type
        sample_rate = _event_int(event, "sampleRate", "sample_rate") or sample_rate
        channels = _event_int(event, "channels", "numChannels", "num_channels") or channels
        event_metadata.update(_event_metadata(event))

    if not audio_parts:
        return None

    audio = b"".join(audio_parts)
    resolved_mime_type = _normalize_mime_type(mime_type or output_mime_type)
    if _is_pcm_mime_type(resolved_mime_type):
        sample_rate = sample_rate or _DEFAULT_NATIVE_OUTPUT_SAMPLE_RATE
        channels = channels or _DEFAULT_NATIVE_OUTPUT_CHANNELS
        audio = _wav_from_pcm16(audio, sample_rate=sample_rate, channels=channels)
        resolved_mime_type = "audio/wav"

    metadata = _audio_metadata(
        config,
        tts_provider=tts_provider,
        tts_model=tts_model,
        pipeline_runtime=_PIPECAT_NATIVE_FRAME_RUNTIME,
    )
    for key, value in event_metadata.items():
        if key not in metadata:
            metadata[key] = value

    return RealtimeOutputAudio(
        data=audio,
        provider=_PIPECAT_PROVIDER,
        runtime=REALTIME_RUNTIME_PIPECAT,
        mime_type=resolved_mime_type,
        sequence=config.audio_sequence,
        sample_rate=sample_rate,
        channels=channels,
        context_id=_context_id(config),
        metadata=metadata,
    )


def _audio_bytes_from_event(event: Mapping[str, Any]) -> bytes | None:
    encoded = _event_text(event, "audio")
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None


def _event_text(event: Mapping[str, Any], *keys: str) -> str | None:
    for source in (event, event.get("payload")):
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            text = _clean_text(source.get(key))
            if text is not None:
                return text
    return None


def _event_int(event: Mapping[str, Any], *keys: str) -> int | None:
    for source in (event, event.get("payload")):
        if not isinstance(source, Mapping):
            continue
        value = _metadata_int(source, *keys)
        if value is not None:
            return value
    return None


def _event_metadata(event: Mapping[str, Any]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for source in (event.get("metadata"), _event_payload_metadata(event)):
        safe_value = sanitize_realtime_public_value(source)
        if isinstance(safe_value, Mapping):
            metadata.update(dict(safe_value))
    return metadata


def _event_payload_metadata(event: Mapping[str, Any]) -> object | None:
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        return payload.get("metadata")
    return None


def _normalize_mime_type(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "audio/mpeg"
    if "/" in text:
        return text
    if text in {"pcm", "pcm16", "s16le"}:
        return "audio/pcm"
    if text in {"mp3", "mpeg"}:
        return "audio/mpeg"
    if text in {"wav", "wave"}:
        return "audio/wav"
    return f"audio/{text}"


def _is_pcm_mime_type(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"audio/pcm", "audio/l16", "audio/s16le", "audio/x-pcm"}


def _wav_from_pcm16(audio: bytes, *, sample_rate: int, channels: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(max(1, channels))
        wav_file.setsampwidth(2)
        wav_file.setframerate(max(1, sample_rate))
        wav_file.writeframes(audio)
    return buffer.getvalue()


def _raise_runner_error_if_finished(run_task: asyncio.Task | None) -> None:
    if run_task is None or not run_task.done() or run_task.cancelled():
        return
    exc = run_task.exception()
    if exc is not None:
        raise exc


async def _close_pipecat_handle(handle: Any, runtime: PipecatRuntime) -> None:
    with suppress(Exception):
        if hasattr(handle.worker, "end"):
            await handle.worker.end()
        elif hasattr(handle.worker, "queue_frame"):
            await handle.worker.queue_frame(runtime.EndFrame())

    run_task = getattr(handle, "run_task", None)
    if run_task is None:
        return
    try:
        await asyncio.wait_for(run_task, timeout=_NATIVE_RUNNER_CLOSE_TIMEOUT_SECONDS)
    except TimeoutError:
        run_task.cancel()
        with suppress(asyncio.CancelledError):
            await run_task
    except Exception:
        logger.debug("turn_based_pipecat_native_runner_close_failed", exc_info=True)
