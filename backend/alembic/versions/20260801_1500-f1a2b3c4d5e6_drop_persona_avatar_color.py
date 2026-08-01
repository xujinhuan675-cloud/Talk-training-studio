"""drop persona avatar color

Revision ID: f1a2b3c4d5e6
Revises: e4f8b6c2d1a9
Create Date: 2026-08-01 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e4f8b6c2d1a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stakeholder_personas") as batch_op:
        batch_op.drop_column("avatar_color")


def downgrade() -> None:
    with op.batch_alter_table("stakeholder_personas") as batch_op:
        batch_op.add_column(sa.Column("avatar_color", sa.String(length=20), nullable=True))
