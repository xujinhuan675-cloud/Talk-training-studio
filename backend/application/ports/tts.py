# input: 文本 + 语音配置
# output: TTSPort Protocol — 文字转语音抽象接口, TTSConfig 语音配置
# owner: wanhua.gu
# pos: 应用层端口 - TTS 文字转语音抽象接口；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Application-owned TTS port abstraction (hexagonal architecture).

Defines the minimal protocol needed by application use cases so that
the application layer does not depend on specific TTS provider details.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import AsyncIterator, Optional, Protocol, runtime_checkable


DEFAULT_TRAINING_VOICE_ID = "zh_female_vv_uranus_bigtts"
WARM_FEMALE_TRAINING_VOICE_ID = "zh_female_tianmeitaozi_mars_bigtts"
STEADY_MALE_TRAINING_VOICE_ID = "zh_male_dayi_saturn_bigtts"
REFINED_MALE_TRAINING_VOICE_ID = "zh_male_ruyayichen_saturn_bigtts"


@dataclass(frozen=True)
class TrainingVoiceProfile:
    """Provider-neutral voice inventory entry exposed to the training UI."""

    id: str
    provider: str
    service: str
    model: str
    english_label: str
    chinese_label: str
    language: str = "zh-CN"
    tags: tuple[str, ...] = ()
    supports_emotion: bool = False
    supports_speed: bool = True
    supports_loudness: bool = True
    supports_pitch: bool = False
    supports_realtime_s2s: bool = False

    def to_public_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        payload["chinese_label"] = _TRAINING_VOICE_CHINESE_LABELS.get(
            self.id, self.chinese_label
        )
        return payload


# This is intentionally a local, validated inventory. Provider voice IDs are
# not interchangeable across streaming TTS, async TTS, and native S2S APIs.
TRAINING_VOICE_CATALOG: tuple[TrainingVoiceProfile, ...] = (
    TrainingVoiceProfile(
        id=DEFAULT_TRAINING_VOICE_ID,
        provider="volcengine",
        service="tts_streaming",
        model="doubao-bigtts",
        english_label="Vivi 2.0",
        chinese_label="Vivi 2.0（活泼女声）",
        tags=("female", "lively", "zh-CN"),
        supports_emotion=True,
    ),
    TrainingVoiceProfile(
        id=WARM_FEMALE_TRAINING_VOICE_ID,
        provider="volcengine",
        service="tts_streaming",
        model="doubao-bigtts",
        english_label="Tianmei Taozi",
        chinese_label="甜美桃子（温柔女声）",
        tags=("female", "warm", "zh-CN"),
        supports_emotion=True,
    ),
    TrainingVoiceProfile(
        id=STEADY_MALE_TRAINING_VOICE_ID,
        provider="volcengine",
        service="tts_streaming",
        model="doubao-bigtts",
        english_label="Da Yi",
        chinese_label="大奕（沉稳男声）",
        tags=("male", "steady", "zh-CN"),
        supports_emotion=True,
    ),
    TrainingVoiceProfile(
        id=REFINED_MALE_TRAINING_VOICE_ID,
        provider="volcengine",
        service="tts_streaming",
        model="doubao-bigtts",
        english_label="Ruya Yichen",
        chinese_label="儒雅逸辰（儒雅男声）",
        tags=("male", "refined", "zh-CN"),
        supports_emotion=True,
    ),
)

_TRAINING_VOICE_CHINESE_LABELS = {
    DEFAULT_TRAINING_VOICE_ID: "Vivi 2.0（活泼女声）",
    WARM_FEMALE_TRAINING_VOICE_ID: "甜美桃子（温柔女声）",
    STEADY_MALE_TRAINING_VOICE_ID: "大壹（沉稳男声）",
    REFINED_MALE_TRAINING_VOICE_ID: "儒雅逸辰（儒雅男声）",
}

SUPPORTED_TRAINING_VOICE_IDS = frozenset(item.id for item in TRAINING_VOICE_CATALOG)


def training_voice_profile(value: str | None) -> TrainingVoiceProfile | None:
    voice_id = str(value or "").strip()
    if not voice_id:
        return None
    return next((item for item in TRAINING_VOICE_CATALOG if item.id == voice_id), None)


def normalize_training_voice_id(value: str | None) -> str | None:
    voice_id = str(value or "").strip()
    if not voice_id:
        return None
    if voice_id not in SUPPORTED_TRAINING_VOICE_IDS:
        raise ValueError("voice_id is not compatible with the configured training TTS resource")
    return voice_id


@dataclass
class TTSConfig:
    """Configuration for a single TTS synthesis request."""

    voice_id: str
    speed: float = 1.0
    volume: float = 1.0
    pitch: float = 0.0
    style_instruction: Optional[str] = None
    language: Optional[str] = None


@runtime_checkable
class TTSPort(Protocol):
    """Port for text-to-speech synthesis."""

    async def synthesize_stream(
        self,
        text: str,
        config: TTSConfig,
    ) -> AsyncIterator[bytes]:
        """Stream audio chunks for the given text.

        Args:
            text: Text to synthesize.
            config: Voice configuration (voice_id, speed, style, etc.).

        Yields:
            Audio bytes in mp3 format.
        """
        ...
