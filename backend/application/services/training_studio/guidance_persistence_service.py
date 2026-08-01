"""Bounded, server-owned persistence for message-tree live guidance.

Guidance generated from a selected message path is useful during review, but it
must not become another client-controlled message stream.  This module keeps a
small history in the training session metadata.  The route supplies only the
already-generated server payload; no client event DTO is accepted here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime

GUIDANCE_HISTORY_METADATA_KEY = "liveGuidanceHistory"
GUIDANCE_PERSISTENCE_METADATA_KEY = "liveGuidancePersistence"
GUIDANCE_HISTORY_LIMIT = 12
GUIDANCE_HISTORY_MAX_BYTES = 64_000
GUIDANCE_EVENTS_PER_SNAPSHOT = 5
GUIDANCE_EVENT_METADATA_MAX_BYTES = 4_096
_SENSITIVE_METADATA_TOKENS = (
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)


def append_selected_path_guidance(
    metadata: Mapping[str, object] | None,
    *,
    session_id: str,
    selected_tail_message_id: str,
    events: object,
    source: str,
    context_runtime: str,
    context_selection: str,
    window_size: int,
    total_turn_count: int,
    persisted_at: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Return a trusted metadata patch and a public persistence result.

    ``events`` is intentionally an untyped internal value.  Callers must pass
    the result of ``TrainingLiveGuidanceService``; this function sanitizes that
    result and never copies request metadata or client identity into storage.
    """

    session_token = _required_text(session_id, "session_id")
    tail_token = _required_text(selected_tail_message_id, "selected_tail_message_id")
    event_items = _sanitize_events(events)
    timestamp = persisted_at or datetime.now(UTC).isoformat()
    normalized_context = {
        "source": _bounded_text(source, 80),
        "contextRuntime": _bounded_text(context_runtime, 80),
        "contextSelection": _bounded_text(context_selection, 80),
        "windowSize": max(0, min(int(window_size), 500)),
        "totalTurnCount": max(0, min(int(total_turn_count), 10_000)),
    }
    signature_payload = {
        "sessionId": session_token,
        "selectedTailMessageId": tail_token,
        "events": [
            {key: value for key, value in event.items() if key != "created_at"}
            for event in event_items
        ],
        **normalized_context,
    }
    signature = hashlib.sha256(
        json.dumps(
            signature_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    snapshot_id = f"guidance-{signature[:24]}"
    snapshot = {
        "snapshotId": snapshot_id,
        "selectedTailMessageId": tail_token,
        "persistedAt": timestamp,
        "eventCount": len(event_items),
        "events": event_items,
        **normalized_context,
    }

    existing = _history_from_metadata(metadata)
    duplicate = next((item for item in existing if item.get("snapshotId") == snapshot_id), None)
    if duplicate is None:
        history = [*existing, snapshot][-GUIDANCE_HISTORY_LIMIT:]
        history = _fit_history(history)
        deduplicated = False
    else:
        history = existing
        deduplicated = True

    state = {
        "status": "ready",
        "retryable": False,
        "lastSnapshotId": str((duplicate or snapshot).get("snapshotId") or snapshot_id),
        "lastSelectedTailMessageId": tail_token,
        "lastPersistedAt": str((duplicate or snapshot).get("persistedAt") or timestamp),
        "historyLimit": GUIDANCE_HISTORY_LIMIT,
    }
    patch: dict[str, object] = {
        GUIDANCE_HISTORY_METADATA_KEY: history,
        GUIDANCE_PERSISTENCE_METADATA_KEY: state,
    }
    result = {
        "status": "ready",
        "retryable": False,
        "persisted": True,
        "deduplicated": deduplicated,
        "snapshotId": snapshot_id,
        "selectedTailMessageId": tail_token,
        "savedCount": 0 if deduplicated else len(event_items),
        "historyCount": len(history),
        "historyLimit": GUIDANCE_HISTORY_LIMIT,
    }
    return patch, result


def read_selected_path_guidance_history(
    metadata: Mapping[str, object] | None,
    *,
    selected_tail_message_id: str,
) -> dict[str, object]:
    """Read only snapshots for a server-validated selected path tail."""

    tail_token = _required_text(selected_tail_message_id, "selected_tail_message_id")
    history = [
        item
        for item in _history_from_metadata(metadata)
        if item.get("selectedTailMessageId") == tail_token
    ]
    state = metadata.get(GUIDANCE_PERSISTENCE_METADATA_KEY) if metadata else None
    if not isinstance(state, dict):
        state = {"status": "empty", "retryable": False}
    return {
        "status": "ready" if history else "empty",
        "retryable": False,
        "selectedTailMessageId": tail_token,
        "history": history,
        "historyCount": len(history),
        "historyLimit": GUIDANCE_HISTORY_LIMIT,
        "persistence": dict(state),
    }


def guidance_persistence_failure(*, selected_tail_message_id: str) -> dict[str, object]:
    """Public retry state for a failed metadata write without leaking details."""

    return {
        "status": "failed",
        "retryable": True,
        "persisted": False,
        "code": "guidance_persistence_failed",
        "selectedTailMessageId": _bounded_text(selected_tail_message_id, 160),
    }


def _history_from_metadata(metadata: Mapping[str, object] | None) -> list[dict[str, object]]:
    value = metadata.get(GUIDANCE_HISTORY_METADATA_KEY) if metadata else None
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)][-GUIDANCE_HISTORY_LIMIT:]


def _fit_history(history: list[dict[str, object]]) -> list[dict[str, object]]:
    while len(history) > 1 and _json_size(history) > GUIDANCE_HISTORY_MAX_BYTES:
        history.pop(0)
    return history


def _sanitize_events(events: object) -> list[dict[str, object]]:
    if not isinstance(events, list):
        return []
    sanitized: list[dict[str, object]] = []
    for event in events[:GUIDANCE_EVENTS_PER_SNAPSHOT]:
        if not isinstance(event, dict):
            continue
        item = {
            "event_type": _bounded_text(event.get("event_type"), 80),
            "severity": _bounded_text(event.get("severity"), 40),
            "title": _bounded_text(event.get("title"), 240),
            "message": _bounded_text(event.get("message"), 1_200),
        }
        suggested = _bounded_optional_text(event.get("suggested_text"), 1_000)
        if suggested:
            item["suggested_text"] = suggested
        metadata = event.get("metadata")
        if isinstance(metadata, dict):
            item["metadata"] = _fit_mapping(
                _safe_mapping(metadata),
                max_bytes=GUIDANCE_EVENT_METADATA_MAX_BYTES,
            )
        created_at = _bounded_optional_text(event.get("created_at"), 80)
        if created_at:
            item["created_at"] = created_at
        if item["title"] and item["message"]:
            sanitized.append(item)
    return sanitized


def _safe_mapping(value: Mapping[object, object], *, depth: int = 0) -> dict[str, object]:
    if depth >= 3:
        return {}
    result: dict[str, object] = {}
    for raw_key, raw_value in list(value.items())[:24]:
        key = _bounded_text(raw_key, 80)
        key_token = "".join(character for character in key.lower() if character.isalnum())
        if not key or any(token in key_token for token in _SENSITIVE_METADATA_TOKENS):
            continue
        if isinstance(raw_value, Mapping):
            result[key] = _safe_mapping(raw_value, depth=depth + 1)
        elif isinstance(raw_value, list):
            result[key] = [_safe_scalar(item, depth=depth + 1) for item in raw_value[:12]]
        else:
            result[key] = _safe_scalar(raw_value, depth=depth + 1)
    return result


def _safe_scalar(value: object, *, depth: int) -> object:
    if isinstance(value, Mapping):
        return _safe_mapping(value, depth=depth)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return _bounded_text(value, 400) if isinstance(value, str) else value
    return _bounded_text(value, 400)


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _fit_mapping(value: Mapping[str, object], *, max_bytes: int) -> dict[str, object]:
    fitted: dict[str, object] = {}
    for key, item in value.items():
        candidate = {**fitted, key: item}
        if _json_size(candidate) <= max_bytes:
            fitted[key] = item
    return fitted


def _required_text(value: object, name: str) -> str:
    text = _bounded_text(value, 160)
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _bounded_optional_text(value: object, limit: int) -> str | None:
    text = _bounded_text(value, limit)
    return text or None


def _bounded_text(value: object, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]
