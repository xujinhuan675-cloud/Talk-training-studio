"""add training session actor scope

Revision ID: 8d3e91f4a2b0
Revises: 6f2a1c9b8d04
Create Date: 2026-07-15 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d3e91f4a2b0"
down_revision: Union[str, Sequence[str], None] = "6f2a1c9b8d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "training_sessions",
        sa.Column("user_id", sa.String(length=100), nullable=True, comment="Training actor user ID"),
    )
    op.add_column(
        "training_sessions",
        sa.Column("team_id", sa.String(length=100), nullable=True, comment="Training actor team ID"),
    )
    op.create_index("ix_training_sessions_user_id", "training_sessions", ["user_id"])
    op.create_index("ix_training_sessions_team_id", "training_sessions", ["team_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_training_sessions_team_id", table_name="training_sessions")
    op.drop_index("ix_training_sessions_user_id", table_name="training_sessions")
    op.drop_column("training_sessions", "team_id")
    op.drop_column("training_sessions", "user_id")
