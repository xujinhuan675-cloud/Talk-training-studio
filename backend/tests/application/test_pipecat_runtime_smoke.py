import pytest


def test_real_pipecat_runtime_imports_declared_voice_symbols():
    pytest.importorskip("pipecat")

    from infrastructure.external.pipecat.realtime_pipeline import (
        create_pipecat_realtime_pipeline,
        get_pipecat_capability,
        import_pipecat_runtime,
    )

    capability = get_pipecat_capability(require_websocket=True)
    assert capability.available is True
    assert capability.core_available is True
    assert capability.websocket_available is True
    assert capability.vad_available is True
    assert capability.stt_available is True
    assert capability.tts_available is True
    assert capability.turn_detection_available is True
    assert capability.optional_missing_modules == ()

    runtime = import_pipecat_runtime(require_websocket=True)
    assert runtime.FastAPIWebsocketTransport is not None
    assert runtime.OpenAIRealtimeSTTService is not None
    assert runtime.OpenAITTSService is not None
    assert runtime.SileroVADAnalyzer is not None
    assert runtime.VADProcessor is not None
    assert runtime.UserTurnProcessor is not None

    assert create_pipecat_realtime_pipeline() is not None
