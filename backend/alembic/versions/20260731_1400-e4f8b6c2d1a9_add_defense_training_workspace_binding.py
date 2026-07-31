"""add Defense Prep training workspace binding

Revision ID: e4f8b6c2d1a9
Revises: d7e1c9a4b2f6
Create Date: 2026-07-31 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4f8b6c2d1a9"
down_revision: Union[str, Sequence[str], None] = "d7e1c9a4b2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "defense_sessions",
        sa.Column("training_session_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "defense_sessions",
        sa.Column("conversation_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_defense_sessions_training_session_id",
        "defense_sessions",
        ["training_session_id"],
    )
    op.create_index(
        "ix_defense_sessions_conversation_id",
        "defense_sessions",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_defense_sessions_conversation_id", table_name="defense_sessions")
    op.drop_index("ix_defense_sessions_training_session_id", table_name="defense_sessions")
    op.drop_column("defense_sessions", "conversation_id")
    op.drop_column("defense_sessions", "training_session_id")
