"""add persona asset ownership and version

Revision ID: c9d4e7f1a2b3
Revises: c9d3a8f4e621
Create Date: 2026-07-31 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d4e7f1a2b3"
down_revision: Union[str, Sequence[str], None] = "c9d3a8f4e621"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stakeholder_personas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("owner_team_id", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private")
        )
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_index("ix_stakeholder_personas_owner_user_id", ["owner_user_id"])
        batch_op.create_index("ix_stakeholder_personas_owner_team_id", ["owner_team_id"])


def downgrade() -> None:
    with op.batch_alter_table("stakeholder_personas", schema=None) as batch_op:
        batch_op.drop_index("ix_stakeholder_personas_owner_team_id")
        batch_op.drop_index("ix_stakeholder_personas_owner_user_id")
        batch_op.drop_column("version")
        batch_op.drop_column("visibility")
        batch_op.drop_column("owner_team_id")
        batch_op.drop_column("owner_user_id")
