import pytest

from application.ports.realtime import (
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingVoiceContext,
)


def test_real_pipecat_runtime_imports_declared_voice_symbols():
    pytest.importorskip("pipecat")

    from infrastructure.external.pipecat.realtime_pipeline import (
        create_pipecat_realtime_pipeline,
        get_pipecat_capability,
        import_pipecat_runtime,
        pipecat_realtime_capability_response,
        pipecat_realtime_smoke_contract,
    )

    capability = get_pipecat_capability(require_websocket=True)
    assert capability.available is True
    assert capability.core_available is True
    assert capability.websocket_available is True
    assert capability.vad_available is True
    assert capability.stt_available is True
    assert capability.tts_available is True
    assert capability.llm_available is True
    assert capability.turn_detection_available is True
    assert capability.optional_missing_modules == ()

    runtime = import_pipecat_runtime(require_websocket=True)
    assert runtime.FastAPIWebsocketTransport is not None
    assert runtime.OpenAIRealtimeSTTService is not None
    assert runtime.OpenAITTSService is not None
    assert runtime.OpenAILLMService is not None
    assert runtime.LLMContext is not None
    assert runtime.LLMContextAggregatorPair is not None
    assert runtime.SileroVADAnalyzer is not None
    assert runtime.VADProcessor is not None
    assert runtime.UserTurnProcessor is not None

    assert create_pipecat_realtime_pipeline() is not None

    capabilities = pipecat_realtime_capability_response(
        require_websocket=True,
        openai_api_key_available=True,
        include_source_snapshot=False,
        input_audio_format="pcm16",
        output_audio_format="pcm16",
    )
    assert capabilities["runtime"] == "pipecat"
    assert capabilities["provider"] == "pipecat"
    assert capabilities["readyForCall"] is True
    assert capabilities["readiness"]["status"] == "ready"
    assert capabilities["smoke"] == pipecat_realtime_smoke_contract(
        ready_for_call=True,
        require_websocket=True,
        input_audio_format="pcm16",
        output_audio_format="pcm16",
    )
    assert capabilities["smoke"]["browserE2EVerified"] is False
    assert {
        "session.started",
        "audio.input",
        "audio.output",
        "transcript.delta",
        "transcript.done",
        "transcript.persisted",
        "training.live_guidance.triggered",
        "user_turn.started",
        "user_turn.stopped",
        "assistant_speaking.started",
        "assistant_speaking.stopped",
        "interrupted",
        "silence_timeout",
    } == set(capabilities["smoke"]["contractEvents"])


def test_real_pipecat_runtime_constructs_native_voice_processors():
    pytest.importorskip("pipecat")

    from infrastructure.external.pipecat.realtime_pipeline import (
        build_pipecat_voice_processors,
        import_pipecat_runtime,
    )

    runtime = import_pipecat_runtime(require_websocket=True)
    context = TrainingVoiceContext(
        binding=RealtimeSessionBinding(training_session_id="smoke-session", room_id=1),
        task_goal="Practice a concise stakeholder response",
        recent_turns=(
            {"speaker": "user", "text": "Can we start with a pilot?"},
            {"speaker": "assistant", "text": "Only if the success metric is clear."},
        ),
        metadata={"scenarioTemplateId": "native-pipecat-smoke"},
    )
    config = RealtimePipelineConfig(
        provider="pipecat",
        model="gpt-4o-mini",
        voice="alloy",
        instructions="Keep the live role-play concise.",
        metadata={
            "stt": {
                "provider": "openai",
                "model": "gpt-4o-mini-transcribe",
                "turnDetection": "disabled",
            },
            "tts": {"provider": "openai", "model": "gpt-4o-mini-tts"},
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "vad": {"provider": "silero", "sampleRate": 16000},
            "turnDetection": {"provider": "pipecat"},
            "openaiApiKey": "sk-test",
        },
    )

    processors = build_pipecat_voice_processors(runtime, config, context=context)

    assert [type(processor).__name__ for processor in processors] == [
        "VADProcessor",
        "OpenAIRealtimeSTTService",
        "LLMUserAggregator",
        "OpenAILLMService",
        "OpenAITTSService",
        "LLMAssistantAggregator",
    ]
