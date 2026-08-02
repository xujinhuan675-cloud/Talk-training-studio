"""add training point ledger

Revision ID: a8c4e2f6b1d9
Revises: f1a2b3c4d5e6
Create Date: 2026-08-01 17:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c4e2f6b1d9"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_point_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("team_id", sa.String(length=100), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "event_type",
            name="uq_training_point_event_source",
        ),
        comment="Idempotent TalkWise Training Points ledger",
    )
    op.create_index(
        "ix_training_point_events_user_created",
        "training_point_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_training_point_events_team",
        "training_point_events",
        ["team_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_training_point_events_team", table_name="training_point_events")
    op.drop_index("ix_training_point_events_user_created", table_name="training_point_events")
    op.drop_table("training_point_events")
