"""add stakeholder message metadata

Revision ID: 2b7c9d4e5f61
Revises: a8f4c2d9b731
Create Date: 2026-07-15 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b7c9d4e5f61"
down_revision: Union[str, Sequence[str], None] = "a8f4c2d9b731"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "stakeholder_messages",
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Structured message metadata",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stakeholder_messages", "metadata")
