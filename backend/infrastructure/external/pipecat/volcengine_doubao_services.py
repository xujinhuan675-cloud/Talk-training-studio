"""Pipecat STT/TTS services backed by the authenticated Doubao voice relay."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import wave
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from infrastructure.external.newapi_user_gateway import authorization_headers
from infrastructure.external.voice.openai_compatible_stt import normalize_transcriptions_url
from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import NOT_GIVEN, STTSettings, TTSSettings, _NotGiven, assert_given
from pipecat.services.stt_service import STTService, SegmentedSTTService
from pipecat.services.tts_service import TTSService
from pipecat.utils.time import time_now_iso8601

logger = logging.getLogger(__name__)

VOLCENGINE_DOUBAO_PROVIDER = "volcengine.doubao"
DOUBAO_INPUT_SAMPLE_RATE = 16000
DOUBAO_OUTPUT_SAMPLE_RATE = 24000
_DOUBAO_MANUAL_COMMIT_MAX_SECONDS = 90
_SPEECH_PATH = "/audio/speech"
_NEWAPI_USER_AUTH_ERROR_CODES = frozenset(
    {
        "AUTH_SESSION_REVOKED",
        "AUTH_TOKEN_EXPIRED",
        "AUTH_UNAUTHORIZED",
        "AUTH_USER_DISABLED",
        "AUTH_USER_INVALID",
    }
)

_TranscribeRequest = Callable[[bytes, str, str], Awaitable[str]]


class DoubaoVoiceServiceError(RuntimeError):
    """Secret-free provider error that survives Pipecat ErrorFrame adaptation."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        category: str,
        phase: str,
        feature: str,
        retryable: bool,
        fatal: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category
        self.phase = phase
        self.feature = feature
        self.retryable = retryable
        self.fatal = fatal
        self.status_code = status_code

    def to_realtime_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
            "provider": VOLCENGINE_DOUBAO_PROVIDER,
            "feature": self.feature,
            "errorCategory": self.category,
            "retryable": self.retryable,
            "fatal": self.fatal,
        }
        if self.status_code is not None:
            payload["statusCode"] = self.status_code
        return payload


def classify_doubao_voice_error(
    error: BaseException | None = None,
    *,
    status_code: int | None = None,
    gateway_error_code: str | None = None,
    feature: str,
) -> DoubaoVoiceServiceError:
    """Classify gateway/provider failures without retaining response bodies or credentials."""

    if str(gateway_error_code or "").strip().upper() in _NEWAPI_USER_AUTH_ERROR_CODES:
        return DoubaoVoiceServiceError(
            "TalkWise session authentication expired",
            code="TALKWISE_SESSION_AUTHENTICATION_FAILED",
            category="authentication",
            phase="gateway_authentication",
            feature=feature,
            retryable=True,
            fatal=True,
            status_code=status_code,
        )
    if status_code in {401, 403}:
        return DoubaoVoiceServiceError(
            "Doubao voice authentication failed",
            code="DOUBAO_VOICE_AUTHENTICATION_FAILED",
            category="authentication",
            phase="provider_request",
            feature=feature,
            retryable=False,
            fatal=True,
            status_code=status_code,
        )
    if status_code == 429:
        return DoubaoVoiceServiceError(
            "Doubao voice rate limit was reached",
            code="DOUBAO_VOICE_RATE_LIMITED",
            category="rate_limit",
            phase="provider_request",
            feature=feature,
            retryable=True,
            fatal=False,
            status_code=status_code,
        )
    if status_code is not None and 400 <= status_code < 500:
        return DoubaoVoiceServiceError(
            "Doubao voice configuration or request was rejected",
            code="DOUBAO_VOICE_CONFIG_INVALID",
            category="bad_request",
            phase="provider_request",
            feature=feature,
            retryable=False,
            fatal=True,
            status_code=status_code,
        )
    if status_code is not None and status_code >= 500:
        return DoubaoVoiceServiceError(
            "Doubao voice provider is unavailable",
            code="DOUBAO_VOICE_PROVIDER_UNAVAILABLE",
            category="provider_unavailable",
            phase="provider_request",
            feature=feature,
            retryable=True,
            fatal=True,
            status_code=status_code,
        )
    if isinstance(error, (httpx.TimeoutException, TimeoutError, asyncio.TimeoutError)):
        return DoubaoVoiceServiceError(
            "Doubao voice request timed out",
            code="DOUBAO_VOICE_NETWORK_TIMEOUT",
            category="network",
            phase="provider_request",
            feature=feature,
            retryable=True,
            fatal=False,
        )
    if isinstance(error, httpx.TransportError):
        return DoubaoVoiceServiceError(
            "Doubao voice network connection failed",
            code="DOUBAO_VOICE_NETWORK_FAILED",
            category="network",
            phase="provider_request",
            feature=feature,
            retryable=True,
            fatal=False,
        )
    return DoubaoVoiceServiceError(
        "Doubao voice provider request failed",
        code="DOUBAO_VOICE_PROVIDER_ERROR",
        category="provider_error",
        phase="provider_request",
        feature=feature,
        retryable=False,
        fatal=True,
    )


def validate_doubao_service_config(
    *,
    api_key: str | None,
    base_url: str | None,
    stt_model: str | None = None,
    tts_model: str | None = None,
    voice: str | None = None,
    input_sample_rate: int = DOUBAO_INPUT_SAMPLE_RATE,
    output_sample_rate: int = DOUBAO_OUTPUT_SAMPLE_RATE,
) -> None:
    """Validate the shared NewAPI relay contract before constructing services."""

    if not str(api_key or "").strip():
        raise DoubaoVoiceServiceError(
            "Doubao voice requires the current NewAPI user credential",
            code="MISSING_DOUBAO_VOICE_CREDENTIAL",
            category="configuration",
            phase="configuration",
            feature="voice:volcengine.doubao",
            retryable=False,
            fatal=True,
        )
    normalized_base_url = str(base_url or "").strip()
    if not normalized_base_url.startswith(("http://", "https://")):
        raise DoubaoVoiceServiceError(
            "Doubao voice requires a valid HTTP NewAPI relay URL",
            code="DOUBAO_VOICE_CONFIG_INVALID",
            category="configuration",
            phase="configuration",
            feature="voice:volcengine.doubao",
            retryable=False,
            fatal=True,
        )
    if stt_model is not None and not str(stt_model).strip():
        raise DoubaoVoiceServiceError(
            "Doubao STT model is required",
            code="DOUBAO_VOICE_CONFIG_INVALID",
            category="configuration",
            phase="configuration",
            feature="stt:volcengine.doubao",
            retryable=False,
            fatal=True,
        )
    if tts_model is not None and (not str(tts_model).strip() or not str(voice or "").strip()):
        raise DoubaoVoiceServiceError(
            "Doubao TTS model and voice are required",
            code="DOUBAO_VOICE_CONFIG_INVALID",
            category="configuration",
            phase="configuration",
            feature="tts:volcengine.doubao",
            retryable=False,
            fatal=True,
        )
    if input_sample_rate != DOUBAO_INPUT_SAMPLE_RATE:
        raise DoubaoVoiceServiceError(
            f"Doubao STT input sample rate must be {DOUBAO_INPUT_SAMPLE_RATE}",
            code="DOUBAO_VOICE_CONFIG_INVALID",
            category="configuration",
            phase="configuration",
            feature="stt:volcengine.doubao",
            retryable=False,
            fatal=True,
        )
    if output_sample_rate != DOUBAO_OUTPUT_SAMPLE_RATE:
        raise DoubaoVoiceServiceError(
            f"Doubao TTS output sample rate must be {DOUBAO_OUTPUT_SAMPLE_RATE}",
            code="DOUBAO_VOICE_CONFIG_INVALID",
            category="configuration",
            phase="configuration",
            feature="tts:volcengine.doubao",
            retryable=False,
            fatal=True,
        )


class VolcengineDoubaoSTTService(SegmentedSTTService):
    """VAD-segmented STT through NewAPI's batch transcription endpoint."""

    _settings: STTSettings

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        sample_rate: int = DOUBAO_INPUT_SAMPLE_RATE,
        language: str = "zh",
        vad_segment_settle_seconds: float = 0.0,
        timeout: float = 30.0,
        http_client: Any | None = None,
        transcribe_request: _TranscribeRequest | None = None,
        **kwargs: Any,
    ) -> None:
        validate_doubao_service_config(
            api_key=api_key,
            base_url=base_url,
            stt_model=model,
            input_sample_rate=sample_rate,
        )
        settings = STTSettings(
            model=model,
            language=language,
        )
        super().__init__(sample_rate=sample_rate, settings=settings, **kwargs)
        self._api_key = api_key
        self._transcriptions_url = normalize_transcriptions_url(base_url)
        self._language = language
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
        )
        self._owns_http_client = http_client is None
        self._transcribe_request = transcribe_request or self._request_transcription
        self._vad_segment_settle_seconds = max(0.0, vad_segment_settle_seconds)
        self._pending_commit_audio = bytearray()
        self._completed_turn_since_commit = False
        self._segment_settle_task: asyncio.Task[None] | None = None
        self._segment_preview_tasks: dict[int, asyncio.Task[Frame | None]] = {}
        self._latest_segment_preview_revision = 0
        self._latest_segment_preview_audio_size = 0
        self._latest_segment_preview_task: asyncio.Task[Frame | None] | None = None
        self._last_published_preview_revision = 0
        self._transcription_tasks: set[asyncio.Task[None]] = set()
        self._transcription_results: dict[int, Frame | None] = {}
        self._transcription_result_lock = asyncio.Lock()
        self._next_transcription_sequence = 0
        self._next_publish_sequence = 0
        self._last_enqueued_sequence = -1
        self._closed = False

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        """Transcribe one complete WAV segment emitted by Pipecat VAD."""

        frame = await self._transcription_frame(audio)
        if frame is not None:
            yield frame

    async def process_generator(
        self,
        generator: AsyncGenerator[Frame | None, None],
    ) -> None:
        """Keep STT results on the downstream TalkWise event path.

        Pipecat's default AI service implementation sends ErrorFrame upstream.
        TalkWise mirrors provider results from a downstream event processor, so
        an empty transcript or provider failure would otherwise disappear from
        the websocket event stream.
        """

        async for frame in generator:
            if frame is not None:
                await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    async def push_frame(
        self,
        frame: Frame,
        direction: FrameDirection = FrameDirection.DOWNSTREAM,
    ) -> None:
        """Preserve explicit finalization for asynchronously published segments."""

        if isinstance(frame, TranscriptionFrame):
            await STTService.push_frame(self, frame, direction)
            return
        await super().push_frame(frame, direction)

    async def process_audio_frame(
        self,
        frame: AudioRawFrame,
        direction: FrameDirection,
    ) -> None:
        """Retain a bounded utterance so an explicit client commit can finalize it."""

        if self._user_speaking:
            self._pending_commit_audio.extend(frame.audio)
            max_bytes = self.sample_rate * 2 * _DOUBAO_MANUAL_COMMIT_MAX_SECONDS
            if max_bytes > 0 and len(self._pending_commit_audio) > max_bytes:
                del self._pending_commit_audio[: len(self._pending_commit_audio) - max_bytes]
        await super().process_audio_frame(frame, direction)

    async def _handle_user_started_speaking(
        self,
        frame: VADUserStartedSpeakingFrame,
    ) -> None:
        resumed_pending_segment = await self._cancel_segment_settlement()
        await super()._handle_user_started_speaking(frame)
        self._completed_turn_since_commit = False
        if not resumed_pending_segment:
            self._pending_commit_audio.clear()
        self._pending_commit_audio.extend(self._audio_buffer)
        self._audio_buffer.clear()

    async def _handle_user_stopped_speaking(
        self,
        frame: VADUserStoppedSpeakingFrame,
    ) -> None:
        if not self._pending_commit_audio:
            self._user_speaking = False
            self._audio_buffer.clear()
            return
        self._user_speaking = False
        self._audio_buffer.clear()
        if self._vad_segment_settle_seconds > 0:
            self._start_segment_preview(self._user_id)
            await self._schedule_segment_settlement(self._user_id)
            return
        self._enqueue_pending_segment(self._user_id)

    async def commit_audio(self) -> None:
        """Finalize buffered browser audio when recording stops before VAD closes a turn."""

        await self._cancel_segment_settlement()
        if self._pending_commit_audio:
            await self._finalize_pending_segment(self._user_id)
        elif self._completed_turn_since_commit:
            self._audio_buffer.clear()
            self._pending_commit_audio.clear()
        else:
            pending_audio = bytes(self._audio_buffer)
            if pending_audio:
                self._audio_buffer.clear()
                self._pending_commit_audio.extend(pending_audio)
                await self._finalize_pending_segment(self._user_id)
        await self._wait_for_pending_transcriptions()

    async def stop(self, frame: EndFrame) -> None:
        await self._cancel_segment_settlement()
        await self._cancel_segment_preview_tasks()
        await self._wait_for_pending_transcriptions()
        await super().stop(frame)
        self._pending_commit_audio.clear()
        await self._close_client()

    async def cancel(self, frame: CancelFrame) -> None:
        await self._cancel_segment_settlement()
        await self._cancel_pending_transcriptions()
        await super().cancel(frame)
        self._pending_commit_audio.clear()
        await self._close_client()

    async def cleanup(self) -> None:
        await self._cancel_segment_settlement()
        await self._cancel_pending_transcriptions()
        await super().cleanup()
        self._pending_commit_audio.clear()
        await self._close_client()

    def _encode_audio_segment(self, audio: bytes) -> bytes:
        if not self.wants_wav_segments:
            return audio

        content = io.BytesIO()
        with wave.open(content, "wb") as wav:
            wav.setsampwidth(2)
            wav.setnchannels(1)
            wav.setframerate(self.sample_rate)
            wav.writeframes(audio)
        return content.getvalue()

    def _enqueue_pending_segment(self, user_id: str) -> None:
        if not self._pending_commit_audio:
            return
        audio = self._encode_audio_segment(bytes(self._pending_commit_audio))
        self._pending_commit_audio.clear()
        self._audio_buffer.clear()
        self._completed_turn_since_commit = True
        self._enqueue_transcription(audio, user_id)

    async def _finalize_pending_segment(self, user_id: str) -> None:
        if not self._pending_commit_audio:
            return
        audio_size = len(self._pending_commit_audio)
        preview_task = self._latest_segment_preview_task
        if (
            preview_task is not None
            and self._latest_segment_preview_audio_size == audio_size
        ):
            frame = await asyncio.shield(preview_task)
        else:
            audio = self._encode_audio_segment(bytes(self._pending_commit_audio))
            frame = await self._transcription_frame(audio, user_id=user_id)
        self._pending_commit_audio.clear()
        self._audio_buffer.clear()
        self._completed_turn_since_commit = True
        self._latest_segment_preview_task = None
        self._latest_segment_preview_audio_size = 0
        if frame is not None:
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    def _start_segment_preview(self, user_id: str) -> None:
        if not self._pending_commit_audio:
            return
        self._latest_segment_preview_revision += 1
        revision = self._latest_segment_preview_revision
        audio_size = len(self._pending_commit_audio)
        audio = self._encode_audio_segment(bytes(self._pending_commit_audio))
        task = self.create_task(
            self._transcribe_segment_preview(revision, audio, user_id),
            name=f"doubao_stt_segment_preview_{revision}",
        )
        self._segment_preview_tasks[revision] = task
        self._latest_segment_preview_audio_size = audio_size
        self._latest_segment_preview_task = task
        task.add_done_callback(
            lambda completed, current_revision=revision: self._segment_preview_tasks.pop(
                current_revision,
                None,
            )
        )

    async def _transcribe_segment_preview(
        self,
        revision: int,
        audio: bytes,
        user_id: str,
    ) -> Frame | None:
        frame = await self._transcription_frame(audio, user_id=user_id)
        if (
            isinstance(frame, TranscriptionFrame)
            and revision >= self._last_published_preview_revision
        ):
            self._last_published_preview_revision = revision
            await self.push_frame(
                InterimTranscriptionFrame(
                    text=frame.text,
                    user_id=frame.user_id,
                    timestamp=frame.timestamp,
                    language=frame.language,
                    result=frame.result,
                ),
                FrameDirection.DOWNSTREAM,
            )
        return frame

    async def _schedule_segment_settlement(self, user_id: str) -> None:
        await self._cancel_segment_settlement()
        task = self.create_task(
            self._settle_segment_after_delay(user_id),
            name="doubao_stt_segment_settlement",
        )
        self._segment_settle_task = task

    async def _settle_segment_after_delay(self, user_id: str) -> None:
        task = asyncio.current_task()
        try:
            await asyncio.sleep(self._vad_segment_settle_seconds)
            await self._finalize_pending_segment(user_id)
        finally:
            if self._segment_settle_task is task:
                self._segment_settle_task = None

    async def _cancel_segment_settlement(self) -> bool:
        task = self._segment_settle_task
        if task is None:
            return False
        self._segment_settle_task = None
        await self.cancel_task(task)
        return True

    def _enqueue_transcription(self, audio: bytes, user_id: str) -> None:
        sequence = self._next_transcription_sequence
        self._next_transcription_sequence += 1
        self._last_enqueued_sequence = sequence
        task = self.create_task(
            self._transcribe_segment(sequence, audio, user_id),
            name=f"doubao_stt_segment_{sequence}",
        )
        self._transcription_tasks.add(task)
        task.add_done_callback(self._transcription_tasks.discard)

    async def _transcribe_segment(
        self,
        sequence: int,
        audio: bytes,
        user_id: str,
    ) -> None:
        frame = await self._transcription_frame(audio, user_id=user_id)
        async with self._transcription_result_lock:
            self._transcription_results[sequence] = frame
            await self._publish_ready_transcriptions()

    async def _publish_ready_transcriptions(self) -> None:
        if self._user_speaking or self._last_enqueued_sequence < self._next_publish_sequence:
            return
        pending_sequences = range(
            self._next_publish_sequence,
            self._last_enqueued_sequence + 1,
        )
        if any(sequence not in self._transcription_results for sequence in pending_sequences):
            return

        last_sequence = self._last_enqueued_sequence
        while self._next_publish_sequence <= last_sequence:
            sequence = self._next_publish_sequence
            frame = self._transcription_results.pop(sequence)
            self._next_publish_sequence += 1
            if frame is None:
                continue
            if isinstance(frame, TranscriptionFrame):
                frame.finalized = sequence == last_sequence
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    async def _wait_for_pending_transcriptions(self) -> None:
        while self._transcription_tasks:
            tasks = tuple(self._transcription_tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            self._transcription_tasks.difference_update(task for task in tasks if task.done())

        async with self._transcription_result_lock:
            await self._publish_ready_transcriptions()

    async def _cancel_pending_transcriptions(self) -> None:
        await self._cancel_segment_preview_tasks()
        tasks = tuple(self._transcription_tasks)
        for task in tasks:
            await self.cancel_task(task)
        self._transcription_tasks.clear()
        self._transcription_results.clear()

    async def _cancel_segment_preview_tasks(self) -> None:
        preview_tasks = tuple(self._segment_preview_tasks.values())
        for task in preview_tasks:
            await self.cancel_task(task)
        self._segment_preview_tasks.clear()
        self._latest_segment_preview_task = None
        self._latest_segment_preview_audio_size = 0

    async def _transcription_frame(
        self,
        audio: bytes,
        *,
        user_id: str | None = None,
    ) -> TranscriptionFrame | ErrorFrame | None:
        if not audio:
            return None
        try:
            text = (
                await self._transcribe_request(
                    audio,
                    assert_given(self._settings.model) or "",
                    self._language,
                )
            ).strip()
            if not text:
                empty_transcript = DoubaoVoiceServiceError(
                    "No clear speech was recognized. Move closer to the microphone and try again.",
                    code="DOUBAO_VOICE_TRANSCRIPT_EMPTY",
                    category="input_audio",
                    phase="provider_response",
                    feature="stt:volcengine.doubao",
                    retryable=True,
                    fatal=False,
                )
                error_frame = ErrorFrame(
                    error=str(empty_transcript),
                    fatal=empty_transcript.fatal,
                )
                error_frame.metadata["providerError"] = empty_transcript.to_realtime_error()
                return error_frame
            return TranscriptionFrame(
                text,
                self._user_id if user_id is None else user_id,
                time_now_iso8601(),
                language=self._settings.language,
                finalized=True,
            )
        except asyncio.CancelledError:
            raise
        except DoubaoVoiceServiceError as exc:
            return ErrorFrame(error=str(exc), fatal=exc.fatal, exception=exc)
        except Exception as exc:
            classified = classify_doubao_voice_error(
                exc,
                feature="stt:volcengine.doubao",
            )
            return ErrorFrame(
                error=str(classified),
                fatal=classified.fatal,
                exception=classified,
            )

    async def _request_transcription(self, audio: bytes, model: str, language: str) -> str:
        try:
            response = await self._http_client.post(
                self._transcriptions_url,
                files={"file": ("audio.wav", audio, "audio/wav")},
                data={
                    "model": model,
                    "language": language,
                    "response_format": "json",
                },
                headers=authorization_headers(self._api_key),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise classify_doubao_voice_error(
                exc,
                feature="stt:volcengine.doubao",
            ) from exc
        if response.status_code != 200:
            raise classify_doubao_voice_error(
                status_code=response.status_code,
                gateway_error_code=await _response_error_code(response),
                feature="stt:volcengine.doubao",
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise DoubaoVoiceServiceError(
                "Doubao STT returned an invalid response",
                code="DOUBAO_VOICE_RESPONSE_INVALID",
                category="provider_error",
                phase="provider_response",
                feature="stt:volcengine.doubao",
                retryable=False,
                fatal=True,
            ) from exc
        return str(payload.get("text") or "") if isinstance(payload, Mapping) else ""

    async def _close_client(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._http_client, "aclose", None)
        if callable(close):
            await close()


@dataclass
class VolcengineDoubaoTTSSettings(TTSSettings):
    """Runtime-updatable settings for Doubao speech synthesis."""

    speed: float | _NotGiven = field(default_factory=lambda: NOT_GIVEN)


class VolcengineDoubaoTTSService(TTSService):
    """Streaming PCM TTS through the existing authenticated NewAPI voice relay."""

    Settings = VolcengineDoubaoTTSSettings
    _settings: Settings

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        voice: str,
        sample_rate: int = DOUBAO_OUTPUT_SAMPLE_RATE,
        speed: float = 1.0,
        timeout: float = 30.0,
        http_client: Any | None = None,
        **kwargs: Any,
    ) -> None:
        validate_doubao_service_config(
            api_key=api_key,
            base_url=base_url,
            tts_model=model,
            voice=voice,
            output_sample_rate=sample_rate,
        )
        if not 0.25 <= speed <= 4.0:
            raise DoubaoVoiceServiceError(
                "Doubao TTS speed must be between 0.25 and 4.0",
                code="DOUBAO_VOICE_CONFIG_INVALID",
                category="configuration",
                phase="configuration",
                feature="tts:volcengine.doubao",
                retryable=False,
                fatal=True,
            )
        settings = self.Settings(model=model, voice=voice, language=None, speed=speed)
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            push_stop_frames=True,
            settings=settings,
            **kwargs,
        )
        self._api_key = api_key
        self._speech_url = f"{base_url.rstrip('/')}{_SPEECH_PATH}"
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
        )
        self._generation = 0
        self._closed = False

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        generation = self._generation
        payload = {
            "model": assert_given(self._settings.model),
            "input": text,
            "voice": assert_given(self._settings.voice),
            "response_format": "pcm",
            "speed": float(self._settings.speed),
        }
        headers = {
            **authorization_headers(self._api_key),
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
        }
        try:
            async with self._http_client.stream(
                "POST",
                self._speech_url,
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    raise classify_doubao_voice_error(
                        status_code=response.status_code,
                        gateway_error_code=await _response_error_code(response),
                        feature="tts:volcengine.doubao",
                    )
                await self.start_tts_usage_metrics(text)
                async for chunk in response.aiter_bytes(chunk_size=self.chunk_size):
                    if generation != self._generation:
                        break
                    if chunk:
                        await self.stop_ttfb_metrics()
                        yield TTSAudioRawFrame(
                            chunk,
                            self.sample_rate,
                            1,
                            context_id=context_id,
                        )
        except asyncio.CancelledError:
            raise
        except DoubaoVoiceServiceError as exc:
            yield ErrorFrame(error=str(exc), fatal=exc.fatal, exception=exc)
        except Exception as exc:
            classified = classify_doubao_voice_error(
                exc,
                feature="tts:volcengine.doubao",
            )
            yield ErrorFrame(
                error=str(classified),
                fatal=classified.fatal,
                exception=classified,
            )

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        if isinstance(frame, InterruptionFrame):
            self._generation += 1
        await super().process_frame(frame, direction)

    async def stop(self, frame: EndFrame) -> None:
        self._generation += 1
        await super().stop(frame)
        await self._close_client()

    async def cancel(self, frame: CancelFrame) -> None:
        self._generation += 1
        await super().cancel(frame)
        await self._close_client()

    async def cleanup(self) -> None:
        self._generation += 1
        await super().cleanup()
        await self._close_client()

    async def _close_client(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._http_client, "aclose", None)
        if callable(close):
            await close()


def create_volcengine_doubao_stt_service(**kwargs: Any) -> VolcengineDoubaoSTTService:
    return VolcengineDoubaoSTTService(**kwargs)


def create_volcengine_doubao_tts_service(**kwargs: Any) -> VolcengineDoubaoTTSService:
    return VolcengineDoubaoTTSService(**kwargs)


async def _response_error_code(response: Any) -> str | None:
    """Read only a bounded, non-secret error code from a failed gateway response."""

    try:
        payload: object
        read = getattr(response, "aread", None)
        if callable(read):
            body = await read()
            if len(body) > 16 * 1024:
                return None
            payload = json.loads(body) if body else response.json()
        else:
            payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    code = payload.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip().upper()
    nested = payload.get("error")
    if isinstance(nested, Mapping):
        code = nested.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip().upper()
    return None


__all__: Sequence[str] = (
    "DOUBAO_INPUT_SAMPLE_RATE",
    "DOUBAO_OUTPUT_SAMPLE_RATE",
    "DoubaoVoiceServiceError",
    "VOLCENGINE_DOUBAO_PROVIDER",
    "VolcengineDoubaoSTTService",
    "VolcengineDoubaoTTSService",
    "classify_doubao_voice_error",
    "create_volcengine_doubao_stt_service",
    "create_volcengine_doubao_tts_service",
    "validate_doubao_service_config",
)
