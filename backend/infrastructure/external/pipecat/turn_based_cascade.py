# input: gateway-backed TTSPort audio and turn-based training metadata
# output: provider-neutral Pipecat audio.output events
# owner: TalkWise training runtime
# pos: infrastructure - adapts NewAPI voice output into training events
"""Turn-based gateway TTS adapter for Pipecat-style training events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from application.ports.realtime import REALTIME_RUNTIME_PIPECAT, RealtimeOutputAudio
from application.ports.tts import TTSConfig, TTSPort
from application.ports.turn_based_voice import TurnBasedVoiceSynthesisConfig

_PIPECAT_PROVIDER = "pipecat"
_PIPECAT_CASCADE_PROFILE = "cascade"
_TURN_BASED_TRANSPORT = "talkwise.audio_chunks"


class PipecatTurnBasedCascadePipeline:
    """Wrap gateway-backed TTS output in the shared training audio contract."""

    def __init__(
        self,
        tts: TTSPort,
        *,
        tts_provider: str | None = None,
        tts_model: str | None = None,
        output_mime_type: str = "audio/mpeg",
    ) -> None:
        self._tts = tts
        self._tts_provider = _clean_text(tts_provider)
        self._tts_model = _clean_text(tts_model)
        self._output_mime_type = output_mime_type

    async def synthesize_stream(
        self,
        text: str,
        config: TurnBasedVoiceSynthesisConfig,
    ) -> AsyncIterator[RealtimeOutputAudio]:
        clean_text = text.strip()
        if not clean_text:
            return

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


def _audio_metadata(
    config: TurnBasedVoiceSynthesisConfig,
    *,
    tts_provider: str | None,
    tts_model: str | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": _PIPECAT_PROVIDER,
        "pipeline": {
            "profile": _PIPECAT_CASCADE_PROFILE,
            "mode": "turn_based",
            "transport": _TURN_BASED_TRANSPORT,
        },
        "tts": {
            "provider": config.tts_provider or tts_provider,
            "model": config.tts_model or tts_model,
            "voice": config.voice_id,
            "language": config.language,
        },
    }

    from application.ports.realtime import sanitize_realtime_public_value

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
