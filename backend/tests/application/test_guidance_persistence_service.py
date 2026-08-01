from __future__ import annotations

import json

from application.services.training_studio.guidance_persistence_service import (
    GUIDANCE_EVENTS_PER_SNAPSHOT,
    GUIDANCE_HISTORY_LIMIT,
    append_selected_path_guidance,
    read_selected_path_guidance_history,
)


def _event(index: int, *, created_at: str | None = None) -> dict[str, object]:
    event: dict[str, object] = {
        "event_type": "risk",
        "severity": "warning",
        "title": f"Risk {index}",
        "message": f"Server guidance {index}",
        "metadata": {"risk_type": "objection", "index": index},
    }
    if created_at is not None:
        event["created_at"] = created_at
    return event


def _append(
    metadata: dict[str, object],
    *,
    tail: str,
    events: list[dict[str, object]],
    persisted_at: str,
) -> tuple[dict[str, object], dict[str, object]]:
    patch, result = append_selected_path_guidance(
        metadata,
        session_id="session-1",
        selected_tail_message_id=tail,
        events=events,
        source="message_tree",
        context_runtime="message_tree",
        context_selection="selected_path",
        window_size=8,
        total_turn_count=12,
        persisted_at=persisted_at,
    )
    metadata.update(patch)
    return patch, result


def test_selected_path_guidance_history_is_bounded_and_filters_by_tail() -> None:
    metadata: dict[str, object] = {}
    for index in range(GUIDANCE_HISTORY_LIMIT + 3):
        _append(
            metadata,
            tail=f"tail-{index % 2}",
            events=[_event(index)],
            persisted_at=f"2026-08-01T00:00:{index:02d}+00:00",
        )

    assert len(metadata["liveGuidanceHistory"]) == GUIDANCE_HISTORY_LIMIT
    history = read_selected_path_guidance_history(
        metadata,
        selected_tail_message_id="tail-1",
    )
    assert history["status"] == "ready"
    assert history["historyCount"] == len(history["history"])
    assert history["history"]
    assert {snapshot["selectedTailMessageId"] for snapshot in history["history"]} == {"tail-1"}


def test_selected_path_guidance_deduplicates_server_events_ignoring_generation_timestamp() -> None:
    metadata: dict[str, object] = {}
    _, first = _append(
        metadata,
        tail="tail-1",
        events=[_event(1, created_at="2026-08-01T00:00:00+00:00")],
        persisted_at="2026-08-01T00:00:01+00:00",
    )
    _, second = _append(
        metadata,
        tail="tail-1",
        events=[_event(1, created_at="2026-08-01T00:00:02+00:00")],
        persisted_at="2026-08-01T00:00:03+00:00",
    )

    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert second["snapshotId"] == first["snapshotId"]
    assert second["savedCount"] == 0
    assert len(metadata["liveGuidanceHistory"]) == 1


def test_selected_path_guidance_sanitizes_and_bounds_each_server_snapshot() -> None:
    metadata: dict[str, object] = {}
    patch, result = _append(
        metadata,
        tail="tail-1",
        events=[
            {
                **_event(index),
                "title": "t" * 500,
                "message": "m" * 3_000,
                "suggested_text": "s" * 3_000,
                "unknown": "not persisted",
                "metadata": {
                    "risk_type": "objection",
                    "api_key": "must-not-be-stored",
                    "nested": {"authorizationToken": "must-not-be-stored"},
                    "details": {f"field-{item}": "x" * 400 for item in range(24)},
                },
            }
            for index in range(GUIDANCE_EVENTS_PER_SNAPSHOT + 4)
        ],
        persisted_at="2026-08-01T00:00:00+00:00",
    )

    snapshot = patch["liveGuidanceHistory"][0]
    assert len(snapshot["events"]) == GUIDANCE_EVENTS_PER_SNAPSHOT
    assert len(snapshot["events"][0]["title"]) == 240
    assert len(snapshot["events"][0]["message"]) == 1_200
    assert len(snapshot["events"][0]["suggested_text"]) == 1_000
    assert "unknown" not in snapshot["events"][0]
    assert snapshot["events"][0]["metadata"] == {
        "risk_type": "objection",
        "nested": {},
    }
    assert len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) < 64_000
    assert result["savedCount"] == GUIDANCE_EVENTS_PER_SNAPSHOT


def test_selected_path_guidance_history_reports_empty_without_fabricating_events() -> None:
    history = read_selected_path_guidance_history(
        {},
        selected_tail_message_id="tail-empty",
    )

    assert history["status"] == "empty"
    assert history["retryable"] is False
    assert history["history"] == []
    assert history["persistence"] == {"status": "empty", "retryable": False}
