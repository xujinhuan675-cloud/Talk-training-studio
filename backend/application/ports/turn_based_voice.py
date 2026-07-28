"""Application-owned port for turn-based voice synthesis pipelines."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from application.ports.realtime import RealtimeOutputAudio


@dataclass(frozen=True)
class TurnBasedVoiceSynthesisConfig:
    """Provider-neutral config for one turn-based TTS sentence."""

    persona_id: str
    voice_id: str = ""
    voice_speed: float = 1.0
    voice_volume: float = 1.0
    voice_pitch: float = 0.0
    style_instruction: str | None = None
    language: str | None = None
    audio_sequence: int | None = None
    tts_provider: str | None = None
    tts_model: str | None = None
    output_mime_type: str = "audio/mpeg"
    metadata: Mapping[str, object] = field(default_factory=dict)


@runtime_checkable
class TurnBasedVoicePipelinePort(Protocol):
    """Turn-based voice pipeline boundary owned by application services."""

    async def synthesize_stream(
        self,
        text: str,
        config: TurnBasedVoiceSynthesisConfig,
    ) -> AsyncIterator[RealtimeOutputAudio]:
        """Synthesize one assistant sentence into provider-neutral audio output."""
        ...
