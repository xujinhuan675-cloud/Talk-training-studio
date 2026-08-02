"""Domain contracts for the persistent Training Points ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TrainingPointEvent:
    user_id: str
    team_id: str | None
    source_type: str
    source_id: str
    event_type: str
    points: int
    created_at: datetime
    id: int | None = None
