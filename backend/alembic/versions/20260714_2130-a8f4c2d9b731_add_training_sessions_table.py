"""add training_sessions table

Revision ID: a8f4c2d9b731
Revises: c57befdb069e
Create Date: 2026-07-14 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8f4c2d9b731"
down_revision: Union[str, Sequence[str], None] = "c57befdb069e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "training_sessions",
        sa.Column("session_id", sa.String(length=100), nullable=False, comment="Session ID"),
        sa.Column(
            "task_config",
            sa.JSON(),
            nullable=False,
            comment="Normalized training task config",
        ),
        sa.Column("mode", sa.String(length=20), nullable=False, comment="text/voice/video/realtime"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="created/active/completed/failed"),
        sa.Column("room_id", sa.String(length=100), nullable=True, comment="Bound chat room ID"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True, comment="Started at"),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Completed at",
        ),
        sa.Column("report_id", sa.String(length=100), nullable=True, comment="Post-session report ID"),
        sa.Column("score_id", sa.String(length=100), nullable=True, comment="Post-session score ID"),
        sa.Column(
            "message_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True, comment="Failure reason"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
            comment="Created at",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
            comment="Updated at",
        ),
        sa.PrimaryKeyConstraint("session_id"),
        comment="Training Studio session lifecycle state",
    )
    op.create_index("ix_training_sessions_room_id", "training_sessions", ["room_id"])
    op.create_index("ix_training_sessions_status", "training_sessions", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_training_sessions_status", table_name="training_sessions")
    op.drop_index("ix_training_sessions_room_id", table_name="training_sessions")
    op.drop_table("training_sessions")
