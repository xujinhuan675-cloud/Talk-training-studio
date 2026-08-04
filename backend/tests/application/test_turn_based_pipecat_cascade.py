from __future__ import annotations

import pytest

from application.ports.realtime import REALTIME_RUNTIME_PIPECAT
from application.ports.turn_based_voice import TurnBasedVoiceSynthesisConfig
from infrastructure.external.pipecat.turn_based_cascade import PipecatTurnBasedCascadePipeline


class _CapturingGatewayTTS:
    def __init__(self) -> None:
        self.requests = []

    async def synthesize_stream(self, text, config):
        self.requests.append((text, config))
        yield b"mp3-"
        yield b"audio"


@pytest.mark.asyncio
async def test_turn_based_cascade_wraps_gateway_tts_as_training_audio_output() -> None:
    tts = _CapturingGatewayTTS()
    pipeline = PipecatTurnBasedCascadePipeline(
        tts,
        tts_provider="openai_compatible_gateway",
        tts_model="tts-1",
    )

    outputs = [
        output
        async for output in pipeline.synthesize_stream(
            "Continue the negotiation in Chinese.",
            TurnBasedVoiceSynthesisConfig(
                persona_id="customer",
                voice_id="alloy",
                voice_speed=1.2,
                style_instruction="Use natural Mandarin pronunciation.",
                language="zh-CN",
                audio_sequence=3,
                metadata={
                    "replyId": "reply-7",
                    "sentenceIndex": 3,
                    "api_key": "secret",
                    "unsafe": object(),
                },
            ),
        )
    ]

    assert len(outputs) == 1
    assert outputs[0].data == b"mp3-audio"
    assert outputs[0].provider == "pipecat"
    assert outputs[0].runtime == REALTIME_RUNTIME_PIPECAT
    assert outputs[0].mime_type == "audio/mpeg"
    assert outputs[0].sequence == 3
    assert outputs[0].context_id == "reply-7:3"
    assert outputs[0].metadata["pipeline"] == {
        "profile": "cascade",
        "mode": "turn_based",
        "transport": "talkwise.audio_chunks",
    }
    assert outputs[0].metadata["tts"] == {
        "provider": "openai_compatible_gateway",
        "model": "tts-1",
        "voice": "alloy",
        "language": "zh-CN",
    }
    assert outputs[0].metadata["replyId"] == "reply-7"
    assert outputs[0].metadata["sentenceIndex"] == 3
    assert "api_key" not in outputs[0].metadata
    assert "unsafe" not in outputs[0].metadata

    assert len(tts.requests) == 1
    text, config = tts.requests[0]
    assert text == "Continue the negotiation in Chinese."
    assert config.voice_id == "alloy"
    assert config.speed == 1.2
    assert config.style_instruction == "Use natural Mandarin pronunciation."
    assert config.language == "zh-CN"


@pytest.mark.asyncio
async def test_turn_based_cascade_does_not_call_gateway_for_blank_text() -> None:
    tts = _CapturingGatewayTTS()
    pipeline = PipecatTurnBasedCascadePipeline(tts)

    outputs = [
        output
        async for output in pipeline.synthesize_stream(
            "   ",
            TurnBasedVoiceSynthesisConfig(persona_id="coach"),
        )
    ]

    assert outputs == []
    assert tts.requests == []
