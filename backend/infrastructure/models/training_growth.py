"""Persistent Training Points ledger."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


class TrainingPointEventModel(Base):
    """One idempotent growth event derived from a trusted training lifecycle."""

    __tablename__ = "training_point_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "event_type",
            name="uq_training_point_event_source",
        ),
        Index("ix_training_point_events_user_created", "user_id", "created_at"),
        Index("ix_training_point_events_team", "team_id"),
        {"comment": "Idempotent TalkWise Training Points ledger"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False)
    team_id = Column(String(100), nullable=True)
    source_type = Column(String(40), nullable=False)
    source_id = Column(String(160), nullable=False)
    event_type = Column(String(60), nullable=False)
    points = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
