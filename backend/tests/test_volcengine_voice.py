from __future__ import annotations

import base64
from dataclasses import dataclass
import gzip
import json
from typing import Any, Mapping

import httpx
import pytest

from application.ports.tts import TTSConfig
from core.config import VoiceSettings, settings
import infrastructure.external.voice as voice_lifecycle
from infrastructure.external.voice.volcengine_voice import (
    VolcengineSTTProvider,
    VolcengineTTSProvider,
    build_volcengine_asr_headers,
    build_volcengine_asr_request_payload,
    encode_volcengine_asr_audio_request,
    encode_volcengine_asr_json_request,
    normalize_volcengine_asr_url,
    normalize_volcengine_tts_url,
    parse_volcengine_asr_response,
)

_MSG_CLIENT_FULL_REQUEST = 0b0001
_MSG_CLIENT_AUDIO_ONLY_REQUEST = 0b0010
_MSG_SERVER_FULL_RESPONSE = 0b1001
_MSG_SERVER_ERROR_RESPONSE = 0b1111
_FLAG_POS_SEQUENCE = 0b0001
_FLAG_NEG_SEQUENCE = 0b0011
_SERIALIZATION_NONE = 0b0000
_SERIALIZATION_JSON = 0b0001
_COMPRESSION_GZIP = 0b0001


@dataclass
class _DecodedFrame:
    message_type: int
    sequence: int | None
    payload: dict[str, Any] | bytes


class _FakeVolcengineWebSocket:
    def __init__(self, responses: list[bytes | str]) -> None:
        self.responses = responses
        self.sent: list[bytes] = []

    async def send(self, message: bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> bytes | str:
        if not self.responses:
            raise AssertionError("Volcengine STT test exhausted fake responses")
        return self.responses.pop(0)


class _FakeVolcengineWebSocketContext:
    def __init__(self, websocket: _FakeVolcengineWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> _FakeVolcengineWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.captured: dict[str, object] = {}

    def stream(self, method: str, url: str, *, json=None, headers=None, **_kwargs):
        self.captured = {
            "method": method,
            "url": url,
            "json": json,
            "headers": dict(headers or {}),
        }
        return _FakeStream(self.response)

    async def aclose(self) -> None:
        return None


class _FakeVolcengineTTSProvider:
    instances: list["_FakeVolcengineTTSProvider"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.instances.append(self)

    async def close(self) -> None:
        self.closed = True


class _FakeVolcengineSTTProvider(_FakeVolcengineTTSProvider):
    instances: list["_FakeVolcengineSTTProvider"] = []


def _decode_client_frame(raw: bytes) -> _DecodedFrame:
    first, second, third = raw[0], raw[1], raw[2]
    offset = (first & 0x0F) * 4
    message_type = second >> 4
    flags = second & 0x0F
    serialization = third >> 4
    compression = third & 0x0F
    sequence: int | None = None
    if flags in {_FLAG_POS_SEQUENCE, _FLAG_NEG_SEQUENCE}:
        sequence = int.from_bytes(raw[offset : offset + 4], "big", signed=True)
        offset += 4

    payload_size = int.from_bytes(raw[offset : offset + 4], "big", signed=False)
    payload = raw[offset + 4 : offset + 4 + payload_size]
    if compression == _COMPRESSION_GZIP:
        payload = gzip.decompress(payload)
    if serialization == _SERIALIZATION_JSON:
        decoded_payload: dict[str, Any] | bytes = json.loads(payload.decode("utf-8"))
    elif serialization == _SERIALIZATION_NONE:
        decoded_payload = payload
    else:
        decoded_payload = payload
    return _DecodedFrame(
        message_type=message_type,
        sequence=sequence,
        payload=decoded_payload,
    )


def _build_server_response_frame(payload: Mapping[str, Any], *, sequence: int = -1) -> bytes:
    data = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    header = bytes(
        [
            0x11,
            (_MSG_SERVER_FULL_RESPONSE << 4) | _FLAG_NEG_SEQUENCE,
            (_SERIALIZATION_JSON << 4) | _COMPRESSION_GZIP,
            0x00,
        ]
    )
    return header + sequence.to_bytes(4, "big", signed=True) + len(data).to_bytes(4, "big") + data


def _build_server_error_frame(code: int, message: str) -> bytes:
    data = message.encode("utf-8")
    header = bytes([0x11, _MSG_SERVER_ERROR_RESPONSE << 4, 0x00, 0x00])
    return header + code.to_bytes(4, "big", signed=False) + len(data).to_bytes(4, "big") + data


def test_volcengine_url_and_asr_request_helpers() -> None:
    assert normalize_volcengine_tts_url("openspeech.bytedance.com") == (
        "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    )
    assert normalize_volcengine_asr_url("openspeech.bytedance.com") == (
        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
    )
    assert build_volcengine_asr_headers(
        api_key="volc-key",
        model="volc.bigasr.test",
        request_id="req-1",
    ) == {
        "X-Api-Key": "volc-key",
        "X-Api-Resource-Id": "volc.bigasr.test",
        "X-Api-Request-Id": "req-1",
        "X-Api-Sequence": "-1",
    }

    payload = build_volcengine_asr_request_payload(
        request_id="req-1",
        language="zh_CN",
        audio_format="opus",
    )

    assert payload["audio"] == {
        "format": "ogg",
        "codec": "opus",
        "rate": 16000,
        "bits": 16,
        "channel": 1,
        "language": "zh-CN",
    }
    assert payload["request"]["model_name"] == "bigmodel"


@pytest.mark.asyncio
async def test_volcengine_stt_sends_headers_and_turn_based_audio_frames() -> None:
    response_frame = _build_server_response_frame(
        {
            "result": [{"text": "contract can renew"}],
            "addition": {"duration": "1250"},
        }
    )
    fake_websocket = _FakeVolcengineWebSocket([response_frame])
    captured_connection: dict[str, object] = {}

    def connector(
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> _FakeVolcengineWebSocketContext:
        captured_connection["url"] = url
        captured_connection["headers"] = dict(headers)
        captured_connection["timeout"] = timeout
        return _FakeVolcengineWebSocketContext(fake_websocket)

    provider = VolcengineSTTProvider(
        api_key="volc-api-key",
        model="volc.bigasr.test",
        base_url="wss://volc.example/asr",
        timeout=12.0,
        websocket_connector=connector,
        request_id_factory=lambda: "req-stt-1",
    )

    result = await provider.transcribe(
        b"wav-audio",
        language="zh-CN",
        audio_format="wav",
    )

    assert result.text == "contract can renew"
    assert result.language == "zh-CN"
    assert result.duration_seconds == 1.25
    assert captured_connection == {
        "url": "wss://volc.example/asr",
        "headers": {
            "X-Api-Key": "volc-api-key",
            "X-Api-Resource-Id": "volc.bigasr.test",
            "X-Api-Request-Id": "req-stt-1",
            "X-Api-Sequence": "-1",
        },
        "timeout": 12.0,
    }
    assert len(fake_websocket.sent) == 2

    config_frame = _decode_client_frame(fake_websocket.sent[0])
    assert config_frame.message_type == _MSG_CLIENT_FULL_REQUEST
    assert config_frame.sequence == 1
    assert config_frame.payload["audio"] == {
        "format": "wav",
        "codec": "raw",
        "rate": 16000,
        "bits": 16,
        "channel": 1,
        "language": "zh-CN",
    }
    assert config_frame.payload["request"]["reqid"] == "req-stt-1"

    audio_frame = _decode_client_frame(fake_websocket.sent[1])
    assert audio_frame.message_type == _MSG_CLIENT_AUDIO_ONLY_REQUEST
    assert audio_frame.sequence == -2
    assert audio_frame.payload == b"wav-audio"


def test_volcengine_stt_frame_parsing_handles_result_dict_and_errors() -> None:
    parsed = parse_volcengine_asr_response(
        _build_server_response_frame({"result": {"text": "approved", "duration": 1.5}})
    )

    assert parsed == {"result": {"text": "approved", "duration": 1.5}}
    with pytest.raises(RuntimeError, match="invalid api key"):
        parse_volcengine_asr_response(_build_server_error_frame(4001, "invalid api key"))


@pytest.mark.asyncio
async def test_volcengine_stt_rejects_browser_webm_before_network() -> None:
    def connector(*_args, **_kwargs):
        raise AssertionError("websocket connector should not be called")

    provider = VolcengineSTTProvider(
        api_key="volc-api-key",
        websocket_connector=connector,
    )

    with pytest.raises(ValueError, match="browser WebM audio must be converted"):
        build_volcengine_asr_request_payload(
            request_id="req-1",
            language="zh",
            audio_format="webm",
        )

    with pytest.raises(ValueError, match="browser WebM audio must be converted"):
        await provider.transcribe(b"webm-audio", audio_format="webm")


def test_volcengine_asr_encoder_round_trips_test_frames() -> None:
    request_frame = _decode_client_frame(
        encode_volcengine_asr_json_request(
            build_volcengine_asr_request_payload(
                request_id="req-1",
                language="en-US",
                audio_format="mp3",
            )
        )
    )
    audio_frame = _decode_client_frame(encode_volcengine_asr_audio_request(b"mp3", sequence=-1))

    assert request_frame.message_type == _MSG_CLIENT_FULL_REQUEST
    assert request_frame.payload["audio"]["format"] == "mp3"
    assert request_frame.payload["audio"]["language"] == "en-US"
    assert audio_frame.message_type == _MSG_CLIENT_AUDIO_ONLY_REQUEST
    assert audio_frame.sequence == -1
    assert audio_frame.payload == b"mp3"


@pytest.mark.asyncio
async def test_volcengine_tts_posts_payload_and_decodes_base64_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = b"mp3-audio"
    fake_client = _FakeAsyncClient(
        httpx.Response(
            200,
            content=(
                b'{"code":0,"data":"'
                + base64.b64encode(audio)
                + b'"}\n{"code":20000000,"message":"ok"}\n'
            ),
            request=httpx.Request("POST", "https://volc.example/tts"),
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: fake_client)

    provider = VolcengineTTSProvider(
        api_key="volc-token",
        model="seed-tts-2.0",
        base_url="https://volc.example/tts",
    )

    chunks = [
        chunk
        async for chunk in provider.synthesize_stream(
            "Please confirm the contract terms.",
            TTSConfig(
                voice_id="zh_female_vv_uranus_bigtts",
                speed=1.1,
                volume=0.9,
                pitch=2.0,
                language="zh-CN",
                style_instruction="Speak clearly.",
            ),
        )
    ]

    assert chunks == [audio]
    assert fake_client.captured["method"] == "POST"
    assert fake_client.captured["url"] == "https://volc.example/tts"
    assert fake_client.captured["headers"]["X-Api-Key"] == "volc-token"
    assert fake_client.captured["headers"]["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert fake_client.captured["json"] == {
        "req_params": {
            "text": "Please confirm the contract terms.",
            "speaker": "zh_female_vv_uranus_bigtts",
            "audio_params": {"format": "mp3", "sample_rate": 24000},
            "speed": 1.1,
            "volume": 0.9,
            "pitch": 2,
            "explicit_language": "zh",
            "additions": json.dumps(
                {"context_texts": ["Speak clearly."]},
                ensure_ascii=False,
            ),
        }
    }


@pytest.mark.asyncio
async def test_volcengine_tts_raises_on_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient(
        httpx.Response(
            200,
            content=b'{"code":4002,"message":"voice not found"}\n',
            request=httpx.Request("POST", "https://volc.example/tts"),
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: fake_client)

    provider = VolcengineTTSProvider(
        api_key="volc-token",
        base_url="https://volc.example/tts",
    )

    with pytest.raises(RuntimeError, match="voice not found"):
        async for _chunk in provider.synthesize_stream(
            "Hello.",
            TTSConfig(voice_id="missing-voice"),
        ):
            pass


@pytest.mark.asyncio
async def test_volcengine_lifecycle_uses_provider_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_voice = settings.voice
    voice_lifecycle._tts_client = None
    voice_lifecycle._stt_client = None
    _FakeVolcengineTTSProvider.instances = []
    _FakeVolcengineSTTProvider.instances = []
    monkeypatch.setattr(
        "infrastructure.external.voice.volcengine_voice.VolcengineTTSProvider",
        _FakeVolcengineTTSProvider,
    )
    monkeypatch.setattr(
        "infrastructure.external.voice.volcengine_voice.VolcengineSTTProvider",
        _FakeVolcengineSTTProvider,
    )
    settings.voice = VoiceSettings(
        tts_provider="doubao",
        tts_api_key="volc-tts-key",
        tts_base_url=None,
        tts_model="speech-2.8-hd",
        stt_provider="volcengine",
        stt_api_key="volc-stt-key",
        stt_base_url=None,
        stt_model="whisper-1",
    )

    try:
        await voice_lifecycle.init_tts_client()
        await voice_lifecycle.init_stt_client()

        tts_provider = voice_lifecycle.get_tts_client()
        stt_provider = voice_lifecycle.get_stt_client()
        assert isinstance(tts_provider, _FakeVolcengineTTSProvider)
        assert isinstance(stt_provider, _FakeVolcengineSTTProvider)
        assert tts_provider.kwargs == {
            "api_key": "volc-tts-key",
            "model": "seed-tts-2.0",
        }
        assert stt_provider.kwargs == {
            "api_key": "volc-stt-key",
            "model": "volc.bigasr.sauc.duration",
        }
    finally:
        await voice_lifecycle.shutdown_tts_client()
        await voice_lifecycle.shutdown_stt_client()
        settings.voice = original_voice


@pytest.mark.asyncio
async def test_volcengine_lifecycle_reuses_tts_key_for_stt_when_dedicated_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_voice = settings.voice
    voice_lifecycle._tts_client = None
    voice_lifecycle._stt_client = None
    _FakeVolcengineSTTProvider.instances = []
    monkeypatch.setattr(
        "infrastructure.external.voice.volcengine_voice.VolcengineSTTProvider",
        _FakeVolcengineSTTProvider,
    )
    settings.voice = VoiceSettings(
        tts_provider="volcengine",
        tts_api_key="volc-shared-speech-key",
        tts_base_url=None,
        tts_model="seed-tts-2.0",
        stt_provider="volcengine",
        stt_api_key=None,
        stt_base_url=None,
        stt_model="volc.bigasr.sauc.duration",
    )

    try:
        await voice_lifecycle.init_stt_client()

        stt_provider = voice_lifecycle.get_stt_client()
        assert isinstance(stt_provider, _FakeVolcengineSTTProvider)
        assert stt_provider.kwargs == {
            "api_key": "volc-shared-speech-key",
            "model": "volc.bigasr.sauc.duration",
        }
    finally:
        await voice_lifecycle.shutdown_stt_client()
        settings.voice = original_voice
