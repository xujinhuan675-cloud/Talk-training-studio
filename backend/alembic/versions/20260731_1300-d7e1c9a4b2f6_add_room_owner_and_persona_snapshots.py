"""add room owner scope and persona snapshots

Revision ID: d7e1c9a4b2f6
Revises: c9d4e7f1a2b3
Create Date: 2026-07-31 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e1c9a4b2f6"
down_revision: Union[str, Sequence[str], None] = "c9d4e7f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """New rooms are directly scoped; legacy rooms retain guarded fallback access."""

    op.add_column(
        "stakeholder_chat_rooms",
        sa.Column("owner_user_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "stakeholder_chat_rooms",
        sa.Column("owner_team_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "stakeholder_chat_rooms",
        sa.Column("persona_snapshots", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_stakeholder_chat_rooms_owner_user_id",
        "stakeholder_chat_rooms",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_stakeholder_chat_rooms_owner_team_id",
        "stakeholder_chat_rooms",
        ["owner_team_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stakeholder_chat_rooms_owner_team_id", table_name="stakeholder_chat_rooms")
    op.drop_index("ix_stakeholder_chat_rooms_owner_user_id", table_name="stakeholder_chat_rooms")
    op.drop_column("stakeholder_chat_rooms", "persona_snapshots")
    op.drop_column("stakeholder_chat_rooms", "owner_team_id")
    op.drop_column("stakeholder_chat_rooms", "owner_user_id")
