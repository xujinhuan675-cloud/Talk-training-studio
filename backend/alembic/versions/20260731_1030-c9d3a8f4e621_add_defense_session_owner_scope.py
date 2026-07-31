"""add defense session owner scope

Revision ID: c9d3a8f4e621
Revises: b7f6a3d2c9e1
Create Date: 2026-07-31 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d3a8f4e621"
down_revision: Union[str, Sequence[str], None] = "b7f6a3d2c9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add auditable ownership without exposing legacy rows by default."""

    op.add_column(
        "defense_sessions",
        sa.Column("owner_user_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "defense_sessions",
        sa.Column("owner_team_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_defense_sessions_owner_user_id",
        "defense_sessions",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_defense_sessions_owner_team_id",
        "defense_sessions",
        ["owner_team_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_defense_sessions_owner_team_id", table_name="defense_sessions")
    op.drop_index("ix_defense_sessions_owner_user_id", table_name="defense_sessions")
    op.drop_column("defense_sessions", "owner_team_id")
    op.drop_column("defense_sessions", "owner_user_id")
