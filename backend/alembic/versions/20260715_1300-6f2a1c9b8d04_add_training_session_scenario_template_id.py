"""add training session scenario template id

Revision ID: 6f2a1c9b8d04
Revises: 2b7c9d4e5f61
Create Date: 2026-07-15 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f2a1c9b8d04"
down_revision: Union[str, Sequence[str], None] = "2b7c9d4e5f61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "training_sessions",
        sa.Column(
            "scenario_template_id",
            sa.String(length=100),
            nullable=True,
            comment="Scenario training template ID",
        ),
    )
    op.create_index(
        "ix_training_sessions_scenario_template_id",
        "training_sessions",
        ["scenario_template_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_training_sessions_scenario_template_id", table_name="training_sessions")
    op.drop_column("training_sessions", "scenario_template_id")
