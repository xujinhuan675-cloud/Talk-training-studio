from __future__ import annotations


_PCM_MIME_TYPES = {"audio/l16", "audio/pcm", "audio/pcm16", "audio/s16le"}


def normalize_audio_mime_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def sniff_audio_mime_type(data: bytes, declared_mime_type: str | None = None) -> str:
    """Prefer byte-level container signatures over untrusted transport metadata."""

    if data.startswith(b"OggS"):
        return "audio/ogg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "audio/mp4"
    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"

    declared = normalize_audio_mime_type(declared_mime_type)
    return declared or "application/octet-stream"


def is_pcm_audio_mime_type(value: str | None) -> bool:
    return normalize_audio_mime_type(value) in _PCM_MIME_TYPES


__all__ = [
    "is_pcm_audio_mime_type",
    "normalize_audio_mime_type",
    "sniff_audio_mime_type",
]
