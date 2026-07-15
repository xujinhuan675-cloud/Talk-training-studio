"""Training Studio session database model."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.sql import func

from .base import Base


class TrainingSessionModel(Base):
    """ORM mapping for training_sessions table."""

    __tablename__ = "training_sessions"
    __table_args__ = (
        Index("ix_training_sessions_status", "status"),
        Index("ix_training_sessions_room_id", "room_id"),
        Index("ix_training_sessions_scenario_template_id", "scenario_template_id"),
        Index("ix_training_sessions_user_id", "user_id"),
        Index("ix_training_sessions_team_id", "team_id"),
        {"comment": "Training Studio session lifecycle state"},
    )

    session_id = Column(String(100), primary_key=True, comment="Session ID")
    task_config = Column(JSON, nullable=False, comment="Normalized training task config")
    mode = Column(String(20), nullable=False, comment="text/voice/video/realtime")
    scenario_template_id = Column(String(100), nullable=True, comment="Scenario training template ID")
    user_id = Column(String(100), nullable=True, comment="Training actor user ID")
    team_id = Column(String(100), nullable=True, comment="Training actor team ID")
    status = Column(String(20), nullable=False, comment="created/active/completed/failed")
    room_id = Column(String(100), nullable=True, comment="Bound chat room ID")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="Started at")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="Completed at")
    report_id = Column(String(100), nullable=True, comment="Post-session report ID")
    score_id = Column(String(100), nullable=True, comment="Post-session score ID")
    message_count = Column(Integer, nullable=False, default=0, server_default="0")
    failure_reason = Column(Text, nullable=True, comment="Failure reason")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="Created at",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Updated at",
    )
